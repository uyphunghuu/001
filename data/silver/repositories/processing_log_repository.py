from datetime import datetime, timezone
from typing import Optional

from data.silver.models.processing_log import ProcessingLog
from data.silver.repositories.base import BaseRepository


class ProcessingLogRepository(BaseRepository):
    def start_run(self, pipeline_name: str = "silver_pipeline") -> str:
        log = ProcessingLog(pipeline_name=pipeline_name)
        with self.session as s:
            s.add(log)
            s.commit()
            return str(log.id)

    def finish_run(
        self,
        run_id: str,
        status: str,
        source_count: int = 0,
        processed_count: int = 0,
        failed_count: int = 0,
        skipped_count: int = 0,
        errors: Optional[list] = None,
        stats: Optional[dict] = None,
    ):
        import uuid
        with self.session as s:
            log = s.query(ProcessingLog).filter(ProcessingLog.id == uuid.UUID(run_id)).first()
            if log:
                log.status = status
                log.completed_at = datetime.now(timezone.utc)
                log.source_count = source_count
                log.processed_count = processed_count
                log.failed_count = failed_count
                log.skipped_count = skipped_count
                log.errors = errors or []
                log.stats = stats or {}
                s.commit()

    def list_runs(self, limit: int = 20):
        with self.session as s:
            return s.query(ProcessingLog).order_by(ProcessingLog.started_at.desc()).limit(limit).all()
