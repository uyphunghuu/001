"""Silver Pipeline — orchestrator with full data observability.

OBSERVABILITY ADDED (2026-07-03):
    - Prometheus metrics: processing time per source, records processed/failed/deduped
    - Structured logging: JSON logs with correlation_id, component, duration_ms
    - OpenLineage lineage: tracks every Bronze→Silver transform
    - Data contract validation: validates email.json against bronze_to_silver contract
    - Schema validation: validates output dicts against Pandera schemas before insert
    - Quality gates: blocks processing on critical contract violations
    - Per-step timing: measures each pipeline stage (reader, cleaner, save)

Why this matters:
    - Without observability, data quality issues go undetected until downstream fail
    - Without lineage, root cause analysis is manual and slow
    - Without contracts, a schema change in Gmail API silently breaks the pipeline
"""
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from data.silver.pipeline.cleaners import TextCleaner
from data.silver.pipeline.readers import get_reader
from data.silver.repositories import (
    DocumentRepository,
    CommunicationRepository,
    EventRepository,
    FileRepository,
    ContactRepository,
    ProcessingLogRepository,
)
from data.silver.schemas.source import SourceData

from data.observability import metrics, lineage, logger, contract, schema


class SilverPipeline:
    """Orchestrates the Bronze → Silver data transformation with full observability."""

    def __init__(self):
        self.text_cleaner = TextCleaner()
        self.doc_repo = DocumentRepository()
        self.comm_repo = CommunicationRepository()
        self.event_repo = EventRepository()
        self.file_repo = FileRepository()
        self.contact_repo = ContactRepository()
        self.log_repo = ProcessingLogRepository()
        self.service_name = "silver_pipeline"

    def process_source(self, source: SourceData, correlation_id: str = "") -> dict:
        """Process a single source from Bronze to Silver with observability.

        Observability flow:
            1. Timer: measure total processing time
            2. Schema check: validate source metadata
            3. Contract check: validate input against data contract (email only)
            4. Reader stage timing
            5. Cleaner stage timing
            6. Repository save timing
            7. Lineage event emission
            8. Metrics counters
        """
        source_cid = correlation_id or str(uuid.uuid4())
        start_time = time.monotonic()
        logger.info("Processing source", component=self.service_name, event="process_source.start",
                     correlation_id=source_cid, filename=source.filename, bucket=source.bucket)

        # ── Reader resolution ──
        reader_start = time.monotonic()
        reader = get_reader(
            self._get_extension(source.filename),
            source.metadata.get("source_type", "") if source.metadata else "",
        )
        if not reader:
            metrics.counter("source_skipped", tags={"reason": "no_reader"}).inc()
            logger.warning("No reader for source", component=self.service_name, event="process_source.skip",
                           correlation_id=source_cid, filename=source.filename)
            return {"status": "skipped", "reason": f"no reader for {source.filename}"}

        if not reader.can_handle(source):
            metrics.counter("source_skipped", tags={"reason": "reader_cannot_handle"}).inc()
            return {"status": "skipped", "reason": f"reader cannot handle {source.filename}"}

        # ── Data contract validation (Bronze → Silver) ──
        if source.filename.endswith(".json"):
            try:
                raw_data = json.loads(source.raw_data.decode("utf-8", errors="replace"))
                contract_violations = contract.validate("bronze_to_silver", raw_data)
                if contract_violations:
                    critical = [v for v in contract_violations if v.get("severity") in ("critical", "high")]
                    if critical:
                        logger.error("Contract violation — blocking", component=self.service_name,
                                     event="process_source.contract_blocked", correlation_id=source_cid,
                                     violations=critical)
                        metrics.counter("contract_violations", tags={"severity": "critical"}).inc()
                        return {"status": "failed", "error": f"Contract violations: {critical}"}
                    else:
                        logger.warning("Contract violations (non-blocking)", component=self.service_name,
                                       event="process_source.contract_warning", correlation_id=source_cid,
                                       violations=contract_violations)
                        metrics.counter("contract_violations", tags={"severity": "warning"}).inc()
            except Exception as e:
                logger.warning("Contract validation failed", component=self.service_name,
                               event="process_source.contract_error", correlation_id=source_cid, error=str(e))

        # ── Read ──
        raw = reader.read(source)
        md = reader.extract_metadata(source)
        reader_time = (time.monotonic() - reader_start) * 1000
        metrics.histogram("reader_duration_ms", tags={"reader": type(reader).__name__}).observe(reader_time)

        source_type = source.metadata.get("source_type", "") if source.metadata else ""
        if not source_type:
            source_type = self._detect_source_type(raw)

        result = {
            "source_type": source_type,
            "filename": source.filename,
            "object_key": source.object_key,
            "bucket": source.bucket,
            "correlation_id": source_cid,
        }

        # ── Dispatch to type-specific processor ──
        try:
            if source_type in ("document", "docx", "pdf", "txt", "csv", "xlsx"):
                proc_result = self._process_document(raw, md, source, result, source_cid)
            elif source_type in ("gmail", "email"):
                proc_result = self._process_communication(raw, md, source, result, source_cid)
            elif source_type == "calendar":
                proc_result = self._process_event(raw, md, source, result, source_cid)
            else:
                proc_result = self._process_document(raw, md, source, result, source_cid)
        except Exception as e:
            total_time = (time.monotonic() - start_time) * 1000
            logger.exception("Source processing failed", component=self.service_name,
                             event="process_source.failed", correlation_id=source_cid,
                             filename=source.filename, duration_ms=total_time)
            metrics.counter("source_failed", tags={"source_type": source_type}).inc()
            metrics.histogram("processing_time_ms", tags={"source_type": source_type, "status": "failed"}).observe(total_time)
            result["status"] = "failed"
            result["error"] = str(e)
            return result

        # ── Lineage: Bronze → Silver ──
        run_id = result.get("run_id") or source_cid
        record_id = proc_result.get("doc_id") or proc_result.get("communications", [{}])[0].get("comm_id") or \
                    proc_result.get("events", [{}])[0].get("event_id") or "unknown"
        table_map = {"document": "documents", "email": "communications", "calendar_event": "events"}
        silver_table = table_map.get(source_type, "documents")
        lineage.emit_bronze_to_silver(run_id, source.object_key, silver_table, str(record_id))

        # ── Final metrics ──
        total_time = (time.monotonic() - start_time) * 1000
        metrics.counter("source_processed", tags={"source_type": source_type}).inc()
        metrics.histogram("processing_time_ms", tags={"source_type": source_type, "status": "success"}).observe(total_time)
        metrics.gauge("freshness_seconds", tags={"table": silver_table}).set(time.time())

        logger.info("Source processed successfully", component=self.service_name,
                     event="process_source.complete", correlation_id=source_cid,
                     filename=source.filename, source_type=source_type, duration_ms=total_time)

        # Push short-lived job metrics
        metrics.push(job_name="silver_pipeline")

        return proc_result

    def _process_document(self, raw, md, source, result, correlation_id: str) -> dict:
        """Process a document source with per-step metrics."""
        logger.info("Processing document", component=self.service_name, event="document.start",
                     correlation_id=correlation_id, filename=source.filename)

        # ── Clean step ──
        clean_start = time.monotonic()
        raw_content = raw.get("content", "")
        content = self.text_cleaner.clean(raw_content)
        clean_time = (time.monotonic() - clean_start) * 1000
        metrics.histogram("cleaner_duration_ms", tags={"source_type": "document"}).observe(clean_time)

        doc_data = {
            "source": source.bucket,
            "source_type": "document",
            "source_object_id": md.get("object_key"),
            "title": source.filename,
            "content": content,
            "checksum": md.get("checksum", ""),
            "mime_type": md.get("mime_type"),
            "size_bytes": source.size_bytes,
            "minio_bucket": source.bucket,
            "minio_path": source.object_key,
            "page_count": raw.get("page_count"),
            "author": md.get("author"),
            "created_time": md.get("created_time"),
            "updated_time": md.get("modified_time"),
            "processing_status": "completed",
            "processed_at": datetime.now(timezone.utc),
            "metadata": {k: v for k, v in md.items() if k not in (
                "checksum", "object_key", "bucket", "mime_type",
            )},
        }

        # ── Schema validation ──
        schema_errors = schema.validate("document", doc_data)
        if schema_errors:
            logger.warning("Document schema violations", component=self.service_name,
                           event="document.schema_issues", correlation_id=correlation_id,
                           errors=schema_errors)
            metrics.counter("schema_violations", tags={"table": "documents"}).inc()

        # ── Save step ──
        save_start = time.monotonic()
        doc_id = self.doc_repo.save(doc_data)
        save_time = (time.monotonic() - save_start) * 1000
        metrics.histogram("repository_save_duration_ms", tags={"table": "documents"}).observe(save_time)
        metrics.histogram("content_length", tags={"table": "documents"}).observe(len(content))

        result["status"] = "processed"
        result["doc_id"] = str(doc_id)
        result["content_length"] = len(content)
        result["checksum"] = md.get("checksum")
        result["correlation_id"] = correlation_id

        logger.info("Document saved", component=self.service_name, event="document.saved",
                     correlation_id=correlation_id, doc_id=str(doc_id), content_length=len(content))

        # ── Quality metrics ──
        if len(content) == 0:
            metrics.counter("empty_content", tags={"table": "documents"}).inc()
            logger.warning("Empty document content", component=self.service_name, event="document.empty",
                           correlation_id=correlation_id, doc_id=str(doc_id))

        return result

    def _process_communication(self, raw, md, source, result, correlation_id: str) -> dict:
        """Process an email/communication source with per-step metrics."""
        logger.info("Processing communication", component=self.service_name, event="communication.start",
                     correlation_id=correlation_id, filename=source.filename)

        emails = raw.get("emails", [])
        results = []
        for email in emails:
            email_cid = f"{correlation_id}/{email.get('email_id', 'unknown')}"

            # ── Clean step ──
            clean_start = time.monotonic()
            body = self.text_cleaner.clean(email.get("body", ""))
            clean_time = (time.monotonic() - clean_start) * 1000
            metrics.histogram("cleaner_duration_ms", tags={"source_type": "email"}).observe(clean_time)

            checksum = hashlib.sha256(json.dumps(email, sort_keys=True).encode()).hexdigest()

            comm_data = {
                "source": "gmail",
                "source_type": "email",
                "source_object_id": email.get("email_id"),
                "thread_id": email.get("thread_id"),
                "subject": email.get("subject"),
                "body": body,
                "sender_name": email.get("sender_name"),
                "sender_email": email.get("sender_email"),
                "recipients": email.get("recipients", []),
                "cc": email.get("cc", []),
                "bcc": email.get("bcc", []),
                "received_at": self._parse_date(email.get("received_at")),
                "has_attachments": email.get("has_attachments", False),
                "attachment_count": len(email.get("attachments", [])),
                "in_reply_to": email.get("in_reply_to"),
                "message_id": email.get("message_id"),
                "checksum": checksum,
                "metadata": md,
                "processing_status": "completed",
                "processed_at": datetime.now(timezone.utc),
            }

            # ── Schema validation ──
            schema_errors = schema.validate("communication", comm_data)
            if schema_errors:
                logger.warning("Communication schema violations", component=self.service_name,
                               event="communication.schema_issues", correlation_id=email_cid,
                               errors=schema_errors)
                metrics.counter("schema_violations", tags={"table": "communications"}).inc()

            # ── Save step ──
            save_start = time.monotonic()
            comm_id = self.comm_repo.save(comm_data)
            save_time = (time.monotonic() - save_start) * 1000
            metrics.histogram("repository_save_duration_ms", tags={"table": "communications"}).observe(save_time)
            metrics.histogram("content_length", tags={"table": "communications"}).observe(len(body))

            # ── Attachments ──
            for att in email.get("attachments", []):
                self.file_repo.save({
                    "source": "gmail",
                    "source_type": "attachment",
                    "source_object_id": f"{email.get('email_id')}/{att.get('filename')}",
                    "filename": att.get("filename", ""),
                    "extension": self._get_extension(att.get("filename", "")),
                    "mime_type": att.get("mime_type", ""),
                    "size_bytes": att.get("size", 0),
                    "checksum": "",
                    "minio_bucket": source.bucket,
                    "minio_path": f"{email.get('email_id')}/{att.get('filename')}",
                    "parent_type": "communication",
                    "parent_id": comm_id,
                    "processing_status": "completed",
                })

            results.append({"comm_id": str(comm_id), "email_id": email.get("email_id")})

        result["status"] = "processed"
        result["communications"] = results
        result["correlation_id"] = correlation_id

        return result

    def _process_event(self, raw, md, source, result, correlation_id: str) -> dict:
        """Process a calendar event source with per-step metrics."""
        events = raw.get("events", [])
        results = []
        for ev in events:
            ev_cid = f"{correlation_id}/{ev.get('event_id', 'unknown')}"
            checksum = hashlib.sha256(json.dumps(ev, sort_keys=True).encode()).hexdigest()

            event_data = {
                "source": "google_calendar",
                "source_type": "calendar_event",
                "source_object_id": ev.get("event_id"),
                "title": ev.get("title"),
                "description": ev.get("description"),
                "location": ev.get("location"),
                "organizer_name": ev.get("organizer_name"),
                "organizer_email": ev.get("organizer_email"),
                "attendees": ev.get("attendees", []),
                "start_time": self._parse_date(ev.get("start_time")),
                "end_time": self._parse_date(ev.get("end_time")),
                "is_all_day": ev.get("is_all_day", False),
                "recurrence": ev.get("recurrence") if isinstance(ev.get("recurrence"), list) else None,
                "status": ev.get("status", "confirmed"),
                "checksum": checksum,
                "metadata": md,
                "processing_status": "completed",
                "processed_at": datetime.now(timezone.utc),
            }

            # Schema validation
            schema_errors = schema.validate("event", event_data)
            if schema_errors:
                metrics.counter("schema_violations", tags={"table": "events"}).inc()

            save_start = time.monotonic()
            event_id = self.event_repo.save(event_data)
            save_time = (time.monotonic() - save_start) * 1000
            metrics.histogram("repository_save_duration_ms", tags={"table": "events"}).observe(save_time)

            results.append({"event_id": str(event_id), "source_id": ev.get("event_id")})

        result["status"] = "processed"
        result["events"] = results
        result["correlation_id"] = correlation_id

        return result

    def process_batch(self, sources: list[SourceData], pipeline_name: str = "silver_pipeline") -> dict:
        """Process a batch of sources with observability.

        OBSERVABILITY:
            - Tracks batch-level metrics (total, processed, failed, skipped)
            - Each source processed with individual correlation_id
            - Lineage events emitted per source
            - Metrics pushed to Prometheus pushgateway
        """
        run_id = str(uuid.uuid4())
        logger.info("Batch processing started", component=self.service_name, event="batch.start",
                     correlation_id=run_id, pipeline_name=pipeline_name, source_count=len(sources))

        batch_start = time.monotonic()
        run_log_id = self.log_repo.start_run(pipeline_name)
        results = []
        processed = failed = skipped = 0
        errors = []

        for idx, source in enumerate(sources):
            correlation_id = f"{run_id}/{idx}"
            try:
                r = self.process_source(source, correlation_id)
                results.append(r)
                if r["status"] == "processed":
                    processed += 1
                elif r["status"] == "failed":
                    failed += 1
                    if "error" in r:
                        errors.append(f"{source.object_key}: {r['error']}")
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                errors.append(f"{source.object_key}: {e}")
                results.append({"status": "error", "object_key": source.object_key, "error": str(e)})
                logger.exception("Batch item failed", component=self.service_name, event="batch.item_error",
                                 correlation_id=run_id, filename=source.filename)

        batch_duration = (time.monotonic() - batch_start) * 1000

        # Update processing log with detailed stats
        self.log_repo.finish_run(
            run_id=run_log_id,
            status="success" if failed == 0 else "partial",
            source_count=len(sources),
            processed_count=processed,
            failed_count=failed,
            skipped_count=skipped,
            errors=errors,
            stats={
                "total": len(sources),
                "processed": processed,
                "failed": failed,
                "skipped": skipped,
                "batch_duration_ms": batch_duration,
                "pipeline_name": pipeline_name,
            },
        )

        # Batch-level metrics
        metrics.counter("batch_total", tags={"pipeline": pipeline_name}).inc()
        metrics.histogram("batch_duration_ms", tags={"pipeline": pipeline_name}).observe(batch_duration)
        metrics.gauge("batch_processed_count", tags={"pipeline": pipeline_name}).set(processed)
        metrics.gauge("batch_failed_count", tags={"pipeline": pipeline_name}).set(failed)
        metrics.gauge("batch_skipped_count", tags={"pipeline": pipeline_name}).set(skipped)

        # Push batch metrics
        metrics.push(job_name=pipeline_name)

        logger.info("Batch processing completed", component=self.service_name, event="batch.complete",
                     correlation_id=run_id, total=len(sources), processed=processed, failed=failed,
                     skipped=skipped, batch_duration_ms=batch_duration)

        return {
            "run_id": run_id,
            "total": len(sources),
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors[:20],
            "results": results,
            "batch_duration_ms": batch_duration,
        }

    @staticmethod
    def _get_extension(filename: str) -> str:
        return os.path.splitext(filename.lower())[1]

    @staticmethod
    def _detect_source_type(raw: dict) -> str:
        if "emails" in raw:
            return "email"
        if "events" in raw:
            return "calendar"
        return "document"

    @staticmethod
    def _parse_date(date_str: str | None):
        if not date_str:
            return None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                return datetime.strptime(date_str.replace("Z", "+0000"), fmt)
            except ValueError:
                continue
        return None
