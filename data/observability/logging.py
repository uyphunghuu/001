"""Structured JSON logging for the AI Platform.

Why:
    - Raw print() statements are not searchable, not aggregatable
    - JSON logs can be ingested by ELK/Loki/Grafana for full-text search
    - Structured fields enable metric extraction, alert correlation, and debugging

How:
    - All pipeline steps emit structured logs via this module
    - Logs go to stdout (for container env) and optionally to file
    - Each log entry has: timestamp, level, service, component, event, correlation_id, duration_ms

File locations for integration:
    - Every pipeline file should use logger.info/warning/error instead of print()
    - Integration point in: silver_pipeline.py, gold_pipeline.py, all readers, all repositories
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional


class StructuredLog:
    """A single structured log entry."""

    def __init__(self, level: str, message: str, **kwargs):
        self.entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "logger": kwargs.pop("logger", "ai_platform"),
            "component": kwargs.pop("component", ""),
            "event": kwargs.pop("event", ""),
            "correlation_id": kwargs.pop("correlation_id", ""),
            "duration_ms": kwargs.pop("duration_ms", None),
            "message": message,
            "data": kwargs,
        }

    def to_json(self) -> str:
        return json.dumps(self.entry, default=str, ensure_ascii=False)


class StructuredLogger:
    """Logger that outputs structured JSON to stdout.

    Usage:
        logger = StructuredLogger(service="silver_pipeline")
        logger.info("Document processed", component="processor", doc_id=doc_id, duration_ms=150)
        logger.warning("Cleaner issue", component="cleaner", field="punctuation", chars_affected=5)
        logger.error("Reader failed", component="docx_reader", filename=fname, error=str(e))
    """

    def __init__(self, service: str = "ai_platform", level: str = "INFO", output_file: Optional[str] = None):
        self.service = service
        self.level = getattr(logging, level.upper(), logging.INFO)
        self.output_file = output_file
        self._file_handle = None
        if output_file:
            try:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                self._file_handle = open(output_file, "a", encoding="utf-8")
            except Exception:
                self._file_handle = None

    def _log(self, level: str, message: str, **kwargs):
        log = StructuredLog(level, message, logger=self.service, **kwargs)
        entry = log.to_json()
        # stdout for container env (use buffer for Windows Unicode support)
        try:
            sys.stdout.write(entry + "\n")
        except UnicodeEncodeError:
            sys.stdout.buffer.write((entry + "\n").encode("utf-8"))
        sys.stdout.flush()
        # file output for local dev
        if self._file_handle:
            try:
                self._file_handle.write(entry + "\n")
                self._file_handle.flush()
            except Exception:
                pass

    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log("CRITICAL", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._log("DEBUG", message, **kwargs)

    def exception(self, message: str, **kwargs):
        kwargs["traceback"] = traceback.format_exc()
        self._log("ERROR", message, **kwargs)

    def close(self):
        if self._file_handle:
            self._file_handle.close()
