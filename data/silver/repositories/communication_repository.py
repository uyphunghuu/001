from data.silver.models.communication import Communication
from data.silver.repositories.base import BaseRepository


class CommunicationRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_by_checksum(data.get("checksum", ""))
        if existing:
            return str(existing.id)
        comm = Communication(**data)
        with self.session as s:
            s.add(comm)
            s.commit()
            return str(comm.id)

    def find_by_checksum(self, checksum: str) -> Communication | None:
        if not checksum:
            return None
        with self.session as s:
            return s.query(Communication).filter(Communication.checksum == checksum).first()

    def find_by_thread(self, thread_id: str, limit: int = 100):
        with self.session as s:
            return s.query(Communication).filter(
                Communication.thread_id == thread_id
            ).order_by(Communication.received_at.asc()).limit(limit).all()

    def list_recent(self, limit: int = 50):
        with self.session as s:
            return s.query(Communication).order_by(Communication.received_at.desc()).limit(limit).all()
