import uuid
from typing import Optional

from sqlalchemy import and_, or_

from data.gold.models.edge import Edge
from data.gold.repositories.base import BaseRepository


class EdgeRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_existing(
            data.get("source_node_id", ""),
            data.get("predicate", ""),
            data.get("target_node_id", ""),
        )
        if existing:
            return str(existing.id)
        edge = Edge(**data)
        with self.session as s:
            s.add(edge)
            s.commit()
            return str(edge.id)

    def find_existing(self, source_id: str, predicate: str, target_id: str) -> Optional[Edge]:
        with self.session as s:
            return s.query(Edge).filter(
                Edge.source_node_id == uuid.UUID(source_id),
                Edge.predicate == predicate,
                Edge.target_node_id == uuid.UUID(target_id),
            ).first()

    def list_by_node(self, node_id: str, direction: str = "both", predicate: str | None = None, limit: int = 100):
        with self.session as s:
            nid = uuid.UUID(node_id)
            if direction == "outgoing":
                q = s.query(Edge).filter(Edge.source_node_id == nid)
            elif direction == "incoming":
                q = s.query(Edge).filter(Edge.target_node_id == nid)
            else:
                q = s.query(Edge).filter(
                    or_(Edge.source_node_id == nid, Edge.target_node_id == nid)
                )
            if predicate:
                q = q.filter(Edge.predicate == predicate)
            return q.limit(limit).all()

    def count(self) -> int:
        with self.session as s:
            return s.query(Edge).count()

    def count_by_predicate(self) -> dict:
        from sqlalchemy import text
        with self.session as s:
            rows = s.execute(text("""
                SELECT predicate, COUNT(*) as cnt
                FROM gold_edges
                GROUP BY predicate
                ORDER BY cnt DESC
            """)).fetchall()
            return {row[0]: row[1] for row in rows}
