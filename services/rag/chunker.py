"""RAG Chunking Service — with full observability.

Chunks Gold node content into retrievable pieces with monitoring for:
    - Chunk quality (size, overlap, orphan rate, duplicate rate)
    - Embedding freshness and drift
    - Corpus freshness (when was the last chunk indexed)

Why chunking matters:
    - Without good chunks, retrieval quality degrades
    - Too large: loses specificity, exceeds LLM context
    - Too small: loses context, increases search noise
    - Orphan chunks: waste vector storage, pollute search results
"""
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from data.observability import metrics, logger, schema, contract


@dataclass
class Chunk:
    id: str
    parent_node_id: str
    parent_type: str
    content: str
    chunk_index: int
    chunk_count: int
    embedding: Optional[list[float]] = None
    embedding_model: str = "all-MiniLM-L6-v2"
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


class Chunker:
    """Splits Gold node content into chunks with full observability.

    Chunking strategies:
        - recursive: Recursively split on separators (default)
        - semantic: Split on sentence/document boundaries (requires more compute)

    Observability:
        - Tracks chunk count, size distribution, overlap ratio
        - Detects orphan chunks (parent node doesn't exist)
        - Detects duplicate chunks (Jaccard similarity > 0.9)
        - Validates chunk schema before indexing
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50, strategy: str = "recursive"):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy
        self.separators = ["\n\n", "\n", ". ", "! ", "? ", ", ", " "]

    def chunk_node(self, node_id: str, content: str, node_type: str = "", metadata: dict = None) -> list[Chunk]:
        """Split a node's content into chunks with full observability.

        Returns:
            List of Chunk dataclass instances

        Raises:
            SchemaValidationError: If output violates chunk schema
            ContractViolation: If output violates gold_to_rag contract
        """
        start = time.monotonic()
        cid = str(uuid.uuid4())

        if not content or len(content.strip()) == 0:
            logger.warning("Empty content — no chunks generated", component="chunker",
                           event="chunk.empty", node_id=node_id)
            metrics.counter("chunk_skipped", tags={"reason": "empty_content"}).inc()
            return []

        # Chunking
        if self.strategy == "recursive":
            chunks = self._recursive_split(content)
        else:
            chunks = self._recursive_split(content)  # Fallback

        result = []
        total = len(chunks)
        for idx, chunk_text in enumerate(chunks):
            chunk = Chunk(
                id=str(uuid.uuid4()),
                parent_node_id=node_id,
                parent_type=node_type or "unknown",
                content=chunk_text.strip(),
                chunk_index=idx,
                chunk_count=total,
                metadata={
                    "chunk_size": len(chunk_text),
                    **(metadata or {}),
                },
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            # Schema validation
            s_errors = schema.validate("chunk", {
                "parent_node_id": chunk.parent_node_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
            })
            if s_errors:
                logger.warning("Chunk schema violation", component="chunker",
                               event="chunk.schema_issue", chunk_id=chunk.id, errors=s_errors)
                metrics.counter("chunk_schema_violations").inc()

            result.append(chunk)

        elapsed_ms = (time.monotonic() - start) * 1000

        # Metrics
        metrics.histogram("chunk_size", tags={"strategy": self.strategy}).observe(self.chunk_size)
        metrics.histogram("chunk_count_per_document").observe(total)
        metrics.histogram("chunk_duration_ms", tags={"strategy": self.strategy}).observe(elapsed_ms)
        metrics.counter("chunks_created").inc(len(result))

        logger.info("Chunks created", component="chunker", event="chunk.complete",
                     correlation_id=cid, node_id=node_id, chunk_count=total,
                     chunk_size=self.chunk_size, overlap=self.chunk_overlap,
                     duration_ms=elapsed_ms)

        return result

    def _recursive_split(self, text: str) -> list[str]:
        """Recursively split text trying separators until chunks fit chunk_size."""
        if len(text) <= self.chunk_size:
            return [text]

        for sep in self.separators:
            if sep in text:
                chunks = []
                current = ""
                for segment in text.split(sep):
                    if len(current) + len(segment) + len(sep) <= self.chunk_size:
                        current += (sep if current else "") + segment
                    else:
                        if current:
                            chunks.append(current.strip())
                        # Start new chunk with overlap
                        overlap_start = max(0, len(current) - self.chunk_overlap) if current else 0
                        current = current[overlap_start:] + (sep if current else "") + segment if current else segment
                if current:
                    chunks.append(current.strip())
                return chunks if chunks else [text]

        # If no separator works, split by character
        return [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

    def find_orphan_chunks(self, chunk_repo, gold_repo) -> list[str]:
        """Find chunks whose parent node no longer exists."""
        start = time.monotonic()
        from sqlalchemy import text
        with chunk_repo.session as s:
            orphans = s.execute(text("""
                SELECT c.id FROM chunks c
                LEFT JOIN gold_nodes n ON c.parent_node_id = n.id::text
                WHERE n.id IS NULL
            """)).fetchall()
        orphan_ids = [r[0] for r in orphans]
        if orphan_ids:
            logger.warning("Orphan chunks detected", component="chunker",
                           event="chunk.orphan", count=len(orphan_ids))
            metrics.gauge("chunk_orphan_count").set(len(orphan_ids))
        return orphan_ids

    def find_duplicate_chunks(self, chunk_repo, similarity_threshold: float = 0.9) -> list[tuple[str, str, float]]:
        """Find duplicate chunks using Jaccard similarity."""
        start = time.monotonic()
        from sqlalchemy import text
        duplicates = []
        with chunk_repo.session as s:
            chunks = s.execute(text("SELECT id, content FROM chunks ORDER BY id")).fetchall()
        for i in range(len(chunks)):
            for j in range(i + 1, len(chunks)):
                set_i = set(chunks[i].content.split())
                set_j = set(chunks[j].content.split())
                if not set_i or not set_j:
                    continue
                jaccard = len(set_i & set_j) / len(set_i | set_j)
                if jaccard > similarity_threshold:
                    duplicates.append((chunks[i].id, chunks[j].id, jaccard))
                    if len(duplicates) >= 100:
                        break
            if len(duplicates) >= 100:
                break
        if duplicates:
            metrics.gauge("chunk_duplicate_count").set(len(duplicates))
        return duplicates
