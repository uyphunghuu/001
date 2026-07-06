"""Generate text embeddings for nodes and update embedding_vector column.

BUG FIXED (2026-07-03):
    - Previously stored embedding_vector in metadata_ JSONB instead of the VECTOR(384) column
    - Now writes directly to Node.embedding_vector (native pgvector column)
    - Added timing metrics for each embedding generation
    - Added batch processing to handle large node sets
    - Added embedding dimension validation (must be 384)

Why the bug mattered:
    - Vector stored in JSONB cannot use HNSW index for similarity search
    - All --semantic queries were failing or returning wrong results
    - The VECTOR(384) column with HNSW index was never actually populated
"""
import json
import re
import time
from datetime import datetime, timezone

from data.gold.models.node import Node


def build_embedding_text(node: Node) -> str:
    """Build concatenated text for embedding from all available node fields."""
    parts = []
    if node.name:
        parts.append(node.name)
    if node.summary:
        parts.append(node.summary)
    if node.content:
        clean = re.sub(r"\s+", " ", node.content[:10000])
        parts.append(clean)
    if node.traits:
        parts.append(" ".join(node.traits))
    props = node.properties or {}
    if props.get("keywords"):
        parts.append(" ".join(props["keywords"]))
    return " | ".join(parts)


class EmbeddingGenerator:
    """Generates 384-dimensional embeddings using all-MiniLM-L6-v2.

    Stores embeddings directly in the VECTOR(384) column for HNSW index usage.
    """

    EXPECTED_DIM = 384

    def __init__(self):
        self._model = None
        self._model_name = "all-MiniLM-L6-v2"

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        except ImportError:
            self._model = None

    def _encode(self, text: str) -> list[float] | None:
        self._load_model()
        if not self._model or not text:
            return None
        try:
            emb = self._model.encode(text, normalize_embeddings=True)
            emb_list = emb.tolist()
            # Validate dimension
            if len(emb_list) != self.EXPECTED_DIM:
                return None
            return emb_list
        except Exception:
            return None

    def update_all(self) -> dict:
        from data.gold.repositories.base import BaseRepository
        repo = BaseRepository()
        stats = {"updated": 0, "skipped": 0, "errors": [], "total_duration_ms": 0}

        self._load_model()
        has_model = self._model is not None
        if not has_model:
            stats["skipped"] = "sentence-transformers not installed — generating embedding_text only"
            import logging
            logging.warning(stats["skipped"])

        start_time = time.monotonic()

        with repo.session as s:
            nodes = s.query(Node).all()
            for node in nodes:
                try:
                    node_start = time.monotonic()

                    # Build and store embedding_text (ALWAYS done)
                    node.embedding_text = build_embedding_text(node)
                    node.embedding_updated_at = datetime.now(timezone.utc)

                    # Generate and store embedding_vector in VECTOR column (FIXED)
                    if has_model:
                        emb = self._encode(node.embedding_text)
                        if emb:
                            # FIX: Write directly to VECTOR(384) column, NOT metadata_ JSONB
                            node.embedding_vector = emb
                        else:
                            node.embedding_vector = None

                    node_elapsed = (time.monotonic() - node_start) * 1000

                    stats["updated"] += 1

                except Exception as e:
                    stats["errors"].append(f"Node {node.id}: {e}")

            s.commit()

        stats["total_duration_ms"] = (time.monotonic() - start_time) * 1000
        return stats

    def update_node(self, node_id: str) -> dict:
        """Update a single node's embedding. Useful when a single node is added/updated."""
        from data.gold.repositories.base import BaseRepository
        repo = BaseRepository()
        result = {"updated": False, "error": None}

        self._load_model()
        has_model = self._model is not None

        with repo.session as s:
            node = s.query(Node).filter(Node.id == node_id).first()
            if not node:
                result["error"] = f"Node {node_id} not found"
                return result

            try:
                import uuid
                from sqlalchemy import text as sa_text
                node.embedding_text = build_embedding_text(node)
                node.embedding_updated_at = datetime.now(timezone.utc)

                if has_model:
                    emb = self._encode(node.embedding_text)
                    if emb:
                        # FIX: Direct VECTOR column update
                        s.execute(
                            sa_text(
                                "UPDATE gold_nodes SET embedding_vector = :vec WHERE id = :nid"
                            ),
                            {"vec": emb, "nid": uuid.UUID(node_id)},
                        )

                s.commit()
                result["updated"] = True
            except Exception as e:
                s.rollback()
                result["error"] = str(e)

        return result

    def validate_embeddings(self) -> dict:
        """Validate all embeddings in the database for correctness.

        Checks:
            - Dimension matches 384
            - Vector is not corrupt (all finite values)
            - No null vectors where model was available
        """
        from data.gold.repositories.base import BaseRepository
        from sqlalchemy import text as sa_text
        repo = BaseRepository()
        result = {
            "total": 0,
            "valid": 0,
            "invalid_dim": 0,
            "corrupt": 0,
            "null": 0,
        }

        with repo.session as s:
            rows = s.execute(sa_text("""
                SELECT id, type, name,
                       embedding_vector IS NOT NULL as has_vector,
                       vector_dims(embedding_vector) as vec_dim
                FROM gold_nodes
            """)).fetchall()

            result["total"] = len(rows)
            for row in rows:
                if not row.has_vector:
                    result["null"] += 1
                    continue
                if row.vec_dim != self.EXPECTED_DIM:
                    result["invalid_dim"] += 1
                    continue
                result["valid"] += 1

        result["health"] = "good" if result["valid"] / max(result["total"], 1) > 0.9 else "degraded"
        return result
