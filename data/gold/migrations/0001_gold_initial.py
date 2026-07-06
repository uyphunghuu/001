"""Gold Layer initial schema.

Revision ID: 0001
Revises: None
Create Date: 2026-07-01

Tables:
  - gold_nodes: universal knowledge entities
  - gold_edges: relationships between nodes (SPO triples)
  - gold_timeline: state change history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0001"
down_revision = None
branch_labels = ("gold",)
depends_on = None


def upgrade():
    op.create_table(
        "gold_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("subtype", sa.String(50), nullable=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("properties", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_ref", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("traits", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(30), nullable=True, server_default="active"),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("importance", sa.Integer, nullable=True, server_default=sa.text("2")),
        sa.Column("effective_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding_text", sa.Text, nullable=True),
        sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("idx_gold_nodes_type", "gold_nodes", ["type"])
    op.create_index("idx_gold_nodes_type_subtype", "gold_nodes", ["type", "subtype"])
    op.create_index("idx_gold_nodes_source_ref", "gold_nodes", ["source_ref"], postgresql_using="gin")
    op.create_index("idx_gold_nodes_properties", "gold_nodes", ["properties"], postgresql_using="gin", postgresql_ops={"properties": "jsonb_path_ops"})
    op.create_index("idx_gold_nodes_metadata", "gold_nodes", ["metadata"], postgresql_using="gin", postgresql_ops={"metadata": "jsonb_path_ops"})
    op.create_index("idx_gold_nodes_traits", "gold_nodes", ["traits"], postgresql_using="gin")
    op.create_index("idx_gold_nodes_effective", "gold_nodes", ["effective_start", "effective_end"])
    op.create_index("idx_gold_nodes_created", "gold_nodes", ["created_at"])

    op.create_table(
        "gold_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_node_id", UUID(as_uuid=True), sa.ForeignKey("gold_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", UUID(as_uuid=True), sa.ForeignKey("gold_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("weight", sa.Float, nullable=True, server_default=sa.text("1.0")),
        sa.Column("properties", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_index("idx_gold_edges_source", "gold_edges", ["source_node_id"])
    op.create_index("idx_gold_edges_target", "gold_edges", ["target_node_id"])
    op.create_index("idx_gold_edges_predicate", "gold_edges", ["predicate"])
    op.create_index("idx_gold_edges_source_predicate", "gold_edges", ["source_node_id", "predicate"])
    op.create_index("idx_gold_edges_target_predicate", "gold_edges", ["target_node_id", "predicate"])
    op.create_index("idx_gold_edges_properties", "gold_edges", ["properties"], postgresql_using="gin", postgresql_ops={"properties": "jsonb_path_ops"})

    op.create_table(
        "gold_timeline",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("node_id", UUID(as_uuid=True), sa.ForeignKey("gold_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column("changed_by", UUID(as_uuid=True), sa.ForeignKey("gold_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_index("idx_gold_timeline_node", "gold_timeline", ["node_id", "changed_at"])
    op.create_index("idx_gold_timeline_field", "gold_timeline", ["field"])
    op.create_index("idx_gold_timeline_changed", "gold_timeline", ["changed_at"])


def downgrade():
    op.drop_table("gold_timeline")
    op.drop_table("gold_edges")
    op.drop_table("gold_nodes")
