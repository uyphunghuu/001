"""OpenLineage integration for data lineage tracking.

Tracks every data transform across Bronze → Silver → Gold → RAG → Agent.
Emits lineage events to Marquez or DataHub for impact analysis and RCA.

File locations:
    - data/observability/lineage.py (this file)
    - Lineage events emitted at: silver_pipeline.py, gold_pipeline.py, chunker.py, agent/tracer.py
    - Dashboard: infrastructure/monitoring/grafana/dashboards/lineage.json
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

try:
    from openlineage.client import OpenLineageClient as _OLClient
    from openlineage.client.run import RunEvent, RunState, Run, Job
    from openlineage.client.event import DatasetEvent
    HAS_OPENLINEAGE = True
except ImportError:
    HAS_OPENLINEAGE = False


class LineageTracker:
    """Tracks data lineage across the platform.

    Why:
        - Impact analysis: "Which downstream systems are affected if I change X?"
        - Root cause analysis: "Which upstream failure caused this data issue?"
        - Audit: "Where did this data come from and what transforms did it go through?"

    How:
        - Each pipeline step emits a lineage event with inputs, outputs, and transform info
        - Events are sent to OpenLineage-compatible backend (Marquez, DataHub)
        - Falls back to JSON file if no backend available

    File locations for integration:
        - run_silver.py:162 — emit lineage before/after batch
        - data/silver/services/silver_pipeline.py:192 — per-source lineage
        - data/gold/pipeline/gold_pipeline.py:28 — per-node lineage
        - services/rag/chunker.py:45 — chunk lineage
        - services/agent/tracer.py:38 — agent execution lineage
    """

    NAMESPACE = "ai_platform"

    def __init__(self, backend_url: Optional[str] = None, file_output: Optional[str] = None):
        self.backend_url = backend_url or os.environ.get("OPENLINEAGE_URL", "")
        self.file_output = file_output or os.environ.get("LINEAGE_FILE", "data/observability/lineage_events.jsonl")
        self._client = None
        if HAS_OPENLINEAGE and self.backend_url:
            try:
                self._client = _OLClient(url=self.backend_url)
            except Exception:
                self._client = None

    def _file_fallback(self, event: dict):
        """Write lineage event to JSONL file as fallback."""
        try:
            os.makedirs(os.path.dirname(self.file_output), exist_ok=True)
            with open(self.file_output, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception:
            pass

    def emit_transform(
        self,
        run_id: str,
        inputs: list[dict],
        outputs: list[dict],
        transform: str,
        context: Optional[dict] = None,
        status: str = "COMPLETE",
    ):
        """Emit a lineage event for a data transform.

        Args:
            run_id: Unique run identifier (UUID string)
            inputs: List of {"namespace": "...", "name": "...", "facets": {...}}
            outputs: List of {"namespace": "...", "name": "...", "facets": {...}}
            transform: Transform/job name (e.g. "silver_pipeline.process_source")
            context: Optional metadata dict
            status: RunState (COMPLETE, FAILED, RUNNING)

        Example:
            tracker.emit_transform(
                run_id=str(uuid.uuid4()),
                inputs=[{"namespace": "minio", "name": "gmail-raw/email.json"}],
                outputs=[{"namespace": "postgres", "name": "ai_platform.documents"}],
                transform="silver_pipeline.process_document",
            )
        """
        event = {
            "eventType": status,
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "run": {"runId": run_id},
            "job": {"namespace": self.NAMESPACE, "name": transform},
            "inputs": inputs,
            "outputs": outputs,
            "context": context or {},
        }

        if self._client:
            try:
                self._client.emit(
                    RunEvent(
                        eventType=RunState.COMPLETE if status == "COMPLETE" else RunState.FAILED,
                        eventTime=datetime.now(timezone.utc),
                        run=Run(runId=run_id),
                        job=Job(namespace=self.NAMESPACE, name=transform),
                        inputs=[DatasetEvent(**i) for i in inputs],
                        outputs=[DatasetEvent(**o) for o in outputs],
                    )
                )
            except Exception:
                self._file_fallback(event)
        else:
            self._file_fallback(event)

    def emit_bronze_to_silver(self, run_id: str, object_key: str, table: str, record_id: str, status: str = "COMPLETE"):
        """Shorthand for Bronze → Silver lineage."""
        self.emit_transform(
            run_id=run_id,
            inputs=[{"namespace": "minio", "name": f"gmail-raw/{object_key}"}],
            outputs=[{"namespace": "postgres", "name": f"ai_platform.{table}", "facets": {"id": record_id}}],
            transform="silver_pipeline",
            status=status,
        )

    def emit_silver_to_gold(self, run_id: str, silver_table: str, silver_id: str, node_id: str, status: str = "COMPLETE"):
        """Shorthand for Silver → Gold lineage."""
        self.emit_transform(
            run_id=run_id,
            inputs=[{"namespace": "postgres", "name": f"ai_platform.{silver_table}", "facets": {"id": silver_id}}],
            outputs=[{"namespace": "postgres", "name": "ai_platform.gold_nodes", "facets": {"id": node_id}}],
            transform="gold_pipeline.classify_and_enrich",
            status=status,
        )

    def emit_gold_to_rag(self, run_id: str, node_id: str, chunk_ids: list[str], status: str = "COMPLETE"):
        """Shorthand for Gold → RAG chunk lineage."""
        self.emit_transform(
            run_id=run_id,
            inputs=[{"namespace": "postgres", "name": "ai_platform.gold_nodes", "facets": {"id": node_id}}],
            outputs=[{"namespace": "postgres", "name": "ai_platform.chunks", "facets": {"ids": chunk_ids}}],
            transform="rag_pipeline.chunk_and_index",
            status=status,
        )
