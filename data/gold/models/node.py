import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Float, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.gold.models.base import Base, TimestampMixin


try:
    from sqlalchemy.dialects.postgresql import VECTOR
except ImportError:
    VECTOR = Text


class Node(Base, TimestampMixin):
    __tablename__ = "gold_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subtype: Mapped[Optional[str]] = mapped_column(String(50))
    name: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)

    properties: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    source_ref: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    traits: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    status: Mapped[Optional[str]] = mapped_column(String(30), default="active")
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    importance: Mapped[Optional[int]] = mapped_column(Integer, default=2)

    effective_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    effective_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    embedding_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    embedding_vector: Mapped[Optional[object]] = mapped_column(VECTOR(384), nullable=True)

    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
