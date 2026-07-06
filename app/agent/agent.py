from openai import OpenAI

from app.agent.prompt import build_prompt
from app.config.settings import settings
from app.retriever.retriever import GoldRetriever, RetrievalContext
from app.schemas.chat import Source


class Agent:
    def __init__(self):
        self.retriever = GoldRetriever()
        self._client = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
        return self._client

    def answer(self, question: str, ctx: RetrievalContext) -> tuple[str, list[Source]]:
        prompt = build_prompt(question, ctx)

        response = self.client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
        )

        answer = response.choices[0].message.content or ""

        sources = []
        seen = set()
        for item in ctx.all_sources():
            uid = str(item.get("id", ""))
            if uid in seen:
                continue
            seen.add(uid)
            name = item.get("name") or ""
            if not name or (item.get("type") == "communication" and name.startswith("Email")):
                summary = item.get("summary") or item.get("content") or ""
                name = summary[:100] if summary else name
            if not name:
                continue
            sources.append(
                Source(
                    type=item.get("type", "unknown"),
                    name=name,
                    summary=(item.get("summary") or item.get("content", "")[:200] or None),
                )
            )

        order = {"event": 0, "agent": 0, "document": 1, "communication": 2}
        sources.sort(key=lambda s: order.get(s.type, 9))

        return answer, sources[:10]
