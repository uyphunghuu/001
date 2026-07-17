# Observability Platform — Project 001

## Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                      FastAPI App                           │
                          │  ┌──────────────────────────────────────────────────────┐  │
                          │  │  OpenTelemetry SDK (auto + manual instrumentation)   │  │
                          │  │  • FastAPIInstrumentor  • RequestsInstrumentor       │  │
                          │  │  • Custom spans: LLM, Retriever, Pipeline            │  │
                          │  └──────────────┬───────────────────────────────────────┘  │
                          │  ┌──────────────────────────────────────────────────────┐  │
                          │  │  Prometheus Client (metrics.py)                      │  │
                          │  │  • http_requests_total/duration/active               │  │
                          │  │  • llm_*, retriever_*, pipeline_* metrics            │  │
                          │  └──────────────┬───────────────────────────────────────┘  │
                          │  ┌──────────────────────────────────────────────────────┐  │
                          │  │  JSON Structured Logging (logging.py)                │  │
                          │  │  • trace_id • span_id • request_id • timestamp       │  │
                          │  └──────────────┬───────────────────────────────────────┘  │
                          │  ┌──────────────────────────────────────────────────────┐  │
                          │  │  Health Endpoints                                   │  │
                          │  │  /health  /ready  /live  /startup                   │  │
                          │  └──────────────────────────────────────────────────────┘  │
                          └──────────┬──────────────┬──────────────────┬──────────────┘
                                     │              │                  │
                          OTLP (traces)        /metrics          JSON logs
                                     │              │                  │
                          ┌──────────┴──────────┐   │                  │
                          │  OpenTelemetry       │   │                  │
                          │  Collector           │   │                  │
                          │  (otel-collector)    │   │                  │
                          └──────────┬──────────┘   │                  │
                                     │               │                  │
                          ┌──────────┴──────────┐   │                  │
                          │  Tempo              │   │                  │
                          │  (Distributed Traces)│  │                  │
                          └──────────┬──────────┘   │                  │
                                     │               │                  │
                          ┌──────────┴──────────┐   │   ┌──────────────┴──────────────┐
                          │  Prometheus          │◄──┘   │  Loki                      │
                          │  (Metrics + Alerts)  │       │  (Log Aggregation)         │
                          └──────────┬──────────┘       └──────────────┬──────────────┘
                                     │                                 │
                          ┌──────────┴─────────────────────────────────┴──────────────┐
                          │                      Grafana                              │
                          │  9 Dashboards: Executive, Infra, App, DB, AI, Pipeline,  │
                          │  Knowledge Graph, Cost, Security                          │
                          └───────────────────────────────────────────────────────────┘
```

## 4 Pillars of Observability

### 1. Metrics (Prometheus)
| Target | Port | Exporter | Description |
|--------|------|----------|-------------|
| fastapi_app | 8000 | Built-in | API request count, latency, active requests, LLM/retriever/pipeline metrics |
| node | 9100 | node_exporter | CPU, RAM, disk, network, load, swap |
| postgresql | 9187 | postgres_exporter | Connections, queries, locks, cache hit ratio, deadlocks |
| cadvisor | 8088 | cAdvisor | Container resource usage, restart count, network IO |
| minio | 9000 | Built-in | Health check (up/down) |
| loki | 3100 | Built-in | Log ingestion rate, query performance |
| tempo | 3200 | Built-in | Trace ingestion, span metrics |
| otel-collector | 8889 | Built-in | Collector metrics, pipeline status |
| pushgateway | 9091 | Pushgateway | Short-lived job metrics (pipeline runs) |

### 2. Logs (Loki + Promtail)
- **Format**: JSON structured logging
- **Fields**: `timestamp`, `level`, `message`, `trace_id`, `span_id`, `request_id`, `method`, `path`, `status`, `duration_ms`
- **Collection**: Promtail reads from `logs/` directory + Docker container logs
- **Storage**: Loki with 168h retention

### 3. Distributed Tracing (OpenTelemetry + Tempo)
- **Instrumentation**: Automatic (FastAPIInstrumentor) + Manual (LLM, Retriever, Pipeline spans)
- **Flow**: App → OTLP → OTel Collector → Tempo
- **Context propagation**: trace_id flows through all spans, logs, and metrics
- **Query**: Grafana Explore with TraceQL

### 4. Visualization (Grafana)
| Dashboard | Focus | Key Panels |
|-----------|-------|------------|
| Executive | High-level KPIs | Uptime, RPS, error rate, p99 latency, pipeline health |
| Infrastructure | System resources | CPU, RAM, disk, swap, containers, network IO |
| Application | API performance | Request rate, latency p50/p95/p99, status codes, endpoints |
| Database | PostgreSQL | Connections, queries, locks, cache hit, table sizes |
| AI | LLM + Retriever | Token usage, latency, cost, hallucination, retrieval quality |
| Pipeline | Data pipelines | Throughput by layer, success rate, processing time |
| Knowledge Graph | Graph analytics | Nodes, edges, growth, communities, entities |
| Cost | FinOps | LLM cost $/h, monthly projection, token cost efficiency |
| Security | Threat monitoring | Failed logins, 403s, rate limits, prompt injections |

## Alert Rules (24 rules)

| Alert | Condition | Severity |
|-------|-----------|----------|
| APIHighErrorRate | 5xx rate > 5% | critical |
| APIHighLatency | p95 > 5s | warning |
| APIHighP99Latency | p99 > 10s | critical |
| APIEndpointDown | up == 0 | critical |
| CPUHighUsage | CPU > 90% | critical |
| MemoryHighUsage | Memory > 85% | warning |
| DiskHighUsage | Disk free < 10% | critical |
| DiskFillRate | Will fill in 24h | warning |
| ContainerRestarting | Restart detected | warning |
| DatabaseDown | pg_up == 0 | critical |
| DatabaseHighConnections | > 50 | warning |
| DatabaseConnectionExhausted | > 80% | critical |
| DatabaseDeadlocks | > 0 | critical |
| DatabaseCacheHitLow | < 95% | warning |
| MinIODown | up == 0 | critical |
| LLMHighErrorRate | Error rate > 10% | warning |
| LLMHighLatency | p95 > 30s | warning |
| LLMTimeout | Timeouts detected | critical |
| HighTokenCost | > $10/h | warning |
| RetrieverHighLatency | p95 > 3s | warning |
| RetrieverEmptyResults | Empty rate > 0 | warning |
| PipelineHighFailureRate | Failure > 10% | critical |
| PipelineStalled | No run in 24h | warning |
| FailedLoginAttempts | > 10/s | critical |

## Health Endpoints

| Endpoint | Purpose | Return |
|----------|---------|--------|
| `GET /health` | Full component health | `{"status":"ok", "components": {"database": {"status":"ok"}}}` |
| `GET /ready` | Readiness check | `{"status":"ready"}` or 503 |
| `GET /live` | Liveness check | `{"status":"alive"}` |
| `GET /startup` | Startup status | `{"status":"started", "elapsed_seconds": 5.2}` |

## Project Structure

```
monitoring/
├── docker-compose.observability.yml   # Complete observability stack
├── README.md
├── app/                               # App instrumentation
│   ├── __init__.py
│   ├── metrics.py                     # Prometheus metrics + middleware
│   ├── logging.py                     # JSON structured logging
│   ├── opentelemetry.py               # OTel setup + tracing decorators
│   └── health.py                      # /health, /ready, /live, /startup
├── prometheus/
│   ├── prometheus.yml                 # Scrape configs (9 targets)
│   └── alerts/
│       └── alerts.yml                 # 24 alert rules
├── grafana/
│   ├── datasources/
│   │   └── datasources.yml           # Prometheus + Loki + Tempo
│   └── dashboards/
│       ├── executive.json
│       ├── infrastructure.json
│       ├── application.json
│       ├── database.json
│       ├── ai.json
│       ├── pipeline.json
│       ├── knowledge_graph.json
│       ├── cost.json
│       └── security.json
├── loki/
│   └── loki-config.yml               # Log aggregation
├── tempo/
│   └── tempo-config.yml              # Distributed tracing
├── otel/
│   └── otel-collector-config.yml     # OTel pipeline
└── promtail/
    └── promtail-config.yml           # Log shipping
```

## Quick Start

### Prerequisites
- Python 3.11+ with dependencies installed
- Docker + Docker Compose

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the app
```bash
# Without tracing (for development)
OTEL_ENABLED=false python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# With tracing (for production)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Start monitoring stack
```bash
docker compose -f monitoring/docker-compose.observability.yml up -d
```

### 4. Verify
```bash
# Check targets
open http://localhost:9090/targets

# Open Grafana
open http://localhost:3000
# admin / admin

# Check app health
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## Metrics Reference

### API Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint, status | Request latency |
| `http_requests_active` | Gauge | — | Concurrent requests |

### LLM Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `llm_requests_total` | Counter | status | LLM API calls |
| `llm_request_duration_seconds` | Histogram | — | LLM response time |
| `llm_tokens_total` | Counter | type (input/output) | Token consumption |
| `llm_cost_usd_total` | Counter | — | Running cost in USD |

### Retriever Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `retriever_duration_seconds` | Histogram | strategy | Search latency |
| `retriever_documents_total` | Counter | strategy | Documents returned |
| `retriever_empty_total` | Counter | strategy | Empty result count |

### Pipeline Metrics
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `pipeline_processed_total` | Counter | layer, status | Documents processed |
| `pipeline_duration_seconds` | Histogram | layer, stage | Processing time |
| `pipeline_last_success_timestamp_seconds` | Gauge | layer | Last successful run |

## Grafana Cloud (Push Mode)

Không muốn self-host Grafana? Push metrics/logs/traces lên Grafana Cloud free tier.

### Setup (2 phút)

1. **Đăng ký**: [grafana.com](https://grafana.com) → Sign up free
2. **Lấy credentials**:
   - [grafana.com/org/access-policies](https://grafana.com/org/access-policies) → Create API Key
   - Chép **Instance ID** (số) và **API Key**
3. **Chạy setup script**:
   ```bash
   # Nhập Instance ID + API Key
   monitoring/setup_grafana_cloud.bat
   
   # Hoặc tự tạo file
   notepad monitoring/.env.grafana-cloud
   ```
4. **Khởi động push mode**:
   ```bash
   docker compose -f monitoring/docker-compose.grafana-cloud.yml up -d
   ```
5. **Upload dashboards**:
   ```bash
   python monitoring/upload_dashboards.py
   ```
6. **Mở**: `https://<instance_id>.grafana.net`

### Kiến trúc Push Mode

```
App (localhost:8000)
  ├─ /metrics ──► Prometheus ──remote_write──► Grafana Cloud (Prometheus)
  ├─ OTLP ──────► OTel Collector ────────────► Grafana Cloud (Tempo)
  └─ logs ──────► (JSON file → Promtail) ───► Grafana Cloud (Loki)

Bạn chỉ cần: Prometheus + Pushgateway + OTel Collector chạy local.
Grafana, Loki, Tempo chạy trên cloud → xem ở app.grafana.net
```

## Access URLs

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |
| Pushgateway | http://localhost:9091 |
| App | http://localhost:8000 |
| App Metrics | http://localhost:8000/metrics |
| App Health | http://localhost:8000/health |
| App Ready | http://localhost:8000/ready |
| App Live | http://localhost:8000/live |

## Tracing with OpenTelemetry

### Automatic instrumentation
Every FastAPI request is automatically traced with:
- Span per HTTP request (method, path, status)
- Span per HTTP client request (via RequestsInstrumentor)
- trace_id propagated in response headers

### Manual instrumentation
```python
from monitoring.app.opentelemetry import get_tracer, trace_llm_call, trace_retrieval

tracer = get_tracer(app)

@trace_llm_call(tracer, model="gpt-4", input_tokens=100, output_tokens=50)
def call_llm(prompt):
    # Your LLM call here
    pass

@trace_retrieval(tracer, strategy="hybrid")
def search(query):
    # Your retriever call here
    pass
```

### Correlation
- **trace_id** appears in: spans, logs, and metrics exemplars
- **request_id** appears in: logs and response headers
- **Grafana Tempo → Loki**: Click a span to see related logs
- **Grafana Loki → Tempo**: Click a log to see related trace

## Extending

### Adding a new metric
```python
from monitoring.app.metrics import Counter
my_counter = Counter("my_metric_total", "Description", labelnames=["label1"])
my_counter.labels(label1="value").inc()
```

### Adding a new dashboard
1. Open Grafana → New Dashboard
2. Add panels → Query Prometheus/Loki/Tempo
3. Export JSON → save to `monitoring/grafana/dashboards/`

### Adding a new target to Prometheus
```yaml
- job_name: "new_service"
  static_configs:
    - targets: ["host.docker.internal:PORT"]
      labels:
        component: my_component
        service: ai-platform
```
