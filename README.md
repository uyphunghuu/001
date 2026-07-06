# Project 001 — AI Operating System

> A personal AI OS that ingests your emails, documents, and calendar events into a knowledge graph, then lets you query everything through a conversational AI agent.

---

## Architecture

```
Bronze (MinIO)
    └─► Silver (PostgreSQL)
            └─► Gold / Knowledge Graph (PostgreSQL + pgvector)
                        └─► RAG + AI Agent (FastAPI + LLM)
```

| Layer | Storage | Description |
|-------|---------|-------------|
| **Bronze** | MinIO | Raw data from Gmail API (JSON + attachments) |
| **Silver** | PostgreSQL 16 | Cleaned & normalized — documents, communications, events |
| **Gold** | PostgreSQL + pgvector | Knowledge graph — nodes, edges, timeline, embeddings |
| **AI MVP** | FastAPI + OpenAI-compatible LLM | Chat with your knowledge base |

---

## Tech Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.11 |
| API Framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 16 + pgvector |
| Object Storage | MinIO |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (384-dim) |
| LLM | OpenAI-compatible (Groq / OpenAI / local) |
| Observability | Prometheus + Grafana + OpenLineage |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
ai-platform/
├── app/                    # FastAPI application
│   ├── agent/              # LLM agent + prompt builder
│   ├── api/                # Chat endpoint
│   ├── config/             # Settings (loaded from .env)
│   ├── database/           # SQLAlchemy session
│   ├── retriever/          # Gold layer retriever
│   └── schemas/            # Pydantic schemas
├── data/
│   ├── bronze/             # MinIO local volume (gitignored)
│   ├── silver/             # Silver pipeline (models, repos, services)
│   ├── gold/               # Gold pipeline (graph, embeddings, timeline)
│   ├── observability/      # Prometheus metrics, lineage, logging
│   └── contracts/          # Data contracts (YAML)
├── services/
│   ├── rag/                # Chunker + hybrid retriever
│   └── agent/              # Agent tracer + observability
├── infrastructure/
│   ├── docker/             # Core stack (PostgreSQL + MinIO)
│   └── monitoring/         # Prometheus + Grafana stack
├── scripts/                # Gmail ingestion, utilities
├── run_silver.py           # Bronze → Silver pipeline runner
├── run_gold.py             # Silver → Gold pipeline runner
└── .env.example            # Environment variables template
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker Desktop
- Git

### 1. Clone & setup environment

```bash
git clone https://github.com/uyphunghuu/001.git
cd 001

# Copy env template
cp .env.example .env
# Edit .env and fill in your values
```

### 2. Start infrastructure

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

Services started:
- PostgreSQL 16 + pgvector → `localhost:5433`
- MinIO → `localhost:9000` (console: `localhost:9001`)

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Run pipelines

```bash
# Health check
python run_silver.py --health

# Bronze → Silver (process emails from MinIO)
python run_silver.py --source minio

# Silver → Gold (build knowledge graph)
python run_gold.py

# Validate embeddings
python run_gold.py --validate-embeddings
```

### 5. Start AI API

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API available at:
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Chat: `POST http://localhost:8000/chat`

### 6. Chat with your knowledge base

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What meetings do I have this week?"}'
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# PostgreSQL
PG_HOST=localhost
PG_PORT=5433
PG_USER=platform
PG_PASSWORD=platform123
PG_DB=ai_platform

# LLM Provider (Groq / OpenAI / local)
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

---

## Data Pipeline Commands

```bash
# Silver pipeline
python run_silver.py --health                        # Health check
python run_silver.py --source minio                  # Ingest from MinIO
python run_silver.py --source local                  # Ingest from local files

# Gold pipeline
python run_gold.py                                   # Build knowledge graph
python run_gold.py --show                            # Stats + quality metrics
python run_gold.py --semantic "query"                # Semantic vector search
python run_gold.py --query "keyword"                 # Full-text search
python run_gold.py --validate-embeddings             # Validate embeddings
python run_gold.py --lineage-stats                   # Lineage event stats

# Monitoring stack
docker compose -f infrastructure/monitoring/docker-compose.yml up -d
```

---

## Roadmap

- [x] Bronze Layer — Gmail API → MinIO
- [x] Silver Layer — Normalized PostgreSQL schema
- [x] Gold Layer — Knowledge graph with pgvector embeddings
- [x] AI MVP — RAG chat API (FastAPI + LLM)
- [x] Observability — Prometheus + Grafana + OpenLineage
- [ ] CI/CD — GitHub Actions
- [ ] Docker Build & Registry
- [ ] Calendar & Slack data sources
- [ ] Production deployment
- [ ] Agent with tool-use (web search, calendar write)
- [ ] Multi-user support

---

## License

MIT License — see [LICENSE](LICENSE) for details.
