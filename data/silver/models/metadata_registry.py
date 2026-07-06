import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from data.silver.models.base import Base


class MetadataRegistry(Base):
    __tablename__ = "metadata_registry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    jsonb_path: Mapped[str] = mapped_column(String(500), nullable=False)
    field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[Optional[str]] = mapped_column(String(50))
    sample_value: Mapped[Optional[str]] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(), server_default=func.now())
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    is_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("source", "table_name", "jsonb_path", name="uq_metadata_registry_path"),
    )
