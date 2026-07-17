import os
from typing import Optional

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.semconv.resource import ResourceAttributes
from fastapi import FastAPI

OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ai-platform")
OTEL_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() == "true"


def setup_opentelemetry(app: FastAPI) -> None:
    if not OTEL_ENABLED:
        return

    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: OTEL_SERVICE_NAME,
        ResourceAttributes.SERVICE_VERSION: "0.1.0",
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: os.getenv("ENVIRONMENT", "production"),
    })

    provider = TracerProvider(
        resource=resource,
        sampler=ParentBasedTraceIdRatio(0.5),
    )
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/traces"),
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_processor = BatchLogRecordProcessor(
        OTLPSpanExporter(endpoint=f"{OTEL_ENDPOINT}/v1/logs"),
    )
    logger_provider.add_log_record_processor(logger_processor)
    set_logger_provider(logger_provider)

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    RequestsInstrumentor().instrument()

    app.state.tracer = trace.get_tracer(OTEL_SERVICE_NAME)

    app.add_event_handler("shutdown", lambda: _shutdown(provider, logger_provider))


def get_tracer(app: Optional[FastAPI] = None):
    if app and hasattr(app.state, "tracer"):
        return app.state.tracer
    return trace.get_tracer(OTEL_SERVICE_NAME)


def _shutdown(provider: TracerProvider, logger_provider: LoggerProvider) -> None:
    provider.shutdown()
    logger_provider.shutdown()


def trace_llm_call(tracer, model: str, input_tokens: int = 0, output_tokens: int = 0):
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span("llm.call") as span:
                span.set_attribute("llm.model", model)
                span.set_attribute("llm.input_tokens", input_tokens)
                span.set_attribute("llm.output_tokens", output_tokens)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("llm.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("llm.status", "error")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def trace_retrieval(tracer, strategy: str = "hybrid"):
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span("retriever.query") as span:
                span.set_attribute("retriever.strategy", strategy)
                try:
                    result = func(*args, **kwargs)
                    doc_count = len(result.chunks) if hasattr(result, "chunks") else 0
                    span.set_attribute("retriever.documents_count", doc_count)
                    span.set_attribute("retriever.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("retriever.status", "error")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def trace_pipeline_step(tracer, layer: str, stage: str):
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"pipeline.{layer}.{stage}") as span:
                span.set_attribute("pipeline.layer", layer)
                span.set_attribute("pipeline.stage", stage)
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("pipeline.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("pipeline.status", "error")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator
