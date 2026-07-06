"""Initial Silver Layer schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin"')

    # ── Documents ──
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("title", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("minio_bucket", sa.String(255)),
        sa.Column("minio_path", sa.String(500)),
        sa.Column("language", sa.String(10)),
        sa.Column("page_count", sa.Integer),
        sa.Column("author", sa.String(255)),
        sa.Column("created_time", sa.DateTime(timezone=True)),
        sa.Column("updated_time", sa.DateTime(timezone=True)),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("error_message", sa.Text),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Communications ──
    op.create_table(
        "communications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("thread_id", sa.String(500)),
        sa.Column("subject", sa.String(500)),
        sa.Column("body", sa.Text),
        sa.Column("sender_name", sa.String(255)),
        sa.Column("sender_email", sa.String(255)),
        sa.Column("recipients", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cc", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bcc", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("has_attachments", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("attachment_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("in_reply_to", sa.String(500)),
        sa.Column("message_id", sa.String(500)),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("error_message", sa.Text),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Events ──
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("title", sa.String(500)),
        sa.Column("description", sa.Text),
        sa.Column("location", sa.String(500)),
        sa.Column("organizer_name", sa.String(255)),
        sa.Column("organizer_email", sa.String(255)),
        sa.Column("attendees", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("start_time", sa.DateTime(timezone=True)),
        sa.Column("end_time", sa.DateTime(timezone=True)),
        sa.Column("is_all_day", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("recurrence", postgresql.JSONB),
        sa.Column("status", sa.String(50), server_default=sa.text("'confirmed'")),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("error_message", sa.Text),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Files ──
    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("extension", sa.String(20)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("minio_bucket", sa.String(255), nullable=False),
        sa.Column("minio_path", sa.String(500), nullable=False),
        sa.Column("parent_type", sa.String(50)),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Contacts ──
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("name", sa.String(255)),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("organization", sa.String(255)),
        sa.Column("role", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_unique_constraint("uq_contact_source_email", "contacts", ["source", "email"])

    # ── Knowledge Objects ──
    op.create_table(
        "knowledge_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50)),
        sa.Column("source_type", sa.String(50)),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("content", sa.Text),
        sa.Column("checksum", sa.String(64)),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.Column("metadata", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_json", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processing_status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Processing Logs ──
    op.create_table(
        "processing_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'running'")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("source_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("processed_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("skipped_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("errors", postgresql.JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("stats", postgresql.JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Ingestion Logs ──
    op.create_table(
        "ingestion_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_object_id", sa.String(500)),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("processing_logs.id")),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("checksum", sa.String(64)),
        sa.Column("processing_time_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # ── Metadata Registry ──
    op.create_table(
        "metadata_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("table_name", sa.String(50), nullable=False),
        sa.Column("jsonb_path", sa.String(500), nullable=False),
        sa.Column("field_name", sa.String(200), nullable=False),
        sa.Column("field_type", sa.String(50)),
        sa.Column("sample_value", sa.Text),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("occurrence_count", sa.Integer, server_default=sa.text("1")),
        sa.Column("is_indexed", sa.Boolean, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_unique_constraint("uq_metadata_registry_path", "metadata_registry", ["source", "table_name", "jsonb_path"])

    # ════════════════════════════════════════════════════════
    # INDEXES
    # ════════════════════════════════════════════════════════

    # Documents
    op.create_index("idx_documents_source", "documents", ["source"])
    op.create_index("idx_documents_source_type", "documents", ["source_type"])
    op.create_index("idx_documents_checksum", "documents", ["checksum"])
    op.create_index("idx_documents_processing_status", "documents", ["processing_status"])
    op.create_index("idx_documents_created_at", "documents", ["created_at"], postgresql_using="btree")
    op.create_index("idx_documents_metadata", "documents", ["metadata"], postgresql_using="gin")
    op.create_index("idx_documents_raw_json", "documents", ["raw_json"], postgresql_using="gin")
    op.execute("CREATE INDEX idx_documents_content_fts ON documents USING GIN(to_tsvector('simple', coalesce(content, '')))")
    op.execute("CREATE INDEX idx_documents_title_trgm ON documents USING GIN(title gin_trgm_ops)")
    op.create_index("idx_documents_source_object_id", "documents", ["source_object_id"])

    # Communications
    op.create_index("idx_communications_source", "communications", ["source"])
    op.create_index("idx_communications_source_type", "communications", ["source_type"])
    op.create_index("idx_communications_checksum", "communications", ["checksum"])
    op.create_index("idx_communications_thread_id", "communications", ["thread_id"])
    op.create_index("idx_communications_sender_email", "communications", ["sender_email"])
    op.create_index("idx_communications_received_at", "communications", ["received_at"], postgresql_using="btree")
    op.create_index("idx_communications_metadata", "communications", ["metadata"], postgresql_using="gin")
    op.create_index("idx_communications_raw_json", "communications", ["raw_json"], postgresql_using="gin")
    op.execute("CREATE INDEX idx_communications_body_fts ON communications USING GIN(to_tsvector('simple', coalesce(body, '')))")
    op.create_index("idx_communications_recipients", "communications", ["recipients"], postgresql_using="gin")

    # Events
    op.create_index("idx_events_source", "events", ["source"])
    op.create_index("idx_events_checksum", "events", ["checksum"])
    op.create_index("idx_events_start_time", "events", ["start_time"])
    op.create_index("idx_events_end_time", "events", ["end_time"])
    op.create_index("idx_events_metadata", "events", ["metadata"], postgresql_using="gin")
    op.create_index("idx_events_raw_json", "events", ["raw_json"], postgresql_using="gin")
    op.create_index("idx_events_attendees", "events", ["attendees"], postgresql_using="gin")

    # Files
    op.create_index("idx_files_checksum", "files", ["checksum"])
    op.create_index("idx_files_minio_path", "files", ["minio_path"])
    op.create_index("idx_files_parent", "files", ["parent_type", "parent_id"])
    op.create_index("idx_files_metadata", "files", ["metadata"], postgresql_using="gin")

    # Contacts
    op.create_index("idx_contacts_email", "contacts", ["email"])
    op.create_index("idx_contacts_organization", "contacts", ["organization"])
    op.create_index("idx_contacts_metadata", "contacts", ["metadata"], postgresql_using="gin")

    # Knowledge Objects
    op.create_index("idx_knowledge_objects_type", "knowledge_objects", ["object_type"])
    op.create_index("idx_knowledge_objects_checksum", "knowledge_objects", ["checksum"])
    op.create_index("idx_knowledge_objects_metadata", "knowledge_objects", ["metadata"], postgresql_using="gin")

    # Logs
    op.create_index("idx_processing_logs_status", "processing_logs", ["status"])
    op.create_index("idx_processing_logs_started_at", "processing_logs", ["started_at"])
    op.create_index("idx_ingestion_logs_source", "ingestion_logs", ["source", "source_type"])
    op.create_index("idx_ingestion_logs_pipeline", "ingestion_logs", ["pipeline_run_id"])
    op.create_index("idx_ingestion_logs_status", "ingestion_logs", ["status"])
    op.create_index("idx_ingestion_logs_checksum", "ingestion_logs", ["checksum"])

    # Metadata Registry
    op.create_index("idx_metadata_registry_source", "metadata_registry", ["source", "table_name"])
    op.create_index("idx_metadata_registry_field", "metadata_registry", ["field_name"])


def downgrade() -> None:
    op.drop_table("metadata_registry")
    op.drop_table("ingestion_logs")
    op.drop_table("processing_logs")
    op.drop_table("knowledge_objects")
    op.drop_table("contacts")
    op.drop_table("files")
    op.drop_table("events")
    op.drop_table("communications")
    op.drop_table("documents")
