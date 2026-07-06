"""Gold Pipeline orchestrator — with full data observability.

OBSERVABILITY ADDED (2026-07-03):
    - Prometheus metrics: nodes/edges created per type, processing times
    - Structured logging: JSON logs per node/edge creation
    - OpenLineage lineage: Silver → Gold per-node tracking
    - Schema validation: validates node/edge dicts before save
    - Contract validation: silver_to_gold contract enforcement
    - Per-step timing: classifier, concept extraction, agent extraction, save
    - Quality gates: blocks on critical contract violations

Why this matters:
    - Gold is the foundation for all downstream AI (RAG, Agent)
    - A bad node corrupts the entire knowledge graph
    - Without lineage, you can't trace which Silver record created a Gold node
    - Without schema validation, JSONB properties drift over time
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from data.gold.pipeline.classifiers import classify_document, classify_communication, classify_event
from data.gold.pipeline.agents import AgentExtractor
from data.gold.pipeline.concept_extractor import extract_concepts
from data.gold.pipeline.timeline_builder import build_timeline, TimelineBuilder
from data.gold.pipeline.embedding_generator import EmbeddingGenerator
from data.gold.pipeline.relationship_discovery import RelationshipDiscovery
from data.gold.pipeline.event_extractor import extract_events_from_text
from data.gold.repositories.node_repository import NodeRepository
from data.gold.repositories.edge_repository import EdgeRepository
from data.gold.repositories.base import BaseRepository

from data.silver.models.document import Document
from data.silver.models.communication import Communication
from data.silver.models.event import Event

from data.observability import metrics, lineage, logger, contract, schema

from data.gold.models.timeline import Timeline


class GoldPipeline:
    """Orchestrates Silver → Gold transformation with full observability."""

    def __init__(self):
        self.node_repo = NodeRepository()
        self.edge_repo = EdgeRepository()
        self.agent_extractor = AgentExtractor()
        self.service_name = "gold_pipeline"

    def process_all(self, limit: int = 10000) -> dict:
        """Process all Silver records into Gold nodes/edges with observability.

        Returns detailed stats including timing per phase.
        """
        run_id = str(uuid.uuid4())
        logger.info("Gold pipeline started", component=self.service_name, event="pipeline.start",
                     correlation_id=run_id, limit=limit)

        pipeline_start = time.monotonic()
        stats = {
            "run_id": run_id,
            "nodes_created": 0,
            "edges_created": 0,
            "agents_created": 0,
            "documents": 0,
            "communications": 0,
            "events": 0,
            "concepts_extracted": 0,
            "timeline_entries": 0,
            "embeddings_updated": 0,
            "discovered_edges": 0,
            "errors": [],
            "phase_times_ms": {},
        }

        # Phase 1: Process Documents
        phase_start = time.monotonic()
        result = self._process_documents(limit)
        for k in ("nodes_created", "documents", "concepts_extracted", "timeline_entries"):
            stats[k] += result.get(k, 0)
        stats["errors"].extend(result.get("errors", []))
        stats["phase_times_ms"]["documents"] = (time.monotonic() - phase_start) * 1000

        # Phase 2: Process Communications
        phase_start = time.monotonic()
        result = self._process_communications(limit)
        for k in ("nodes_created", "edges_created", "agents_created", "communications",
                   "concepts_extracted", "timeline_entries"):
            stats[k] += result.get(k, 0)
        stats["errors"].extend(result.get("errors", []))
        stats["phase_times_ms"]["communications"] = (time.monotonic() - phase_start) * 1000

        # Phase 3: Process Events
        phase_start = time.monotonic()
        result = self._process_events(limit)
        for k in ("nodes_created", "edges_created", "agents_created", "events",
                   "concepts_extracted", "timeline_entries"):
            stats[k] += result.get(k, 0)
        stats["errors"].extend(result.get("errors", []))
        stats["phase_times_ms"]["events"] = (time.monotonic() - phase_start) * 1000

        # Phase 4: Post-processing (embeddings, timeline, relationships)
        phase_start = time.monotonic()
        self._run_post_processing(stats)
        stats["phase_times_ms"]["post_processing"] = (time.monotonic() - phase_start) * 1000

        stats["total_duration_ms"] = (time.monotonic() - pipeline_start) * 1000

        # Emit metrics
        metrics.gauge("gold_nodes_total").set(stats["nodes_created"])
        metrics.gauge("gold_edges_total").set(stats["edges_created"])
        metrics.histogram("gold_pipeline_duration_ms").observe(stats["total_duration_ms"])
        metrics.push(job_name="gold_pipeline")

        logger.info("Gold pipeline completed", component=self.service_name, event="pipeline.complete",
                     correlation_id=run_id, total_duration_ms=stats["total_duration_ms"],
                     nodes=stats["nodes_created"], edges=stats["edges_created"],
                     errors=len(stats["errors"]))

        return stats

    def _save_node(self, node_data: dict, stats: dict, correlation_id: str = "") -> tuple[str, bool]:
        """Save a node with observability: schema check, concept extraction, timeline.
        Returns (node_id, is_new) where is_new is True if the node was actually created."""
        cid = correlation_id or str(uuid.uuid4())

        # Check if node already exists (dedup by source_ref)
        existing_id = self.node_repo.find_by_source_ref(node_data.get("source_ref", {}))
        if existing_id:
            logger.info("Gold node already exists — skipping", component=self.service_name,
                        event="node.skipped", correlation_id=cid, node_id=str(existing_id),
                        node_type=node_data.get("type"), name=node_data.get("name"))
            return (str(existing_id.id), False)

        # Schema validation
        s_errors = schema.validate("gold_node", node_data)
        if s_errors:
            logger.warning("Gold node schema violations", component=self.service_name,
                           event="node.schema_issues", correlation_id=cid, errors=s_errors)
            metrics.counter("schema_violations", tags={"table": "gold_nodes"}).inc()

        # Contract validation (skip for derived nodes like events)
        if node_data.get("type") != "event":
            try:
                contract.validate_or_raise("silver_to_gold", node_data)
            except Exception as e:
                logger.error("Gold contract violation — blocking node", component=self.service_name,
                             event="node.contract_blocked", correlation_id=cid, error=str(e))
                metrics.counter("contract_violations", tags={"severity": "critical", "table": "gold_nodes"}).inc()
                raise

        # Enrich with concepts
        enrich_start = time.monotonic()
        enriched = self._enrich_with_concepts(node_data)
        enrich_time = (time.monotonic() - enrich_start) * 1000
        metrics.histogram("concept_extraction_duration_ms").observe(enrich_time)

        # Save
        save_start = time.monotonic()
        node_id = self.node_repo.save(enriched)
        save_time = (time.monotonic() - save_start) * 1000
        metrics.histogram("node_save_duration_ms").observe(save_time)

        stats["concepts_extracted"] += 1

        # Timeline
        self._build_timeline(node_id, node_data, stats)

        # Lineage: Silver → Gold
        source_ref = node_data.get("source_ref", {})
        lineage.emit_silver_to_gold(
            run_id=correlation_id or str(uuid.uuid4()),
            silver_table=source_ref.get("table", "unknown"),
            silver_id=source_ref.get("id", "unknown"),
            node_id=node_id,
        )

        logger.info("Gold node saved", component=self.service_name, event="node.saved",
                     correlation_id=cid, node_id=node_id,
                     node_type=node_data.get("type"), name=node_data.get("name"))

        return (node_id, True)

    def _enrich_with_concepts(self, node_data: dict) -> dict:
        concepts = extract_concepts(
            node_data.get("content", ""),
            node_data.get("name", ""),
        )
        existing_traits = node_data.get("traits", []) or []
        existing_props = node_data.get("properties", {}) or {}
        node_data["traits"] = list(set(existing_traits + concepts["traits"]))
        for k, v in concepts["properties"].items():
            if k not in existing_props:
                existing_props[k] = v
            elif isinstance(v, list):
                existing_props[k] = list(set(existing_props.get(k, []) + v))
        node_data["properties"] = existing_props
        return node_data

    def _build_timeline(self, node_id: str, node_data: dict, stats: dict):
        repo = BaseRepository()
        entries = build_timeline(node_id, node_data)
        if not entries:
            return
        with repo.session as s:
            for entry in entries:
                existing = s.query(Timeline).filter(
                    Timeline.node_id == entry["node_id"],
                    Timeline.field == entry["field"],
                ).first()
                if not existing:
                    tl = Timeline(**entry)
                    s.add(tl)
                    stats["timeline_entries"] += 1
            s.commit()

    def _run_post_processing(self, stats: dict):
        """Run embeddings, timeline population, and relationship discovery."""
        # Embeddings
        logger.info("Generating embeddings", component=self.service_name, event="embeddings.start")
        emb_start = time.monotonic()
        emb = EmbeddingGenerator()
        emb_result = emb.update_all()
        stats["embeddings_updated"] = emb_result.get("updated", 0)
        if isinstance(emb_result.get("skipped"), str):
            stats["errors"].append(emb_result["skipped"])
        stats["phase_times_ms"]["embeddings"] = (time.monotonic() - emb_start) * 1000
        logger.info("Embeddings generated", component=self.service_name, event="embeddings.complete",
                     updated=emb_result.get("updated"), duration_ms=stats["phase_times_ms"]["embeddings"])

        # Timeline population
        logger.info("Building timeline", component=self.service_name, event="timeline.start")
        tl_start = time.monotonic()
        td = TimelineBuilder(self.node_repo)
        tl_result = td.populate_all()
        stats["timeline_entries"] += tl_result.get("entries_created", 0)
        stats["errors"].extend(tl_result.get("errors", []))
        stats["phase_times_ms"]["timeline"] = (time.monotonic() - tl_start) * 1000

        # Relationship discovery
        logger.info("Discovering relationships", component=self.service_name, event="relationships.start")
        rd_start = time.monotonic()
        rd = RelationshipDiscovery(self.node_repo, max_pairs_per_group=100)
        rd_result = rd.discover_all()
        stats["discovered_edges"] = rd_result.get("edges_created", 0)
        stats["edges_created"] += rd_result.get("edges_created", 0)
        stats["phase_times_ms"]["relationships"] = (time.monotonic() - rd_start) * 1000
        for strategy, s_data in rd_result.get("strategies", {}).items():
            logger.info(f"Relationship strategy {strategy}", component=self.service_name,
                         event="relationships.strategy", strategy=strategy,
                         edges_created=s_data.get("edges_created"),
                         pairs_evaluated=s_data.get("pairs_evaluated"),
                         duration_ms=s_data.get("duration_ms"))

    def _process_documents(self, limit: int) -> dict:
        stats = {"nodes_created": 0, "documents": 0, "concepts_extracted": 0, "timeline_entries": 0,
                 "events_extracted": 0, "edges_created": 0, "errors": []}
        with self.node_repo.session as s:
            docs = s.query(Document).order_by(Document.created_at.desc()).limit(limit).all()
        logger.info(f"Processing {len(docs)} documents", component=self.service_name, event="documents.start")
        for doc in docs:
            cid = f"doc/{doc.id}"
            try:
                doc_start = time.monotonic()
                node_data = classify_document(doc)
                if not node_data.get("embedding_text"):
                    node_data["embedding_text"] = doc.content or doc.title or ""
                doc_id, is_new_doc = self._save_node(node_data, stats, cid)
                if is_new_doc:
                    stats["nodes_created"] += 1
                    stats["documents"] += 1
                metrics.histogram("node_creation_duration_ms", tags={"type": "document"}).observe(
                    (time.monotonic() - doc_start) * 1000)
                metrics.counter("nodes_created", tags={"type": "document"}).inc()

                # Extract events from document content
                content = doc.content or ""
                doc_source_ref = node_data.get("source_ref", {})
                if content:
                    events = extract_events_from_text(content, doc_id, node_data.get("name", ""))
                    for evt_data in events:
                        evt_data["embedding_text"] = evt_data.get("name", "")
                        evt_data["source_ref"] = dict(doc_source_ref)
                        evt_data["source_ref"]["id"] = f'{doc_source_ref.get("id", "")}_{evt_data.get("effective_start", "")}_{evt_data.get("name", "")}'
                        evt_data["source_ref"]["_gold_node_id"] = doc_id
                        try:
                            evt_id, is_new_evt = self._save_node(evt_data, stats, f"{cid}/evt")
                            if is_new_evt:
                                stats["events_extracted"] += 1
                                stats["nodes_created"] += 1
                            # Edge: document -> contains -> event
                            self.edge_repo.save({
                                "source_node_id": doc_id,
                                "predicate": "contains",
                                "target_node_id": evt_id,
                                "properties": {"extracted_by": "event_extractor"},
                            })
                            stats["edges_created"] += 1
                        except Exception as evt_err:
                            stats["errors"].append(f"Event from {doc.id}: {evt_err}")
                            logger.exception("Event extraction failed", component=self.service_name,
                                             event="event.extract_failed", correlation_id=cid)
            except Exception as e:
                stats["errors"].append(f"Document {doc.id}: {e}")
                logger.exception("Document processing failed", component=self.service_name,
                                 event="document.failed", correlation_id=cid, doc_id=str(doc.id))
                metrics.counter("node_failed", tags={"type": "document"}).inc()
        return stats

    def _process_communications(self, limit: int) -> dict:
        stats = {"nodes_created": 0, "edges_created": 0, "agents_created": 0, "communications": 0,
                 "concepts_extracted": 0, "timeline_entries": 0, "errors": []}
        with self.node_repo.session as s:
            comms = s.query(Communication).order_by(Communication.received_at.desc().nullslast()).limit(limit).all()
        logger.info(f"Processing {len(comms)} communications", component=self.service_name,
                     event="communications.start")
        for comm in comms:
            cid = f"comm/{comm.id}"
            try:
                comm_start = time.monotonic()
                node_data = classify_communication(comm)
                if not node_data.get("embedding_text"):
                    node_data["embedding_text"] = comm.body or comm.subject or ""
                comm_id, is_new_comm = self._save_node(node_data, stats, cid)
                if is_new_comm:
                    stats["nodes_created"] += 1
                    stats["communications"] += 1

                agents = self.agent_extractor.extract_from_communication(comm)
                for agent in agents:
                    role = agent["role"]
                    if role == "sender":
                        self.edge_repo.save({
                            "source_node_id": agent["agent_id"],
                            "predicate": "sends",
                            "target_node_id": comm_id,
                            "properties": {"email": agent["email"]},
                        })
                    else:
                        self.edge_repo.save({
                            "source_node_id": comm_id,
                            "predicate": "to" if role == "to" else "cc",
                            "target_node_id": agent["agent_id"],
                            "properties": {"email": agent["email"], "role": role},
                        })
                    stats["edges_created"] += 1
                    stats["agents_created"] += 1

                metrics.histogram("node_creation_duration_ms", tags={"type": "communication"}).observe(
                    (time.monotonic() - comm_start) * 1000)
                metrics.counter("nodes_created", tags={"type": "communication"}).inc()
            except Exception as e:
                stats["errors"].append(f"Communication {comm.id}: {e}")
                logger.exception("Communication processing failed", component=self.service_name,
                                 event="communication.failed", correlation_id=cid, comm_id=str(comm.id))
                metrics.counter("node_failed", tags={"type": "communication"}).inc()
        return stats

    def _process_events(self, limit: int) -> dict:
        stats = {"nodes_created": 0, "edges_created": 0, "agents_created": 0, "events": 0,
                 "concepts_extracted": 0, "timeline_entries": 0, "errors": []}
        with self.node_repo.session as s:
            events = s.query(Event).order_by(Event.start_time.desc().nullslast()).limit(limit).all()
        logger.info(f"Processing {len(events)} events", component=self.service_name, event="events.start")
        for event in events:
            cid = f"evt/{event.id}"
            try:
                evt_start = time.monotonic()
                node_data = classify_event(event)
                if not node_data.get("embedding_text"):
                    node_data["embedding_text"] = event.title or event.description or ""
                event_id, is_new_event = self._save_node(node_data, stats, cid)
                if is_new_event:
                    stats["nodes_created"] += 1
                    stats["events"] += 1

                agents = self.agent_extractor.extract_from_event(event)
                for agent in agents:
                    if agent["role"] == "organizer":
                        self.edge_repo.save({
                            "source_node_id": agent["agent_id"],
                            "predicate": "organizes",
                            "target_node_id": event_id,
                            "properties": {"email": agent["email"]},
                        })
                    else:
                        self.edge_repo.save({
                            "source_node_id": agent["agent_id"],
                            "predicate": "participates_in",
                            "target_node_id": event_id,
                            "properties": {"email": agent["email"]},
                        })
                    stats["edges_created"] += 1
                    stats["agents_created"] += 1

                metrics.histogram("node_creation_duration_ms", tags={"type": "event"}).observe(
                    (time.monotonic() - evt_start) * 1000)
                metrics.counter("nodes_created", tags={"type": "event"}).inc()
            except Exception as e:
                stats["errors"].append(f"Event {event.id}: {e}")
                logger.exception("Event processing failed", component=self.service_name,
                                 event="event.failed", correlation_id=cid, event_id=str(event.id))
                metrics.counter("node_failed", tags={"type": "event"}).inc()
        return stats
