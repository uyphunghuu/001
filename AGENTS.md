# Project 001 — Data Platform

## Architecture
Bronze (MinIO) → Silver (PostgreSQL) → Gold (PostgreSQL / Knowledge Graph) → AI Agent

## Stack
- MinIO (localhost:9000/9001) — Bronze Layer
- PostgreSQL 16 + pgvector (localhost:5433, db=ai_platform, user=platform, pass=platform123)
- Python 3.11 + SQLAlchemy 2.0 + Alembic + FastAPI + sentence-transformers
- pgAdmin (localhost:5050)
- **Prometheus + Grafana** — Metrics & Dashboards (monitoring stack)
- **OpenLineage / Marquez** — Data Lineage (planned)
- **Great Expectations** — Data Contracts (planned)

## Current State (2026-07-03)

### Bronze
- Bucket `gmail-raw`: 20+ objects (email.json + DOCX attachments from Gmail API)
- `scripts/gmail_to_minio.py` — fetch Gmail → MinIO (full message JSON + attachments)

### Silver
- 9 tables: documents, communications, events, files, contacts, knowledge_objects, processing_logs, ingestion_logs, metadata_registry
- 2 documents + 21 communications processed

### Gold (Graph-Centric model)
- 3 tables: gold_nodes, gold_edges, gold_timeline
- **36 nodes**: 21 communications, 13 agents, 2 documents
- **360 edges**: 178 related_to, 140 involves, 21 sends, 21 to
- **23 timeline entries** (from effective_start)
- **Embeddings**: all nodes have embedding_text + embedding_vector (384-d, all-MiniLM-L6-v2) stored in native pgvector column
- **Traits**: 20 nodes have auto-extracted concepts (projects, topics, entities)
- Built-in dedup by source_ref (table + id)
- HNSW index on embedding_vector (vector_cosine_ops, m=16, ef_construction=64)

## Data Observability & Lineage (Added 2026-07-03)

### Core Modules (`data/observability/`)
| File | Purpose |
|------|---------|
| `metrics.py` | Prometheus metrics collector (counters, histograms, gauges, summaries) |
| `lineage.py` | OpenLineage integration (Bronze→Silver→Gold→RAG→Agent tracking) |
| `logging.py` | Structured JSON logging (stdout + file, correlation_id, component, event) |
| `contract.py` | Data contract validator (Great Expectations integration, blocking on critical) |
| `schema.py` | Schema validator (Pandera-like, field types, enums, patterns, constraints) |

### Data Contracts (`data/contracts/`)
| File | Contract | Severity |
|------|----------|----------|
| `bronze_to_silver.yaml` | Email JSON schema, headers, base64 validation | Critical |
| `silver_to_gold.yaml` | Node type, source_ref, embedding dimension | Critical |
| `gold_to_rag.yaml` | Chunk schema, parent_node_id, embedding dim | Critical |

### Fixed Critical Bugs
- **embedding_generator.py**: Vector now stored in VECTOR(384) column instead of JSONB metadata
- **relationship_discovery.py**: Added max_pairs_per_group (100) to prevent O(n²) explosion
- **concept_extractor.py**: Added pluggable extractors, more topics, entity extraction (email, URL, phone, date)

### Instrumented Pipelines
- **Silver Pipeline** (`data/silver/services/silver_pipeline.py`): Per-source timing, contract checks, schema validation, lineage events, cleaner step timing
- **Gold Pipeline** (`data/gold/pipeline/gold_pipeline.py`): Per-node timing, phase timing, contract enforcement, schema validation

### RAG Observability (`services/rag/`)
| File | Purpose |
|------|---------|
| `chunker.py` | Recursive text splitter with orphan/duplicate detection |
| `retriever.py` | Hybrid vector+keyword retriever with p95 latency, diversity scoring |
| `observability.py` | Chunk quality, embedding drift (PSI/MMD), corpus freshness, vector DB health |

### Agent Observability (`services/agent/`)
| File | Purpose |
|------|---------|
| `tracer.py` | Full execution trace: tool calls, memory, planning steps, provenance |
| `observability.py` | Agent metrics, cost tracking, loop detection, recovery tracking |
| `hallucination_detector.py` | Hallucination scoring: attribution, entity grounding, contradiction |

### Monitoring Infrastructure (`infrastructure/monitoring/`)
| File | Purpose |
|------|---------|
| `docker-compose.yml` | Prometheus + Pushgateway + Grafana + pg_exporter + node_exporter |
| `prometheus/prometheus.yml` | Scrape configs for all pipeline services |
| `prometheus/alerts/platform_alerts.yml` | Alert rules (pipeline failure, stale data, drift, cost) |
| `grafana/dashboards/ai_platform_overview.json` | Overview dashboard (pipeline rates, latency, quality, cost) |
| `grafana/datasources/prometheus.yml` | Grafana datasource provisioning |

## Key Files (Complete)

### Data Pipeline
- `data/silver/` — Silver pipeline (models, repositories, pipeline, migrations)
- `data/gold/` — Gold pipeline (models, repositories, pipeline, migrations, design)
  - `pipeline/concept_extractor.py` — Rule-based concept/topic/project/entity extraction
  - `pipeline/embedding_generator.py` — Sentence-transformer embeddings (384-d, VECTOR column)
  - `pipeline/timeline_builder.py` — Timeline entries from node effective dates
  - `pipeline/relationship_discovery.py` — Implicit edges with O(n²) protection
- `data/observability/` — Core observability module
- `data/contracts/` — Data contract YAML files
- `scripts/gmail_to_minio.py` — Gmail → MinIO (Bronze ingestion)
- `scripts/install_pgvector.py` — Install pgvector extension + migrate embeddings
- `run_silver.py` — Run Silver pipeline with --health, --verbose
- `run_gold.py` — Run Gold pipeline with --health, --validate-embeddings, --lineage-stats

### AI Services
- `services/rag/chunker.py` — RAG chunking service with observability
- `services/rag/retriever.py` — RAG retriever (vector + keyword + hybrid)
- `services/rag/observability.py` — RAG metrics (drift, freshness, quality)
- `services/agent/tracer.py` — Agent execution tracer
- `services/agent/observability.py` — Agent metrics + hallucination detector
- `api/` — FastAPI (documents CRUD)

### Infrastructure
- `infrastructure/docker/` — Core stack (PostgreSQL + MinIO + init)
- `infrastructure/monitoring/` — Observability stack (Prometheus + Grafana)

## Commands
```bash
# Pipeline
python scripts/gmail_to_minio.py --query "in:inbox after:2026/06/30"  # Gmail → MinIO
python run_silver.py --source minio                                     # Bronze → Silver
python run_silver.py --health                                           # Health check
python run_gold.py                                                      # Silver → Gold
python run_gold.py --health                                             # Gold health check
python run_gold.py --validate-embeddings                                # Validate embeddings
python run_gold.py --show                                               # Stats + quality
python run_gold.py --detail                                             # All nodes + edges
python run_gold.py --query "keyword"                                    # Full-text search
python run_gold.py --semantic "query"                                   # Semantic vector search
python run_gold.py --lineage-stats                                      # Lineage events

# Monitoring
docker-compose -f infrastructure/monitoring/docker-compose.yml up -d    # Start monitoring stack
```

## Next Potential Steps
1. Build AI Agent that queries Gold via graph traversal + semantic search
2. Add Calendar/Slack data to Bronze
3. Re-process old DOCX (08:30 spacing bug) — delete from documents, re-run Silver
4. **Enable Great Expectations**: Install `great_expectations`, run `great_expectations init` in `data/contracts/`
5. **Enable OpenLineage**: Install Marquez (`docker-compose`), point `OPENLINEAGE_URL` env var
6. **Deploy Prometheus + Grafana**: Run `docker-compose -f infrastructure/monitoring/docker-compose.yml up -d`
7. **Integrate piipod/veriff/other data sources** into Bronze layer
8. **Build production agent** using `services/agent/tracer.py` + `services/rag/retriever.py`

## Notes
- Punctuation bug (08:30 → 08: 30) was fixed in cleaner but old DOCX data in Silver still has spaces (dedup'd before fix).
- Gold uses Graph-Centric model (Phuong an C): universal nodes + edges.
- pgvector installed via `pgvector/pgvector:pg16` Docker image. HNSW index created on embedding_vector.
- `all-MiniLM-L6-v2` model (384-dim) used for embeddings via sentence-transformers.
- Metrics use Prometheus Pushgateway for short-lived pipeline jobs.
- Lineage falls back to JSONL file (`data/observability/lineage_events.jsonl`) when no OpenLineage backend.
