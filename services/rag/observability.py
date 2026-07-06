"""RAG Observability Dashboard — comprehensive monitoring for RAG system.

This module provides the metrics and health checks for:
    - Chunk quality (size, overlap, orphan, duplicate)
    - Embedding drift (PSI, MMD, mean shift)
    - Corpus freshness (last index time, stale chunks)
    - Retrieval quality (precision, recall, MRR, NDCG)
    - Vector DB health (index size, query latency, recall)
    - Orphan and duplicate chunk detection

All metrics are exposed via Prometheus for Grafana dashboards.
"""
import time
from datetime import datetime, timezone
from typing import Optional

from data.observability import metrics, logger


class RAGObservability:
    """Comprehensive RAG system observability.

    Usage:
        rag_obs = RAGObservability()
        rag_obs.record_chunk_quality(chunk_count=10, avg_size=450, overlap_ratio=0.1)
        rag_obs.record_retrieval_quality(precision=0.8, recall=0.7, mrr=0.85)
        rag_obs.check_corpus_freshness(last_index_time=datetime.now(timezone.utc))
        rag_obs.detect_embedding_drift(reference_embeddings=[...], current_embeddings=[...])
    """

    # ─── Chunk Quality ──────────────────────────────────────────────────────

    @staticmethod
    def record_chunk_quality(chunk_count: int, avg_size: float, overlap_ratio: float,
                              empty_chunks: int = 0, total_documents: int = 0):
        """Record chunk quality metrics.

        Tracks:
            - Average chunk size (too large = bad for retrieval)
            - Overlap ratio (too much overlap = waste)
            - Empty chunk rate (should be 0)
            - Chunks per document (consistency check)
        """
        metrics.histogram("rag_chunk_size_avg").observe(avg_size)
        metrics.histogram("rag_chunk_overlap_ratio").observe(overlap_ratio)
        metrics.gauge("rag_chunk_empty_count").set(empty_chunks)
        if total_documents > 0:
            metrics.histogram("rag_chunks_per_document").observe(chunk_count / max(total_documents, 1))

    @staticmethod
    def record_orphan_chunks(count: int):
        """Record orphan chunks — chunks whose parent no longer exists."""
        metrics.gauge("rag_orphan_chunks").set(count)
        if count > 0:
            logger.warning("Orphan chunks detected", component="rag_observability",
                           event="rag.orphan_chunks", count=count)

    @staticmethod
    def record_duplicate_chunks(count: int):
        """Record duplicate chunks — chunks with high similarity to others."""
        metrics.gauge("rag_duplicate_chunks").set(count)
        if count > 0:
            logger.warning("Duplicate chunks detected", component="rag_observability",
                           event="rag.duplicate_chunks", count=count)

    # ─── Embedding Drift ────────────────────────────────────────────────────

    @staticmethod
    def detect_embedding_drift(reference_mean: list[float], current_mean: list[float],
                                reference_std: list[float], current_std: list[float]) -> dict:
        """Detect embedding drift using mean shift and PSI.

        Args:
            reference_mean: Mean embedding from reference period
            current_mean: Mean embedding from current period
            reference_std: Std from reference period
            current_std: Std from current period

        Returns:
            dict with drift metrics: mean_shift, max_psi, drift_detected
        """
        if not reference_mean or not current_mean:
            return {"mean_shift": 0, "max_psi": 0, "drift_detected": False}

        import math
        # Mean shift (Euclidean distance between mean vectors)
        mean_shift = math.sqrt(sum((a - b) ** 2 for a, b in zip(reference_mean, current_mean)))

        # PSI (Population Stability Index) per dimension
        psi_values = []
        for ref_m, cur_m, ref_s, cur_s in zip(reference_mean, current_mean, reference_std, current_std):
            if ref_s == 0:
                continue
            # Simplified PSI: compare z-score bins
            ref_z = abs(ref_m) / max(ref_s, 1e-10)
            cur_z = abs(cur_m) / max(cur_s, 1e-10)
            if ref_z == 0:
                continue
            psi = (cur_z - ref_z) * math.log(cur_z / max(ref_z, 1e-10))
            psi_values.append(psi)

        max_psi = max(psi_values) if psi_values else 0
        avg_psi = sum(psi_values) / max(len(psi_values), 1) if psi_values else 0

        drift_detected = mean_shift > 0.1 or max_psi > 0.2

        metrics.gauge("rag_embedding_mean_shift").set(mean_shift)
        metrics.gauge("rag_embedding_max_psi").set(max_psi)
        metrics.gauge("rag_embedding_avg_psi").set(avg_psi)

        if drift_detected:
            logger.warning("Embedding drift detected", component="rag_observability",
                           event="rag.embedding_drift", mean_shift=mean_shift, max_psi=max_psi)

        return {
            "mean_shift": mean_shift,
            "max_psi": max_psi,
            "avg_psi": avg_psi,
            "drift_detected": drift_detected,
        }

    # ─── Corpus Freshness ───────────────────────────────────────────────────

    @staticmethod
    def check_corpus_freshness(last_index_time: Optional[datetime] = None) -> dict:
        """Check how fresh the vector corpus is.

        Returns:
            dict with: freshness_hours, is_stale, staleness_threshold_hours
        """
        threshold = 24  # 24 hours before corpus is considered stale
        if last_index_time is None:
            return {"freshness_hours": -1, "is_stale": True, "staleness_threshold_hours": threshold}

        delta = datetime.now(timezone.utc) - last_index_time
        freshness_hours = delta.total_seconds() / 3600
        is_stale = freshness_hours > threshold

        metrics.gauge("rag_corpus_freshness_hours").set(freshness_hours)

        if is_stale:
            logger.warning("Corpus is stale", component="rag_observability",
                           event="rag.corpus_stale", freshness_hours=freshness_hours,
                           threshold_hours=threshold)

        return {
            "freshness_hours": round(freshness_hours, 2),
            "is_stale": is_stale,
            "staleness_threshold_hours": threshold,
        }

    # ─── Retrieval Quality ──────────────────────────────────────────────────

    @staticmethod
    def record_retrieval_quality(precision: float = 0.0, recall: float = 0.0,
                                  mrr: float = 0.0, ndcg: float = 0.0,
                                  latency_ms: float = 0.0, result_count: int = 0):
        """Record retrieval quality metrics if ground truth is available."""
        metrics.gauge("rag_retrieval_precision").set(precision)
        metrics.gauge("rag_retrieval_recall").set(recall)
        metrics.gauge("rag_retrieval_mrr").set(mrr)
        metrics.gauge("rag_retrieval_ndcg").set(ndcg)

    # ─── Vector DB Health ───────────────────────────────────────────────────

    @staticmethod
    def record_vector_db_health(total_vectors: int, index_size_bytes: int,
                                 avg_query_latency_ms: float, recall_at_k: float = 0.0):
        """Record vector database health metrics."""
        metrics.gauge("rag_vector_total_count").set(total_vectors)
        metrics.gauge("rag_vector_index_size_bytes").set(index_size_bytes)
        metrics.gauge("rag_vector_query_latency_ms").set(avg_query_latency_ms)
        metrics.gauge("rag_vector_recall_at_k").set(recall_at_k)
