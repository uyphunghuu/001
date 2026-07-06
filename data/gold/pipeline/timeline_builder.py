"""Build gold_timeline entries from gold_nodes."""
from datetime import datetime, timezone

from data.gold.models.node import Node
from data.gold.models.timeline import Timeline


def build_timeline(node_id: str, node_data: dict) -> list[dict]:
    entries = []
    effective_start = node_data.get("effective_start")
    effective_end = node_data.get("effective_end")
    now = datetime.now(timezone.utc)

    if effective_start:
        entries.append({
            "node_id": node_id,
            "field": "effective_start",
            "new_value": effective_start.isoformat() if hasattr(effective_start, "isoformat") else str(effective_start),
            "changed_at": effective_start if hasattr(effective_start, "tzname") else now,
            "metadata_": {"reason": "node_created", "type": node_data.get("type"), "subtype": node_data.get("subtype")},
        })

    if effective_end:
        entries.append({
            "node_id": node_id,
            "field": "effective_end",
            "new_value": effective_end.isoformat() if hasattr(effective_end, "isoformat") else str(effective_end),
            "changed_at": now,
            "metadata_": {"reason": "node_created", "type": node_data.get("type")},
        })

    return entries


class TimelineBuilder:
    def __init__(self, repo):
        self.repo = repo

    def populate_all(self) -> dict:
        from data.gold.repositories.base import BaseRepository
        repo = BaseRepository()
        stats = {"entries_created": 0, "nodes_processed": 0, "errors": []}

        with repo.session as s:
            nodes = s.query(Node).all()
            for node in nodes:
                try:
                    entries = build_timeline(str(node.id), {
                        "effective_start": node.effective_start,
                        "effective_end": node.effective_end,
                        "type": node.type,
                        "subtype": node.subtype,
                    })
                    for entry in entries:
                        existing = s.query(Timeline).filter(
                            Timeline.node_id == node.id,
                            Timeline.field == entry["field"],
                        ).first()
                        if not existing:
                            tl = Timeline(**entry)
                            s.add(tl)
                            stats["entries_created"] += 1
                    stats["nodes_processed"] += 1
                except Exception as e:
                    stats["errors"].append(f"Node {node.id}: {e}")
            s.commit()
        return stats
