from datetime import datetime

from data.silver.models.event import Event
from data.silver.repositories.base import BaseRepository


class EventRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_by_checksum(data.get("checksum", ""))
        if existing:
            return str(existing.id)
        event = Event(**data)
        with self.session as s:
            s.add(event)
            s.commit()
            return str(event.id)

    def find_by_checksum(self, checksum: str) -> Event | None:
        if not checksum:
            return None
        with self.session as s:
            return s.query(Event).filter(Event.checksum == checksum).first()

    def find_upcoming(self, from_time: datetime | None = None, limit: int = 50):
        from datetime import timezone
        now = from_time or datetime.now(timezone.utc)
        with self.session as s:
            return s.query(Event).filter(
                Event.start_time >= now
            ).order_by(Event.start_time.asc()).limit(limit).all()

    def list_recent(self, limit: int = 50):
        with self.session as s:
            return s.query(Event).order_by(Event.start_time.desc()).limit(limit).all()
