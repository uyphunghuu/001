from datetime import datetime, timezone

from app.retriever.retriever import RetrievalContext


def _fmt_dt(dt) -> str:
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M")


def _section(title: str, items: list[dict], fields: list[str]) -> str:
    if not items:
        return ""
    lines = [f"=== {title} ==="]
    for item in items:
        parts = []
        for f in fields:
            val = item.get(f)
            if val is None:
                continue
            if f == "properties" and isinstance(val, dict):
                val = ", ".join(f"{k}={v}" for k, v in val.items() if not k.startswith("_"))
            parts.append(f"{f}: {val}")
        if parts:
            lines.append("  " + " | ".join(parts))
    return "\n".join(lines)


def build_prompt(question: str, ctx: RetrievalContext) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections = [
        f"You are a helpful AI assistant for a knowledge worker. Today is {now_str}.",
        "",
        "Below is data retrieved from the user's knowledge base. Use it to answer the question.",
        "If the data is insufficient, say so clearly. Be concise and factual.",
        "",
    ]

    upcoming = _section(
        "SCHEDULED ITEMS (EVENTS, MEETINGS, DEADLINES)",
        ctx.upcoming,
        ["name", "type", "subtype", "summary", "effective_start", "effective_end", "importance"],
    )
    if upcoming:
        sections.append(upcoming)
        sections.append("")

    comms = _section(
        "RECENT COMMUNICATIONS",
        ctx.communications,
        ["name", "summary", "effective_start", "type", "subtype"],
    )
    if comms:
        sections.append(comms)
        sections.append("")

    docs = _section(
        "IMPORTANT DOCUMENTS",
        ctx.documents,
        ["name", "summary", "importance"],
    )
    if docs:
        sections.append(docs)
        sections.append("")

    search = _section(
        "SEARCH RESULTS",
        ctx.search_results,
        ["name", "type", "summary", "effective_start", "importance"],
    )
    if search:
        sections.append(search)
        sections.append("")

    if not ctx.has_data:
        sections.append("No relevant data found in the knowledge base for this question.")
        sections.append("")

    sections.append("Question: " + question)
    sections.append("")
    sections.append("Answer:")

    return "\n".join(sections)
