-- ============================================================
-- Silver Layer - AI Platform
-- PostgreSQL 17 Initialization
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ============================================================
-- CORE ENTITIES
-- ============================================================

-- Documents: docx, pdf, txt, csv, xlsx, google docs, notion pages
CREATE TABLE IF NOT EXISTS documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    title           TEXT,
    content         TEXT,
    checksum        VARCHAR(64) NOT NULL,
    mime_type       VARCHAR(100),
    size_bytes      BIGINT,
    minio_bucket    VARCHAR(255),
    minio_path      VARCHAR(500),
    language        VARCHAR(10),
    page_count      INT,
    author          VARCHAR(255),
    created_time    TIMESTAMPTZ,
    updated_time    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    processing_status VARCHAR(20) DEFAULT 'pending',
    error_message   TEXT,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Communications: email, slack, teams, chat
CREATE TABLE IF NOT EXISTS communications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    thread_id       VARCHAR(500),
    subject         VARCHAR(500),
    body            TEXT,
    sender_name     VARCHAR(255),
    sender_email    VARCHAR(255),
    recipients      JSONB DEFAULT '[]'::jsonb,
    cc              JSONB DEFAULT '[]'::jsonb,
    bcc             JSONB DEFAULT '[]'::jsonb,
    received_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    has_attachments BOOLEAN DEFAULT FALSE,
    attachment_count INT DEFAULT 0,
    in_reply_to     VARCHAR(500),
    message_id      VARCHAR(500),
    checksum        VARCHAR(64) NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    processing_status VARCHAR(20) DEFAULT 'pending',
    error_message   TEXT,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Events: calendar, meetings, deadlines
CREATE TABLE IF NOT EXISTS events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    title           VARCHAR(500),
    description     TEXT,
    location        VARCHAR(500),
    organizer_name  VARCHAR(255),
    organizer_email VARCHAR(255),
    attendees       JSONB DEFAULT '[]'::jsonb,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    is_all_day      BOOLEAN DEFAULT FALSE,
    recurrence      JSONB,
    status          VARCHAR(50) DEFAULT 'confirmed',
    checksum        VARCHAR(64) NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    processing_status VARCHAR(20) DEFAULT 'pending',
    error_message   TEXT,
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Files: all files in MinIO
CREATE TABLE IF NOT EXISTS files (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    filename        VARCHAR(500) NOT NULL,
    extension       VARCHAR(20),
    mime_type       VARCHAR(100),
    size_bytes      BIGINT,
    checksum        VARCHAR(64) NOT NULL,
    minio_bucket    VARCHAR(255) NOT NULL,
    minio_path      VARCHAR(500) NOT NULL,
    parent_type     VARCHAR(50),
    parent_id       UUID,
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    processing_status VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Contacts: people, organizations
CREATE TABLE IF NOT EXISTS contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    name            VARCHAR(255),
    email           VARCHAR(255),
    phone           VARCHAR(50),
    organization    VARCHAR(255),
    role            VARCHAR(255),
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, email)
);

-- Knowledge Objects: future Gold/KB layer
CREATE TABLE IF NOT EXISTS knowledge_objects (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50),
    source_type     VARCHAR(50),
    object_type     VARCHAR(100) NOT NULL,
    title           TEXT,
    content         TEXT,
    checksum        VARCHAR(64),
    source_object_id VARCHAR(500),
    parent_id       UUID,
    metadata        JSONB DEFAULT '{}'::jsonb,
    raw_json        JSONB DEFAULT '{}'::jsonb,
    processing_status VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- LOGGING & MONITORING
-- ============================================================

-- Processing Logs: pipeline run tracking
CREATE TABLE IF NOT EXISTS processing_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pipeline_name   VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    source_count    INT DEFAULT 0,
    processed_count INT DEFAULT 0,
    failed_count    INT DEFAULT 0,
    skipped_count   INT DEFAULT 0,
    errors          JSONB DEFAULT '[]'::jsonb,
    stats           JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ingestion Logs: per-record tracking
CREATE TABLE IF NOT EXISTS ingestion_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,
    source_object_id VARCHAR(500),
    pipeline_run_id UUID REFERENCES processing_logs(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    checksum        VARCHAR(64),
    processing_time_ms INT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Metadata Registry: auto-learn JSONB fields
CREATE TABLE IF NOT EXISTS metadata_registry (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source          VARCHAR(50) NOT NULL,
    table_name      VARCHAR(50) NOT NULL,
    jsonb_path      VARCHAR(500) NOT NULL,
    field_name      VARCHAR(200) NOT NULL,
    field_type      VARCHAR(50),
    sample_value    TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrence_count INT DEFAULT 1,
    is_indexed      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, table_name, jsonb_path)
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Documents
CREATE INDEX idx_documents_source ON documents(source);
CREATE INDEX idx_documents_source_type ON documents(source_type);
CREATE INDEX idx_documents_checksum ON documents(checksum);
CREATE INDEX idx_documents_processing_status ON documents(processing_status);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_documents_raw_json ON documents USING GIN(raw_json);
CREATE INDEX idx_documents_content_fts ON documents USING GIN(to_tsvector('simple', coalesce(content, '')));
CREATE INDEX idx_documents_title_trgm ON documents USING GIN(title gin_trgm_ops);
CREATE INDEX idx_documents_source_object_id ON documents(source_object_id);

-- Communications
CREATE INDEX idx_communications_source ON communications(source);
CREATE INDEX idx_communications_source_type ON communications(source_type);
CREATE INDEX idx_communications_checksum ON communications(checksum);
CREATE INDEX idx_communications_thread_id ON communications(thread_id);
CREATE INDEX idx_communications_sender_email ON communications(sender_email);
CREATE INDEX idx_communications_received_at ON communications(received_at DESC);
CREATE INDEX idx_communications_metadata ON communications USING GIN(metadata);
CREATE INDEX idx_communications_raw_json ON communications USING GIN(raw_json);
CREATE INDEX idx_communications_body_fts ON communications USING GIN(to_tsvector('simple', coalesce(body, '')));
CREATE INDEX idx_communications_recipients ON communications USING GIN(recipients);

-- Events
CREATE INDEX idx_events_source ON events(source);
CREATE INDEX idx_events_checksum ON events(checksum);
CREATE INDEX idx_events_start_time ON events(start_time);
CREATE INDEX idx_events_end_time ON events(end_time);
CREATE INDEX idx_events_metadata ON events USING GIN(metadata);
CREATE INDEX idx_events_raw_json ON events USING GIN(raw_json);
CREATE INDEX idx_events_attendees ON events USING GIN(attendees);

-- Files
CREATE INDEX idx_files_checksum ON files(checksum);
CREATE INDEX idx_files_minio_path ON files(minio_path);
CREATE INDEX idx_files_parent ON files(parent_type, parent_id);
CREATE INDEX idx_files_metadata ON files USING GIN(metadata);

-- Contacts
CREATE INDEX idx_contacts_email ON contacts(email);
CREATE INDEX idx_contacts_organization ON contacts(organization);
CREATE INDEX idx_contacts_metadata ON contacts USING GIN(metadata);

-- Knowledge Objects
CREATE INDEX idx_knowledge_objects_type ON knowledge_objects(object_type);
CREATE INDEX idx_knowledge_objects_checksum ON knowledge_objects(checksum);
CREATE INDEX idx_knowledge_objects_metadata ON knowledge_objects USING GIN(metadata);

-- Logs
CREATE INDEX idx_processing_logs_status ON processing_logs(status);
CREATE INDEX idx_processing_logs_started_at ON processing_logs(started_at DESC);
CREATE INDEX idx_ingestion_logs_source ON ingestion_logs(source, source_type);
CREATE INDEX idx_ingestion_logs_pipeline ON ingestion_logs(pipeline_run_id);
CREATE INDEX idx_ingestion_logs_status ON ingestion_logs(status);
CREATE INDEX idx_ingestion_logs_checksum ON ingestion_logs(checksum);

-- Metadata Registry
CREATE INDEX idx_metadata_registry_source ON metadata_registry(source, table_name);
CREATE INDEX idx_metadata_registry_field ON metadata_registry(field_name);
