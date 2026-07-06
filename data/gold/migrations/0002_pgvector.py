"""Migration 0002: Enable pgvector, add embedding column, migrate data."""
import json
import uuid

from sqlalchemy import text

from data.gold.repositories.base import BaseRepository


def upgrade():
    repo = BaseRepository()
    with repo.session as s:
        s.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        s.execute(text("""
            ALTER TABLE gold_nodes
            ADD COLUMN IF NOT EXISTS embedding_vector vector(384)
        """))
        s.execute(text("""
            UPDATE gold_nodes
            SET embedding_vector = (metadata->'embedding_vector')::text::vector
            WHERE metadata->'embedding_vector' IS NOT NULL
        """))
        s.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_gold_nodes_embedding
            ON gold_nodes
            USING hnsw (embedding_vector vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        s.commit()
    print("Migration 0002: pgvector enabled, column added, data migrated, index created")


def downgrade():
    repo = BaseRepository()
    with repo.session as s:
        s.execute(text("DROP INDEX IF EXISTS idx_gold_nodes_embedding"))
        s.execute(text("ALTER TABLE gold_nodes DROP COLUMN IF EXISTS embedding_vector"))
        s.commit()
    print("Migration 0002: rolled back")
