import time
from functools import wraps

from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "endpoint", "status"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

http_requests_active = Gauge(
    "http_requests_active",
    "Active HTTP requests",
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    labelnames=["status"],
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    labelnames=[],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens",
    labelnames=["type"],
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD",
    labelnames=[],
)

retriever_duration_seconds = Histogram(
    "retriever_duration_seconds",
    "Retriever query duration in seconds",
    labelnames=["strategy"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0],
)

retriever_documents_total = Counter(
    "retriever_documents_total",
    "Total documents retrieved",
    labelnames=["strategy"],
)

retriever_empty_total = Counter(
    "retriever_empty_total",
    "Empty retrieval results",
    labelnames=["strategy"],
)

pipeline_processed_total = Counter(
    "pipeline_processed_total",
    "Total documents processed by pipeline",
    labelnames=["layer", "status"],
)

pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "Pipeline processing duration in seconds",
    labelnames=["layer", "stage"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

pipeline_last_success_timestamp_seconds = Gauge(
    "pipeline_last_success_timestamp_seconds",
    "Timestamp of last successful pipeline run",
    labelnames=["layer"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        http_requests_active.inc()
        start = time.monotonic()

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration = time.monotonic() - start
            endpoint = self._normalize_path(path)
            http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
            http_request_duration_seconds.labels(method=method, endpoint=endpoint, status=status).observe(duration)
            http_requests_active.dec()

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        if path.startswith("/static/"):
            return "/static/*"
        return path


def metrics_endpoint(request: Request) -> Response:
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


def track_llm_request(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
            llm_requests_total.labels(status="success").inc()
            return result
        except Exception:
            llm_requests_total.labels(status="error").inc()
            raise
        finally:
            duration = time.monotonic() - start
            llm_request_duration_seconds.observe(duration)
    return wrapper


def track_llm_tokens(input_tokens: int, output_tokens: int, cost_usd: float = 0.0):
    llm_tokens_total.labels(type="input").inc(input_tokens)
    llm_tokens_total.labels(type="output").inc(output_tokens)
    if cost_usd > 0:
        llm_cost_usd_total.inc(cost_usd)


def track_retrieval(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        strategy = kwargs.get("strategy", "hybrid")
        start = time.monotonic()
        try:
            result = func(*args, **kwargs)
            doc_count = len(result.chunks) if hasattr(result, "chunks") else 0
            retriever_documents_total.labels(strategy=strategy).inc(doc_count)
            if doc_count == 0:
                retriever_empty_total.labels(strategy=strategy).inc()
            return result
        except Exception:
            retriever_empty_total.labels(strategy=strategy).inc()
            raise
        finally:
            duration = time.monotonic() - start
            retriever_duration_seconds.labels(strategy=strategy).observe(duration)
    return wrapper
