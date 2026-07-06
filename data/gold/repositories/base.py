"""Base repository with connection pool monitoring."""
import time
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from data.silver.config import get_settings
from data.observability import metrics, logger


class BaseRepository:
    def __init__(self, connection_string: str | None = None):
        settings = get_settings()
        cs = connection_string or settings.pg_connection_string
        self._engine = create_engine(
            cs, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=3600
        )
        self._session_factory = sessionmaker(bind=self._engine)

    @property
    def session(self) -> Session:
        start = time.monotonic()
        session = self._session_factory()
        elapsed_ms = (time.monotonic() - start) * 1000
        metrics.histogram("gold_db_session_create_ms").observe(elapsed_ms)
        try:
            pool = self._engine.pool
            metrics.gauge("gold_db_pool_checkedout").set(pool.checkedout())
        except Exception:
            pass
        return session

    def init_schema(self):
        from data.gold.models.base import Base
        start = time.monotonic()
        Base.metadata.create_all(self._engine, checkfirst=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("Schema initialized", component="gold_base_repo", event="schema.init",
                     duration_ms=elapsed_ms)

    def execute_raw(self, sql: str, params: dict | None = None) -> Any:
        start = time.monotonic()
        with self.session as s:
            result = s.execute(text(sql), params or {})
            elapsed_ms = (time.monotonic() - start) * 1000
            metrics.histogram("gold_db_query_duration_ms").observe(elapsed_ms)
            if result.returns_rows:
                return result.fetchall()
            return None

    def health_check(self) -> dict:
        """Check database connectivity and return health status."""
        start = time.monotonic()
        try:
            with self.session as s:
                s.execute(text("SELECT 1"))
                latency_ms = (time.monotonic() - start) * 1000
                vec_check = s.execute(text(
                    "SELECT 1 FROM pg_catalog.pg_extension WHERE extname = 'vector'"
                )).fetchone()
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "has_pgvector": vec_check is not None,
                }
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("Gold DB health check failed", component="gold_base_repo",
                         event="health_check.failed", latency_ms=elapsed_ms, error=str(e))
            return {"status": "unhealthy", "error": str(e), "latency_ms": elapsed_ms}
