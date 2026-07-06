from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class RetrievalContext:
    upcoming: list[dict] = field(default_factory=list)
    communications: list[dict] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)
    search_results: list[dict] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return bool(self.upcoming or self.communications or self.documents or self.search_results)

    def all_sources(self) -> list[dict]:
        return self.upcoming + self.communications + self.documents + self.search_results


class GoldRetriever:
    def retrieve(self, question: str, session: Session) -> RetrievalContext:
        now = datetime.now(timezone.utc)
        ctx = RetrievalContext(
            upcoming=self._nodes_with_time(now, session),
            communications=self._recent_communications(now, session),
            documents=self._important_documents(session),
            search_results=self._text_search(question, session),
        )
        return ctx

    def _nodes_with_time(self, now: datetime, session: Session) -> list[dict]:
        sql = text("""
            SELECT id, type, subtype, name, summary, content,
                   effective_start, effective_end,
                   importance, properties
            FROM gold_nodes
            WHERE effective_start IS NOT NULL
              AND effective_start >= :week_ago
              AND effective_start <= :month_later
            ORDER BY effective_start ASC
            LIMIT 100
        """)
        rows = session.execute(sql, {
            "week_ago": now - timedelta(days=7),
            "month_later": now + timedelta(days=30),
        }).mappings().all()
        return [dict(r) for r in rows]

    def _recent_communications(self, now: datetime, session: Session) -> list[dict]:
        since = now - timedelta(days=7)
        sql = text("""
            SELECT id, name, summary, content,
                   effective_start, type, subtype,
                   importance, properties
            FROM gold_nodes
            WHERE type = 'communication'
              AND effective_start >= :since
            ORDER BY effective_start DESC
            LIMIT 20
        """)
        rows = session.execute(sql, {"since": since}).mappings().all()
        return [dict(r) for r in rows]

    def _important_documents(self, session: Session) -> list[dict]:
        sql = text("""
            SELECT id, name, summary, content,
                   importance, created_at
            FROM gold_nodes
            WHERE type = 'document'
              AND importance >= 2
            ORDER BY importance DESC, updated_at DESC
            LIMIT 10
        """)
        rows = session.execute(sql).mappings().all()
        return [dict(r) for r in rows]

    def _text_search(self, query: str, session: Session) -> list[dict]:
        if not query.strip():
            return []
        keywords = [w.strip() for w in query.replace("?", "").split() if len(w.strip()) > 1]
        if not keywords:
            return []
        conditions = " OR ".join(
            f"(name ILIKE :kw{i} OR summary ILIKE :kw{i} OR content ILIKE :kw{i})"
            for i in range(len(keywords))
        )
        sql = text(f"""
            SELECT id, type, name, summary,
                   content, effective_start, importance
            FROM gold_nodes
            WHERE {conditions}
            ORDER BY importance DESC NULLS LAST,
                     effective_start DESC NULLS LAST
            LIMIT 10
        """)
        params = {f"kw{i}": f"%{kw}%" for i, kw in enumerate(keywords)}
        rows = session.execute(sql, params).mappings().all()
        if rows:
            return [dict(r) for r in rows]
        sql = text("""
            SELECT id, type, name, summary,
                   content, effective_start, importance
            FROM gold_nodes
            WHERE to_tsvector('simple',
                  coalesce(name,'') || ' ' ||
                  coalesce(summary,'') || ' ' ||
                  coalesce(content,'')
            ) @@ plainto_tsquery('simple', :query)
            ORDER BY importance DESC, effective_start DESC NULLS LAST
            LIMIT 10
        """)
        rows = session.execute(sql, {"query": query}).mappings().all()
        return [dict(r) for r in rows]

    def vector_search(self, session: Session, embedding: list[float], top_k: int = 5) -> list[dict]:
        sql = text("""
            SELECT id, type, name, summary, content,
                   1 - (embedding_vector <=> :embedding) AS similarity
            FROM gold_nodes
            WHERE embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> :embedding
            LIMIT :top_k
        """)
        rows = session.execute(
            sql,
            {"embedding": embedding, "top_k": top_k},
        ).mappings().all()
        return [dict(r) for r in rows]
