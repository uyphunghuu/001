"""Prometheus metrics collector for the entire AI Platform."""
import time
from functools import wraps
from typing import Optional

try:
    from prometheus_client import Counter, Histogram, Gauge, Summary, push_to_gateway, Registry
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False


class _NullMetric:
    def labels(self, **kwargs):
        return self
    def inc(self, amount=1):
        pass
    def observe(self, amount):
        pass
    def set(self, value):
        pass
    def dec(self, amount=1):
        pass


class MetricsCollector:
    """Collects and exposes Prometheus metrics with pushgateway fallback.

    Usage:
        metrics = MetricsCollector(namespace="ai_platform")
        metrics.counter("records_processed", "Total records", tags={"layer": "silver"})
        metrics.histogram("processing_time_ms", "Processing time", buckets=[10, 50, 100, 500, 1000, 5000])
        with metrics.timer("pipeline_duration_seconds", tags={"pipeline": "gold"}):
            run_pipeline()
    """

    def __init__(self, namespace: str = "ai_platform", pushgateway: Optional[str] = None):
        self.namespace = namespace
        self.pushgateway = pushgateway
        self._registry = Registry() if HAS_PROMETHEUS else None
        self._counters = {}
        self._histograms = {}
        self._gauges = {}
        self._summaries = {}

    def _metric_name(self, name: str) -> str:
        return f"{self.namespace}_{name}" if self.namespace else name

    def counter(self, name: str, description: str = "", tags: dict = None) -> "_NullMetric":
        full_name = self._metric_name(name)
        if not HAS_PROMETHEUS:
            return _NullMetric()
        if full_name not in self._counters:
            self._counters[full_name] = Counter(full_name, description, registry=self._registry)
        return self._counters[full_name]

    def histogram(self, name: str, description: str = "", buckets: list = None, tags: dict = None) -> "_NullMetric":
        full_name = self._metric_name(name)
        if not HAS_PROMETHEUS:
            return _NullMetric()
        if full_name not in self._histograms:
            self._histograms[full_name] = Histogram(
                full_name, description, buckets=buckets or Histogram.DEFAULT_BUCKETS,
                registry=self._registry,
            )
        return self._histograms[full_name]

    def gauge(self, name: str, description: str = "", tags: dict = None) -> "_NullMetric":
        full_name = self._metric_name(name)
        if not HAS_PROMETHEUS:
            return _NullMetric()
        if full_name not in self._gauges:
            self._gauges[full_name] = Gauge(full_name, description, registry=self._registry)
        return self._gauges[full_name]

    def summary(self, name: str, description: str = "") -> "_NullMetric":
        full_name = self._metric_name(name)
        if not HAS_PROMETHEUS:
            return _NullMetric()
        if full_name not in self._summaries:
            self._summaries[full_name] = Summary(full_name, description, registry=self._registry)
        return self._summaries[full_name]

    def timer(self, metric_name: str, tags: dict = None):
        """Context manager for timing code blocks.

        Usage:
            with metrics.timer("processing_time_ms"):
                process_item()
        """
        class _TimerContext:
            def __init__(self, collector, name, tags):
                self.collector = collector
                self.name = name
                self.tags = tags or {}
                self.start = None
            def __enter__(self):
                self.start = time.monotonic()
                return self
            def __exit__(self, *args):
                elapsed_ms = (time.monotonic() - self.start) * 1000
                self.collector.histogram(self.name, tags=self.tags).observe(elapsed_ms)
        return _TimerContext(self, metric_name, tags)

    def push(self, job_name: str = "ai_platform"):
        """Push metrics to pushgateway (for short-lived jobs)."""
        if HAS_PROMETHEUS and self.pushgateway and self._registry:
            try:
                push_to_gateway(self.pushgateway, job=job_name, registry=self._registry)
            except Exception:
                pass

    def track(self, name: str, tags: dict = None):
        """Decorator for timing function execution.

        Usage:
            @metrics.track("process_document")
            def process_document(doc):
                ...
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.monotonic()
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.monotonic() - start) * 1000
                    self.histogram(f"{name}_duration_ms", tags=tags).observe(elapsed_ms)
                    self.counter(f"{name}_total", tags={**(tags or {}), "status": "success"}).inc()
                    return result
                except Exception as e:
                    elapsed_ms = (time.monotonic() - start) * 1000
                    self.histogram(f"{name}_duration_ms", tags=tags).observe(elapsed_ms)
                    self.counter(f"{name}_total", tags={**(tags or {}), "status": "failed"}).inc()
                    raise
            return wrapper
        return decorator

    def get_registry(self):
        return self._registry
