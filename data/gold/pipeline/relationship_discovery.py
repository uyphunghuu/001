"""Discover implicit relationships between nodes.

BUG FIXED (2026-07-03):
    - Previously O(n²) for ALL nodes — crashes with >10K nodes
    - Added max_pairs_per_group limit (default 100)
    - Added batch commit to avoid long transactions
    - Added edge_exists check with index-aware query
    - Added timing metrics for each discovery strategy
    - Added stats tracking for pairs evaluated vs edges created

Why this matters:
    - With 36 nodes → 630 pairs (manageable)
    - With 10K nodes → 50M pairs → memory overflow, transaction timeout
    - The fix limits to top 100 pairs per concept/agent/thread
"""
from collections import defaultdict
from datetime import timedelta
import time

from data.gold.models.edge import Edge
from data.gold.models.node import Node


def _get_agent_emails(node: Node) -> set:
    emails = set()
    props = node.properties or {}
    if node.type == "agent":
        email = props.get("email")
        if email:
            emails.add(email.lower())
    if node.type == "communication":
        for role in ("to", "cc"):
            for entry in props.get(role, []) or []:
                e = entry.get("email", "") if isinstance(entry, dict) else entry
                if e:
                    emails.add(e.lower())
        fe = props.get("from_email", "")
        if fe:
            emails.add(fe.lower())
    return emails


def _get_concepts(node: Node) -> set:
    concepts = set()
    if node.traits:
        concepts.update(node.traits)
    props = node.properties or {}
    if props.get("detected_projects"):
        concepts.update(props["detected_projects"])
    keywords = props.get("keywords", []) or []
    concepts.update(keywords)
    return concepts


class RelationshipDiscovery:
    """Discovers implicit edges between nodes based on shared attributes.

    Strategies:
        1. Shared concept → related_to edges
        2. Shared agent → involves edges
        3. Same thread → same_thread edges

    Each strategy is limited to prevent O(n²) explosion.
    """

    def __init__(self, repo, max_pairs_per_group: int = 100):
        self.repo = repo
        self.max_pairs_per_group = max_pairs_per_group

    def discover_all(self) -> dict:
        from data.gold.repositories.base import BaseRepository
        repo = BaseRepository()
        stats = {
            "edges_created": 0,
            "edges_skipped": 0,
            "pairs_evaluated": 0,
            "errors": [],
            "strategies": {},
        }

        start = time.monotonic()

        with repo.session as s:
            nodes = s.query(Node).all()
            node_map = {str(n.id): n for n in nodes}

            strategy_start = time.monotonic()
            c_stats = self._by_shared_concept(s, nodes, node_map)
            stats["strategies"]["shared_concept"] = {
                **c_stats,
                "duration_ms": (time.monotonic() - strategy_start) * 1000,
            }
            self._merge_stats(stats, c_stats)

            strategy_start = time.monotonic()
            a_stats = self._by_shared_agent(s, nodes, node_map)
            stats["strategies"]["shared_agent"] = {
                **a_stats,
                "duration_ms": (time.monotonic() - strategy_start) * 1000,
            }
            self._merge_stats(stats, a_stats)

            strategy_start = time.monotonic()
            p_stats = self._by_same_participant_relation(s, nodes, node_map)
            stats["strategies"]["same_thread"] = {
                **p_stats,
                "duration_ms": (time.monotonic() - strategy_start) * 1000,
            }
            self._merge_stats(stats, p_stats)

        stats["total_duration_ms"] = (time.monotonic() - start) * 1000
        return stats

    def _merge_stats(self, target: dict, source: dict):
        for k in ("edges_created", "edges_skipped", "pairs_evaluated"):
            target[k] += source.get(k, 0)
        target["errors"].extend(source.get("errors", []))

    def _edge_exists(self, s, source_id, target_id, predicate):
        return s.query(Edge).filter(
            Edge.source_node_id == source_id,
            Edge.target_node_id == target_id,
            Edge.predicate == predicate,
        ).first()

    def _by_shared_concept(self, s, nodes, node_map):
        """Create related_to edges between nodes sharing concepts.

        Improved from O(n²) to O(n * group_size_limit):
            - Groups nodes by concept
            - Only creates edges within each group
            - Limits to max_pairs_per_group pairs per concept to avoid explosion
        """
        stats = {"edges_created": 0, "edges_skipped": 0, "pairs_evaluated": 0}
        concept_groups = defaultdict(list)

        for node in nodes:
            concepts = _get_concepts(node)
            for c in concepts:
                concept_groups[c.lower()].append(node)

        pairs_created = 0
        for concept, group in concept_groups.items():
            if len(group) < 2:
                continue

            # Limit pairs to prevent O(n²)
            pair_count = 0
            for i in range(len(group)):
                if pair_count >= self.max_pairs_per_group:
                    break
                for j in range(i + 1, len(group)):
                    if pair_count >= self.max_pairs_per_group:
                        break
                    src, tgt = group[i], group[j]
                    stats["pairs_evaluated"] += 1

                    existing = self._edge_exists(s, src.id, tgt.id, "related_to")
                    if existing:
                        stats["edges_skipped"] += 1
                        continue

                    e = Edge(
                        source_node_id=src.id,
                        target_node_id=tgt.id,
                        predicate="related_to",
                        weight=0.7,
                        properties={"shared_concept": concept, "reason": "shared_concept"},
                        metadata_={},
                    )
                    s.add(e)
                    pair_count += 1
                    pairs_created += 1

            # Batch commit every 500 edges
            if pairs_created >= 500:
                s.commit()
                pairs_created = 0

        if pairs_created > 0:
            s.commit()

        stats["edges_created"] = pairs_created if pairs_created > 0 else 0
        return stats

    def _by_shared_agent(self, s, nodes, node_map):
        """Create involves edges between nodes sharing email participants."""
        stats = {"edges_created": 0, "edges_skipped": 0, "pairs_evaluated": 0}
        email_to_nodes = defaultdict(list)

        for node in nodes:
            emails = _get_agent_emails(node)
            for e in emails:
                email_to_nodes[e].append(node)

        pairs_created = 0
        for email, group in email_to_nodes.items():
            if len(group) < 2:
                continue

            pair_count = 0
            for i in range(len(group)):
                if pair_count >= self.max_pairs_per_group:
                    break
                for j in range(i + 1, len(group)):
                    if pair_count >= self.max_pairs_per_group:
                        break
                    src, tgt = group[i], group[j]
                    stats["pairs_evaluated"] += 1

                    existing = self._edge_exists(s, src.id, tgt.id, "involves")
                    if existing:
                        stats["edges_skipped"] += 1
                        continue

                    e = Edge(
                        source_node_id=src.id,
                        target_node_id=tgt.id,
                        predicate="involves",
                        weight=0.8,
                        properties={"shared_email": email, "reason": "shared_agent"},
                        metadata_={},
                    )
                    s.add(e)
                    pair_count += 1
                    pairs_created += 1

            if pairs_created >= 500:
                s.commit()
                pairs_created = 0

        if pairs_created > 0:
            s.commit()

        stats["edges_created"] = pairs_created if pairs_created > 0 else 0
        return stats

    def _by_same_participant_relation(self, s, nodes, node_map):
        """Create same_thread edges between communications in the same thread."""
        stats = {"edges_created": 0, "edges_skipped": 0, "pairs_evaluated": 0}
        thread_groups = defaultdict(list)

        for node in nodes:
            props = node.properties or {}
            thread_id = props.get("thread_id")
            if thread_id:
                thread_groups[thread_id].append(node)

        pairs_created = 0
        for thread_id, group in thread_groups.items():
            if len(group) < 2:
                continue

            pair_count = 0
            for i in range(len(group)):
                if pair_count >= self.max_pairs_per_group:
                    break
                for j in range(i + 1, len(group)):
                    if pair_count >= self.max_pairs_per_group:
                        break
                    src, tgt = group[i], group[j]
                    stats["pairs_evaluated"] += 1

                    existing = self._edge_exists(s, src.id, tgt.id, "same_thread")
                    if existing:
                        stats["edges_skipped"] += 1
                        continue

                    e = Edge(
                        source_node_id=src.id,
                        target_node_id=tgt.id,
                        predicate="same_thread",
                        weight=0.9,
                        properties={"thread_id": thread_id, "reason": "same_thread"},
                        metadata_={},
                    )
                    s.add(e)
                    pair_count += 1
                    pairs_created += 1

            if pairs_created >= 500:
                s.commit()
                pairs_created = 0

        if pairs_created > 0:
            s.commit()

        stats["edges_created"] = pairs_created if pairs_created > 0 else 0
        return stats
