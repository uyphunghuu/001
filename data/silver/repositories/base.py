"""Base repository with connection pool monitoring.

OBSERVABILITY ADDED (2026-07-03):
    - Connection pool size monitoring (gauge)
    - Query timing histogram
    - Connection health check
    - Pool overflow tracking

Why this matters:
    - Connection pool exhaustion is silent — queries block, pipeline slows
    - Without pool monitoring, you don't know you need more connections until it's too late
    - Query timing helps identify slow queries before they become problems
"""
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
            cs,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        self._session_factory = sessionmaker(bind=self._engine)
        self._pool_metrics_initialized = False

    def _init_pool_metrics(self):
        if self._pool_metrics_initialized:
            return
        try:
            pool = self._engine.pool
            metrics.gauge("db_pool_size").set(pool.size())
            metrics.gauge("db_pool_overflow").set(pool.max_overflow)
            self._pool_metrics_initialized = True
        except Exception:
            pass

    @property
    def session(self) -> Session:
        self._init_pool_metrics()
        start = time.monotonic()
        session = self._session_factory()
        elapsed_ms = (time.monotonic() - start) * 1000
        metrics.histogram("db_session_create_ms").observe(elapsed_ms)

        # Track pool usage
        try:
            pool = self._engine.pool
            metrics.gauge("db_pool_checkedin").set(pool.checkedin())
            metrics.gauge("db_pool_checkedout").set(pool.checkedout())
            metrics.gauge("db_pool_overflow_used").set(pool.overflow())
        except Exception:
            pass

        return session

    def init_schema(self):
        from data.silver.models.base import Base
        start = time.monotonic()
        Base.metadata.create_all(self._engine, checkfirst=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info("Schema initialized", component="base_repository", event="schema.init",
                     duration_ms=elapsed_ms)

    def execute_raw(self, sql: str, params: dict | None = None) -> Any:
        start = time.monotonic()
        with self.session as s:
            result = s.execute(text(sql), params or {})
            elapsed_ms = (time.monotonic() - start) * 1000
            metrics.histogram("db_query_duration_ms").observe(elapsed_ms)
            if result.returns_rows:
                rows = result.fetchall()
                metrics.histogram("db_query_row_count").observe(len(rows))
                return rows
            return None

    def is_checksum_duplicate(self, table: str, checksum: str) -> bool:
        if not checksum:
            return False
        start = time.monotonic()
        rows = self.execute_raw(
            f"SELECT 1 FROM {table} WHERE checksum = :cs LIMIT 1",
            {"cs": checksum},
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        is_dup = len(rows) > 0 if rows else False
        if is_dup:
            metrics.counter("checksum_duplicates", tags={"table": table}).inc()
        return is_dup

    def health_check(self) -> dict:
        """Check database connectivity and return health status."""
        start = time.monotonic()
        try:
            with self.session as s:
                s.execute(text("SELECT 1"))
                latency_ms = (time.monotonic() - start) * 1000
                # Test pgvector extension
                vec_check = s.execute(text("SELECT 1 FROM pg_catalog.pg_extension WHERE extname = 'vector'")).fetchone()
                has_vector = vec_check is not None
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "has_pgvector": has_vector,
                    "pool_size": self._engine.pool.size() if hasattr(self._engine.pool, 'size') else None,
                    "pool_checkedout": self._engine.pool.checkedout() if hasattr(self._engine.pool, 'checkedout') else None,
                }
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("Database health check failed", component="base_repository",
                         event="health_check.failed", latency_ms=elapsed_ms, error=str(e))
            return {"status": "unhealthy", "error": str(e), "latency_ms": elapsed_ms}
