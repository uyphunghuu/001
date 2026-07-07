from sqlalchemy import text

from app.database.session import engine

INIT_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS gold_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(50) NOT NULL,
    subtype VARCHAR(50),
    name TEXT,
    summary TEXT,
    content TEXT,
    properties JSONB DEFAULT '{}'::jsonb,
    source_ref JSONB DEFAULT '{}'::jsonb,
    traits JSONB DEFAULT '[]'::jsonb,
    status VARCHAR(30) DEFAULT 'active',
    confidence FLOAT,
    importance INTEGER DEFAULT 2,
    effective_start TIMESTAMPTZ,
    effective_end TIMESTAMPTZ,
    embedding_text TEXT,
    embedding_updated_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS gold_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL REFERENCES gold_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES gold_nodes(id) ON DELETE CASCADE,
    predicate VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0,
    properties JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS gold_timeline (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES gold_nodes(id) ON DELETE CASCADE,
    field VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by UUID REFERENCES gold_nodes(id) ON DELETE SET NULL,
    changed_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb
);
"""

INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_type ON gold_nodes(type)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_type_subtype ON gold_nodes(type, subtype)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_source_ref ON gold_nodes USING gin(source_ref)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_properties ON gold_nodes USING gin(properties jsonb_path_ops)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_metadata ON gold_nodes USING gin(metadata jsonb_path_ops)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_traits ON gold_nodes USING gin(traits)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_effective ON gold_nodes(effective_start, effective_end)",
    "CREATE INDEX IF NOT EXISTS idx_gold_nodes_created ON gold_nodes(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_source ON gold_edges(source_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_target ON gold_edges(target_node_id)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_predicate ON gold_edges(predicate)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_source_predicate ON gold_edges(source_node_id, predicate)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_target_predicate ON gold_edges(target_node_id, predicate)",
    "CREATE INDEX IF NOT EXISTS idx_gold_edges_properties ON gold_edges USING gin(properties jsonb_path_ops)",
    "CREATE INDEX IF NOT EXISTS idx_gold_timeline_node ON gold_timeline(node_id, changed_at)",
    "CREATE INDEX IF NOT EXISTS idx_gold_timeline_field ON gold_timeline(field)",
    "CREATE INDEX IF NOT EXISTS idx_gold_timeline_changed ON gold_timeline(changed_at)",
]

EMBEDDING_COL_SQL = """
ALTER TABLE gold_nodes
ADD COLUMN IF NOT EXISTS embedding_vector vector(384)
"""

HNSW_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_gold_nodes_embedding
ON gold_nodes
USING hnsw (embedding_vector vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
"""


def init_database():
    with engine.begin() as conn:
        conn.execute(text(INIT_SQL))
        for sql in INDEXES_SQL:
            conn.execute(text(sql))
        conn.execute(text(EMBEDDING_COL_SQL))
        conn.execute(text(HNSW_INDEX_SQL))
