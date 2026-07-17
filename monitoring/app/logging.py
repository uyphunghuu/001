import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_JSON_LOGS = os.getenv("JSON_LOGS", "true").lower() == "true"


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            log_entry["trace_id"] = hex(span_context.trace_id)[2:]
            log_entry["span_id"] = hex(span_context.span_id)[2:]

        request_id = request_id_var.get()
        if request_id:
            log_entry["request_id"] = request_id

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        extra = getattr(record, "extra", {})
        if extra:
            log_entry.update(extra)

        return json.dumps(log_entry, default=str)


def setup_logging() -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ai_platform")
    logger.setLevel(_LOG_LEVEL)
    logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    if _JSON_LOGS:
        stdout_handler.setFormatter(JSONFormatter())
    else:
        stdout_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        ))
    logger.addHandler(stdout_handler)

    file_handler = logging.FileHandler(_LOG_DIR / "ai-platform.log", encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    return logger


logger = setup_logging()


def get_request_id() -> str:
    return request_id_var.get()


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        token = request_id_var.set(request_id)
        start = time.monotonic()
        method = request.method
        path = request.url.path

        logger.info("Request started", extra={
            "method": method,
            "path": path,
            "client": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        })

        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info("Request completed", extra={
                "method": method,
                "path": path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            })
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error("Request failed", extra={
                "method": method,
                "path": path,
                "duration_ms": duration_ms,
                "error": str(exc),
            }, exc_info=True)
            raise
        finally:
            request_id_var.reset(token)
