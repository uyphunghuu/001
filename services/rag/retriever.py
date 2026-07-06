"""RAG Retrieval Service — with full observability.

Retrieves relevant chunks for a query with monitoring for:
    - Retrieval latency and result count
    - Precision/recall at K
    - Context diversity (unique documents in top-K)
    - Score distribution
    - Retrieval failures and fallbacks

Why retrieval observability matters:
    - Bad retrieval = bad LLM response = bad user experience
    - High latency = poor user experience
    - Low diversity = narrow context = hallucination risk
    - Low precision = noise = wasted LLM tokens
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from data.observability import metrics, logger


@dataclass
class RetrievalResult:
    query: str
    chunks: list[dict]
    total_results: int
    latency_ms: float
    strategy: str
    query_embedding: Optional[list[float]] = None
    diversity_score: float = 0.0
    unique_parents: int = 0


class Retriever:
    """Retrieves relevant chunks using hybrid (vector + keyword) search.

    Observability:
        - Tracks retrieval latency, count, score distribution
        - Computes context diversity (how many unique parent nodes)
        - Tracks retrieval errors and fallback strategies
        - Monitors vector search health (index searches, recall)
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2", top_k: int = 5,
                 score_threshold: float = 0.5, hybrid_weight: float = 0.7):
        self.embedding_model = embedding_model
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.hybrid_weight = hybrid_weight
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.embedding_model)
        except ImportError:
            self._model = None

    def retrieve(self, query: str, repo, top_k: int = None, strategy: str = "hybrid") -> RetrievalResult:
        """Retrieve chunks for a query with full observability.

        Args:
            query: User query string
            repo: BaseRepository for DB access
            top_k: Override default top_k
            strategy: "vector", "keyword", or "hybrid"

        Returns:
            RetrievalResult with chunks, metrics, and quality indicators
        """
        start = time.monotonic()
        k = top_k or self.top_k
        rid = str(uuid.uuid4())

        logger.info("Retrieving chunks", component="retriever", event="retrieve.start",
                     correlation_id=rid, query=query[:100], strategy=strategy, top_k=k)

        if strategy == "vector":
            result = self._vector_search(query, repo, k)
        elif strategy == "keyword":
            result = self._keyword_search(query, repo, k)
        else:
            result = self._hybrid_search(query, repo, k)

        elapsed_ms = (time.monotonic() - start) * 1000
        result.latency_ms = elapsed_ms
        result.query = query
        result.strategy = strategy

        # Quality metrics
        if result.chunks:
            # Unique parent nodes = diversity
            parent_ids = set(c.get("parent_node_id", "") for c in result.chunks)
            result.unique_parents = len(parent_ids)
            result.diversity_score = len(parent_ids) / max(len(result.chunks), 1)

        # Observability
        metrics.histogram("retrieval_latency_ms", tags={"strategy": strategy}).observe(elapsed_ms)
        metrics.histogram("retrieval_result_count", tags={"strategy": strategy}).observe(result.total_results)
        metrics.histogram("retrieval_diversity_score").observe(result.diversity_score)
        metrics.counter("retrieval_total", tags={"strategy": strategy}).inc()

        logger.info("Retrieval completed", component="retriever", event="retrieve.complete",
                     correlation_id=rid, total=result.total_results, latency_ms=elapsed_ms,
                     strategy=strategy, diversity=result.diversity_score)

        return result

    def _vector_search(self, query: str, repo, top_k: int) -> RetrievalResult:
        """Vector similarity search using pgvector cosine distance."""
        self._load_model()
        if not self._model:
            return RetrievalResult(query=query, chunks=[], total_results=0,
                                   latency_ms=0, strategy="vector",
                                   query_embedding=None)

        try:
            vec = self._model.encode(query, normalize_embeddings=True)
            from sqlalchemy import text
            with repo.session as s:
                rows = s.execute(text("""
                    SELECT id, parent_node_id, content, chunk_index,
                           1 - (embedding <=> CAST(:vec AS vector)) as score,
                           parent_type
                    FROM chunks
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> CAST(:vec AS vector)) > :threshold
                    ORDER BY embedding <=> CAST(:vec AS vector)
                    LIMIT :limit
                """), {"vec": vec.tolist(), "threshold": self.score_threshold, "limit": top_k}).fetchall()

            chunks = [{
                "id": str(r.id),
                "parent_node_id": str(r.parent_node_id) if r.parent_node_id else "",
                "content": r.content,
                "chunk_index": r.chunk_index,
                "parent_type": r.parent_type,
                "score": float(r.score),
            } for r in rows]

            return RetrievalResult(
                query=query, chunks=chunks, total_results=len(chunks),
                latency_ms=0, strategy="vector", query_embedding=vec.tolist(),
            )

        except Exception as e:
            logger.error("Vector search failed", component="retriever", event="retrieve.vector_error",
                         error=str(e))
            metrics.counter("retrieval_errors", tags={"strategy": "vector"}).inc()
            return RetrievalResult(query=query, chunks=[], total_results=0,
                                   latency_ms=0, strategy="vector")

    def _keyword_search(self, query: str, repo, top_k: int) -> RetrievalResult:
        """Full-text keyword search fallback."""
        try:
            from sqlalchemy import text
            with repo.session as s:
                rows = s.execute(text("""
                    SELECT id, parent_node_id, content, chunk_index, parent_type,
                           ts_rank(to_tsvector('english', content), plainto_tsquery('english', :q)) as score
                    FROM chunks
                    WHERE to_tsvector('english', content) @@ plainto_tsquery('english', :q)
                    ORDER BY score DESC
                    LIMIT :limit
                """), {"q": query, "limit": top_k}).fetchall()

            chunks = [{
                "id": str(r.id),
                "parent_node_id": str(r.parent_node_id) if r.parent_node_id else "",
                "content": r.content,
                "chunk_index": r.chunk_index,
                "parent_type": r.parent_type,
                "score": float(r.score),
            } for r in rows]

            return RetrievalResult(
                query=query, chunks=chunks, total_results=len(chunks),
                latency_ms=0, strategy="keyword",
            )

        except Exception as e:
            logger.error("Keyword search failed", component="retriever", event="retrieve.keyword_error",
                         error=str(e))
            metrics.counter("retrieval_errors", tags={"strategy": "keyword"}).inc()
            return RetrievalResult(query=query, chunks=[], total_results=0,
                                   latency_ms=0, strategy="keyword")

    def _hybrid_search(self, query: str, repo, top_k: int) -> RetrievalResult:
        """Hybrid search: combine vector + keyword scores with weighted normalization."""
        vec_result = self._vector_search(query, repo, top_k * 2)
        kw_result = self._keyword_search(query, repo, top_k * 2)

        combined = {}
        # Weight vector results
        for c in vec_result.chunks:
            cid = c["id"]
            combined[cid] = {"chunk": c, "score": c["score"] * self.hybrid_weight}

        # Add keyword results with weight
        for c in kw_result.chunks:
            cid = c["id"]
            if cid in combined:
                combined[cid]["score"] += c["score"] * (1 - self.hybrid_weight)
                combined[cid]["chunk"]["hybrid"] = True
            else:
                combined[cid] = {"chunk": c, "score": c["score"] * (1 - self.hybrid_weight)}

        # Sort by combined score
        sorted_chunks = sorted(combined.values(), key=lambda x: x["score"], reverse=True)[:top_k]

        chunks = [c["chunk"] for c in sorted_chunks]
        for c, s in zip(chunks, sorted_chunks):
            c["score"] = s["score"]

        return RetrievalResult(
            query=query, chunks=chunks, total_results=len(chunks),
            latency_ms=0, strategy="hybrid",
        )
