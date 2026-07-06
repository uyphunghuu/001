CREATE EXTENSION IF NOT EXISTS vector;

-- Silver Layer Schema
-- Email records with full enrichment
CREATE TABLE IF NOT EXISTS silver_records (
    email_id        TEXT PRIMARY KEY,
    subject         TEXT,
    sender_name     TEXT,
    sender_email    TEXT,
    received_at     TIMESTAMPTZ,
    content_type    TEXT,
    language        TEXT,
    attachment_count INTEGER DEFAULT 0,
    total_text_length INTEGER DEFAULT 0,
    keyword_count   INTEGER DEFAULT 0,
    metadata        JSONB DEFAULT '{}',
    processed_at    TIMESTAMPTZ DEFAULT NOW(),
    pipeline_run_id INTEGER
);

-- Individual attachment details
CREATE TABLE IF NOT EXISTS silver_attachments (
    id                  SERIAL PRIMARY KEY,
    email_id            TEXT REFERENCES silver_records(email_id),
    filename            TEXT,
    normalized_filename TEXT,
    file_category       TEXT,
    size_kb             REAL DEFAULT 0,
    language            TEXT,
    content_hash        TEXT,
    text_length         INTEGER DEFAULT 0,
    text_word_count     INTEGER DEFAULT 0,
    content_type        TEXT,
    keywords            TEXT[] DEFAULT '{}',
    cleaning_ops        TEXT[] DEFAULT '{}',
    processed_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Extracted and normalized text content
CREATE TABLE IF NOT EXISTS silver_texts (
    id              SERIAL PRIMARY KEY,
    email_id        TEXT REFERENCES silver_records(email_id),
    filename        TEXT,
    normalized_text TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Text chunks for downstream processing
CREATE TABLE IF NOT EXISTS silver_chunks (
    id              SERIAL PRIMARY KEY,
    email_id        TEXT REFERENCES silver_records(email_id),
    chunk_index     INTEGER,
    text            TEXT,
    length          INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Pipeline run history
CREATE TABLE IF NOT EXISTS silver_processing (
    id          SERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ DEFAULT NOW(),
    status      TEXT,
    processed   INTEGER DEFAULT 0,
    failed      INTEGER DEFAULT 0,
    errors      JSONB DEFAULT '[]'
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_attachments_email_id ON silver_attachments(email_id);
CREATE INDEX IF NOT EXISTS idx_texts_email_id ON silver_texts(email_id);
CREATE INDEX IF NOT EXISTS idx_chunks_email_id ON silver_chunks(email_id);
CREATE INDEX IF NOT EXISTS idx_records_content_type ON silver_records(content_type);
CREATE INDEX IF NOT EXISTS idx_records_language ON silver_records(language);
