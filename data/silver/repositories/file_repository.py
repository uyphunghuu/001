from data.silver.models.file import File
from data.silver.repositories.base import BaseRepository


class FileRepository(BaseRepository):
    def save(self, data: dict) -> str:
        existing = self.find_by_checksum(data.get("checksum", ""))
        if existing:
            return str(existing.id)
        f = File(**data)
        with self.session as s:
            s.add(f)
            s.commit()
            return str(f.id)

    def find_by_checksum(self, checksum: str) -> File | None:
        if not checksum:
            return None
        with self.session as s:
            return s.query(File).filter(File.checksum == checksum).first()

    def find_by_minio_path(self, bucket: str, path: str) -> File | None:
        with self.session as s:
            return s.query(File).filter(
                File.minio_bucket == bucket,
                File.minio_path == path,
            ).first()

    def list_by_parent(self, parent_type: str, parent_id: str):
        import uuid
        with self.session as s:
            return s.query(File).filter(
                File.parent_type == parent_type,
                File.parent_id == uuid.UUID(parent_id),
            ).all()
