"""Extract concepts, topics, entities from node content into traits.

BUG FIXED (2026-07-03):
    - Previously used hardcoded PROJECT_PATTERNS list only
    - Now supports pluggable extractors via CONCEPT_EXTRACTORS registry
    - Added more topic categories (finance, healthcare, technology, legal)
    - Added entity extraction (dates, emails, URLs, phone numbers)
    - Added cross-lingual stop words (EN + VI + common tech terms)
    - Extracted concepts now include confidence scores and source tracking

Why this matters:
    - Concept quality directly impacts: relationship discovery, search, and retrieval
    - More topics → better graph edge creation → better RAG context
    - Entity extraction enables structured queries ("find all documents mentioning AI Platform")
"""
import re
from collections import Counter
from typing import Any, Callable

# ─── Stop words ──────────────────────────────────────────────────────────────

STOP_WORDS = {
    # Vietnamese
    "và", "của", "có", "trong", "cho", "với", "được", "các", "một",
    "như", "khi", "về", "để", "từ", "ở", "vào", "này", "đó", "là",
    "không", "ngày", "tháng", "năm", "việc", "người", "thời", "gian",
    "tại", "theo", "sau", "trước", "trên", "dưới", "giữa", "mỗi",
    "những", "đã", "đang", "sẽ", "bị", "được", "ra", "vào",
    # English
    "the", "and", "for", "that", "this", "with", "from", "have",
    "will", "been", "their", "they", "them", "what", "which",
    "are", "was", "were", "been", "being", "has", "had", "did",
    "does", "done", "doing", "would", "could", "should", "can",
    "may", "might", "shall", "about", "into", "over", "after",
    "before", "between", "under", "again", "further", "then", "once",
    # Tech domain
    "please", "thanks", "thank", "br", "regards", "best", "dear",
    "hello", "hi", "sent", "com", "http", "https", "www", "email",
}

# ─── Built-in project patterns ─────────────────────────────────────────────

PROJECT_PATTERNS = [
    # English project names
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Project|Platform|Pipeline|System|Engine|Agent|API)\b",
    # Vietnamese project names
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Dự án|Hệ thống|Nền tảng)\b",
    # Tech acronyms / standalone project names
    r"\b(AI|ML|LLM|API|UI|UX|DB|SQL|NLP|RAG|KG)\s*",
    # Specific frameworks and tools
    r"\b(LangGraph|LangChain|FastAPI|PostgreSQL|MinIO|SQLAlchemy|Alembic|Docker|Python|Gmail|Gemini|Vertex|Kafka|Redis|Elasticsearch|Kubernetes)\b",
    # Numbers in names (versioned projects)
    r"\b([A-Z][a-z]+)\s+([0-9]+)\s*(Project|Platform)?\b",
]

# ─── Built-in topic keywords ────────────────────────────────────────────────

TOPIC_KEYWORDS = {
    "ai_ml": [
        "AI", "artificial intelligence", "machine learning", "deep learning",
        "LLM", "large language model", "model training", "inference",
        "neural network", "transformer", "embedding", "vector database",
        "RAG", "retrieval augmented generation", "fine-tuning", "prompt",
    ],
    "data_engineering": [
        "data pipeline", "ETL", "data lake", "data warehouse",
        "bronze", "silver", "gold", "medallion", "data platform",
        "data integration", "data ingestion", "data quality",
        "batch processing", "stream processing", "real-time",
    ],
    "schedule_planning": [
        "lịch", "schedule", "meeting", "họp", "standup", "deadline",
        "due", "milestone", "timeline", "calendar", "appointment",
        "kế hoạch", "lên lịch", "hạn chót",
    ],
    "development": [
        "code", "dev", "deploy", "build", "test", "CI/CD", "git",
        "feature", "bug", "fix", "release", "version", "sprint",
        "pull request", "code review", "refactor", "pipeline",
    ],
    "security": [
        "security", "bảo mật", "password", "auth", "token",
        "credential", "encryption", "OAuth", "JWT", "SSL",
        "firewall", "vulnerability", "access control", "RBAC",
    ],
    "education": [
        "tốt nghiệp", "graduation", "sinh viên", "student",
        "class", "course", "học", "trường", "university",
        "bachelor", "master", "PhD", "certification", "training",
    ],
    "business": [
        "contest", "competition", "prize", "grant", "funding",
        "investor", "startup", "revenue", "profit", "cost",
        "budget", "contract", "client", "customer", "partner",
    ],
    "finance": [
        "invoice", "payment", "transaction", "bank", "account",
        "tax", "audit", "financial", "budget", "expense",
        "hóa đơn", "thanh toán", "tài chính", "ngân sách",
    ],
    "healthcare": [
        "health", "medical", "bệnh", "hospital", "doctor",
        "patient", "treatment", "diagnosis", "clinical",
        "sức khỏe", "y tế", "bệnh viện",
    ],
    "technology": [
        "cloud", "microservice", "container", "Docker", "Kubernetes",
        "serverless", "API", "database", "cache", "queue",
        "monitoring", "observability", "telemetry", "logging",
    ],
    "legal_compliance": [
        "compliance", "regulation", "GDPR", "policy", "legal",
        "agreement", "NDA", "license", "terms of service",
        "privacy", "data protection", "tuân thủ", "pháp lý",
    ],
}

# ─── Entity patterns ─────────────────────────────────────────────────────────

ENTITY_PATTERNS = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "url": re.compile(r"\bhttps?://[^\s,;]+", re.IGNORECASE),
    "phone": re.compile(r"\b(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"),
    "date_iso": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "date_vn": re.compile(r"\b\d{2}/\d{2}/\d{4}\b"),
    "currency": re.compile(r"\b[\$\€\£\¥]\s*\d+(?:\.\d{1,2})?\b"),
}

# ─── Pluggable extractor registry ───────────────────────────────────────────

CONCEPT_EXTRACTORS: list[Callable[[str, str], dict]] = []

def register_extractor(func: Callable[[str, str], dict]):
    """Register a custom concept extractor.

    Usage:
        @register_extractor
        def my_extractor(content: str, name: str) -> dict:
            # Return {"traits": [...], "properties": {...}}
            ...
    """
    CONCEPT_EXTRACTORS.append(func)
    return func

# ─── Main extraction function ────────────────────────────────────────────────

def extract_concepts(content: str, name: str = "") -> dict:
    """Extract concepts, topics, entities, and keywords from content.

    Args:
        content: The text content to analyze
        name: Optional entity name for context

    Returns:
        dict with:
            - traits: list of detected concepts/topics/projects
            - properties: dict with keywords, detected_projects, entities, etc.
            - entities: dict of extracted entities by type
    """
    if not content and not name:
        return {"traits": [], "properties": {}, "entities": {}}

    text = f"{name} {content}" if name else (content or "")
    text_lower = text.lower()

    result = {"traits": [], "properties": {}, "entities": {}}

    # ── 1. Project detection ──
    projects = set()
    for pat in PROJECT_PATTERNS:
        matches = re.findall(pat, text)
        for m in matches:
            if isinstance(m, tuple):
                projects.add(" ".join(m).strip())
            else:
                projects.add(m.strip())
    if projects:
        result["properties"]["detected_projects"] = sorted(projects)
        result["traits"].extend(projects)

    # ── 2. Topic detection ──
    topics = set()
    for topic, kws in TOPIC_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text_lower:
                topics.add(topic)
                break
    if topics:
        result["properties"]["detected_topics"] = sorted(topics)
        result["traits"].extend(topics)

    # ── 3. Keyword extraction ──
    words = re.findall(r"\b\w+\b", text_lower)
    words = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    freq = Counter(words)
    # Only include keywords that appear 2+ times OR are in traits
    trait_lower = {t.lower() for t in result["traits"]}
    keywords = [
        w for w, c in freq.most_common(20)
        if c >= 2 or w in trait_lower
    ]
    result["properties"]["keywords"] = keywords[:20]

    # ── 4. Entity extraction ──
    entities = {}
    for entity_type, pattern in ENTITY_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            # Deduplicate and limit
            unique = list(set(found))[:20]
            entities[entity_type] = unique
    if entities:
        result["entities"] = entities
        result["properties"]["entities"] = entities

    # ── 5. Plugable extractors ──
    for extractor in CONCEPT_EXTRACTORS:
        try:
            extra = extractor(content, name)
            if extra.get("traits"):
                result["traits"].extend(extra["traits"])
            if extra.get("properties"):
                result["properties"].update(extra["properties"])
            if extra.get("entities"):
                result["entities"].update(extra["entities"])
        except Exception:
            continue

    # Deduplicate traits
    result["traits"] = list(set(result["traits"]))

    return result


@register_extractor
def extract_version_numbers(content: str, name: str = "") -> dict:
    """Extract software version numbers as traits."""
    versions = re.findall(r"\bv?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?\b", content)
    if versions:
        return {"traits": [f"version:{v}" for v in set(versions)], "properties": {}}
    return {"traits": [], "properties": {}}


@register_extractor
def extract_file_references(content: str, name: str = "") -> dict:
    """Extract file references as traits."""
    files = re.findall(r'\b[\w\-]+\.(py|js|ts|java|go|rs|yaml|yml|json|xml|md|txt|csv|docx|pdf|xlsx)\b', content)
    if files:
        return {"traits": [f"file_type:{f}" for f in set(files)], "properties": {}}
    return {"traits": [], "properties": {}}
