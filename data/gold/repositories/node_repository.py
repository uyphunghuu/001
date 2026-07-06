import uuid
from typing import Optional

from sqlalchemy import and_, text
from sqlalchemy.orm import joinedload

from data.gold.models.node import Node
from data.gold.repositories.base import BaseRepository


class NodeRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_by_source_ref(data.get("source_ref", {}))
        if existing:
            return str(existing.id)
        node = Node(**data)
        with self.session as s:
            s.add(node)
            s.commit()
            return str(node.id)

    def find_by_source_ref(self, source_ref: dict) -> Optional[Node]:
        if not source_ref or not source_ref.get("id"):
            return None
        table = source_ref.get("table", "")
        sid = source_ref.get("id", "")
        with self.session as s:
            return s.query(Node).filter(
                Node.source_ref["table"].astext == table,
                Node.source_ref["id"].astext == sid,
            ).first()

    def find_agent_by_email(self, email: str) -> Optional[Node]:
        if not email:
            return None
        with self.session as s:
            return s.query(Node).filter(
                Node.type == "agent",
                Node.properties["email"].astext == email,
            ).first()

    def find_by_id(self, node_id: str) -> Optional[Node]:
        with self.session as s:
            return s.query(Node).filter(Node.id == uuid.UUID(node_id)).first()

    def list_by_type(self, type_: str, subtype: str | None = None, limit: int = 100):
        with self.session as s:
            q = s.query(Node).filter(Node.type == type_)
            if subtype:
                q = q.filter(Node.subtype == subtype)
            return q.order_by(Node.created_at.desc()).limit(limit).all()

    def count_by_type(self, type_: str | None = None) -> dict:
        with self.session as s:
            if type_:
                total = s.query(Node).filter(Node.type == type_).count()
                return {type_: total}
            result = s.execute(text("""
                SELECT type, COUNT(*) as cnt
                FROM gold_nodes
                GROUP BY type
                ORDER BY cnt DESC
            """)).fetchall()
            return {row[0]: row[1] for row in result}

    def count(self) -> int:
        with self.session as s:
            return s.query(Node).count()

    def search_by_property(self, key: str, value: str, type_: str | None = None, limit: int = 50):
        with self.session as s:
            q = s.query(Node).filter(Node.properties[key].astext == value)
            if type_:
                q = q.filter(Node.type == type_)
            return q.limit(limit).all()

    def list_by_type_and_subtype(self, type_: str, subtype: str, limit: int = 100):
        with self.session as s:
            return s.query(Node).filter(
                Node.type == type_, Node.subtype == subtype
            ).order_by(Node.created_at.desc()).limit(limit).all()
