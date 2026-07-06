from data.silver.models.document import Document
from data.silver.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_by_checksum(data.get("checksum", ""))
        if existing:
            return str(existing.id)
        doc = Document(**data)
        with self.session as s:
            s.add(doc)
            s.commit()
            return str(doc.id)

    def find_by_checksum(self, checksum: str) -> Document | None:
        if not checksum:
            return None
        with self.session as s:
            return s.query(Document).filter(Document.checksum == checksum).first()

    def find_by_id(self, doc_id: str) -> Document | None:
        import uuid
        with self.session as s:
            return s.query(Document).filter(Document.id == uuid.UUID(doc_id)).first()

    def list_recent(self, limit: int = 50, offset: int = 0):
        with self.session as s:
            return s.query(Document).order_by(Document.created_at.desc()).offset(offset).limit(limit).all()

    def count(self) -> int:
        with self.session as s:
            return s.query(Document).count()

    def update_status(self, doc_id: str, status: str, error: str | None = None):
        import uuid
        from datetime import datetime, timezone
        with self.session as s:
            doc = s.query(Document).filter(Document.id == uuid.UUID(doc_id)).first()
            if doc:
                doc.processing_status = status
                if error:
                    doc.error_message = error
                if status in ("completed", "failed"):
                    doc.processed_at = datetime.now(timezone.utc)
                s.commit()
