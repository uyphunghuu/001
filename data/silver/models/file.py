import uuid
from typing import Optional

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.silver.models.base import Base, TimestampMixin


class File(Base, TimestampMixin):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_object_id: Mapped[Optional[str]] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    extension: Mapped[Optional[str]] = mapped_column(String(20))
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    minio_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    parent_type: Mapped[Optional[str]] = mapped_column(String(50))
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending")
