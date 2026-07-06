#!/usr/bin/env python3
"""
Silver Layer Pipeline: Bronze -> Silver
Steps: Validation -> Cleaning -> Normalization -> Deduplication -> Enrichment

Applies all 5 steps to BOTH metadata and text content (inside attachments).
"""
import hashlib
import io
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.storage import get_client, BUCKET


# ============================================================
# TEXT EXTRACTION (raw binary -> raw text)
# ============================================================

def extract_text_from_docx(data: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return ""
    except Exception:
        return ""


def extract_text_from_pdf(data: bytes) -> str:
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        return ""
    except Exception:
        return ""


def extract_raw_text(filename: str, data: bytes) -> str:
    if not data:
        return ""
    fname = filename.lower()
    if fname.endswith(".docx"):
        return extract_text_from_docx(data)
    elif fname.endswith(".pdf"):
        return extract_text_from_pdf(data)
    elif fname.endswith(".txt"):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.decode("latin-1", errors="replace")
    return ""


# ============================================================
# Stage 1: Content Validation
# ============================================================

def validate_raw_text(text: str) -> dict:
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "length": len(text),
        "line_count": text.count("\n") + 1 if text else 0,
        "non_ascii_ratio": 0.0,
        "control_char_ratio": 0.0,
    }

    if not text or not text.strip():
        result["valid"] = False
        result["errors"].append("text is empty after extraction")
        return result

    if len(text.strip()) < 10:
        result["warnings"].append("text too short (<10 chars), may be unreadable")

    total = len(text) or 1
    control_count = sum(1 for c in text if unicodedata.category(c) == "Cc" and c not in ("\n", "\r", "\t"))
    result["control_char_ratio"] = round(control_count / total, 4)
    if result["control_char_ratio"] > 0.05:
        result["warnings"].append(
            f"high control char ratio ({result['control_char_ratio']:.2%}), "
            f"may contain binary garbage"
        )

    non_ascii = sum(1 for c in text if ord(c) > 127)
    result["non_ascii_ratio"] = round(non_ascii / total, 4)

    # Check for garbled extraction (too many symbols, too few real words)
    word_count = len(re.findall(r"\b\w+\b", text))
    symbol_count = len(re.findall(r"[^\w\s]", text))
    result["word_count"] = word_count
    result["symbol_count"] = symbol_count
    if word_count > 0 and symbol_count / word_count > 3:
        result["warnings"].append(
            f"high symbol/word ratio ({symbol_count}/{word_count}), "
            f"text may be garbled"
        )

    return result


# ============================================================
# Stage 2: Content Cleaning
# ============================================================

def clean_text(text: str) -> str:
    if not text:
        return ""

    # Remove BOM and zero-width chars
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")

    # Normalize line endings: \r\n -> \n, \r -> \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove control chars except newline, tab, carriage return
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Remove HTML entities
    text = re.sub(r"&[#a-zA-Z0-9]+;", " ", text)

    # Collapse multiple blank lines to max 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim leading/trailing whitespace per line
    text = "\n".join(line.strip() for line in text.split("\n"))

    # Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Remove lines that are only separators (---, ===, ___, ...)
    text = "\n".join(
        line for line in text.split("\n")
        if not re.match(r"^[\s\-_=*#]{3,}$", line)
    )

    # Final trim
    text = text.strip()

    return text


def clean_subject(subject: str) -> str:
    if not subject:
        return ""
    subject = re.sub(r"&[#a-zA-Z0-9]+;", " ", subject)
    subject = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", subject)
    subject = re.sub(r"\s+", " ", subject).strip()
    return subject


def clean_sender(sender: str) -> dict:
    if not sender:
        return {"name": "", "email": ""}

    match = re.match(r"^(.+?)\s*<([^>]+)>\s*$", sender)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip().lower()
        return {"name": name, "email": email}

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", sender)
    if email_match:
        email = email_match.group(0).strip().lower()
        name_part = (
            sender.replace(email_match.group(0), "")
            .strip()
            .strip("<>()")
            .strip('"')
        )
        return {"name": name_part, "email": email}

    return {"name": sender.strip(), "email": ""}


def clean_date(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.isoformat()
    except Exception:
        return date_str


def clean_filename(filename: str) -> str:
    filename = re.sub(r"[\x00-\x1f]", "", filename)
    filename = filename.strip()
    name, ext = os.path.splitext(filename)
    ext = ext.lower()
    return f"{name}{ext}"


# ============================================================
# Stage 3: Content Normalization
# ============================================================

def normalize_text(text: str, lowercase: bool = False) -> str:
    if not text:
        return ""

    # Unicode normalization: NFC (composed form)
    text = unicodedata.normalize("NFC", text)

    # Normalize numbers: standardize digit chars
    # Full-width digits -> half-width
    text = re.sub(r"[０-９]", lambda m: chr(ord(m.group(0)) - 0xFEE0), text)

    if lowercase:
        text = text.lower()

    # Normalize dashes: em-dash, en-dash -> hyphen
    text = text.replace("\u2013", "-").replace("\u2014", "-")

    # Normalize quotes: smart quotes -> straight quotes
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    # Normalize bullet points
    text = re.sub(r"[\u2022\u2023\u25E6\u2043]", "*", text)

    # Normalize spaces around punctuation
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)

    # Ensure single space after punctuation (if followed by letter)
    text = re.sub(r"([.,;:!?])([A-Za-z0-9\u00C0-\u024F])", r"\1 \2", text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()

    return text


def normalize_number_text(text: str) -> str:
    """Normalize numbers in text: standardize date/number formats."""
    if not text:
        return ""

    # Normalize date separators: 01/06/2026 -> 01-06-2026 or vice versa
    # Keep as-is but detect patterns
    text = re.sub(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})", r"\1-\2-\3", text)

    # Normalize thousand separators: 1,000 -> 1000
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)

    return text


FILE_CATEGORIES = {
    ".pdf": "document",
    ".doc": "document",
    ".docx": "document",
    ".txt": "text",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
}


def normalize_filename(filename: str) -> str:
    name, ext = os.path.splitext(filename)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^\w\-]", "", name)
    name = name[:100]
    return f"{name}{ext}"


def classify_file_type(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    return FILE_CATEGORIES.get(ext, "unknown")


# ============================================================
# Stage 4: Content Deduplication
# ============================================================

def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_text_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity on word shingles (word-level overlap)."""
    if not text1 or not text2:
        return 0.0

    def shingles(t: str, n: int = 5) -> set:
        tokens = re.findall(r"\b\w+\b", t.lower())
        return {" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)} if len(tokens) >= n else set()

    s1 = shingles(text1)
    s2 = shingles(text2)

    if not s1 or not s2:
        return 0.0

    intersection = s1 & s2
    union = s1 | s2
    return len(intersection) / len(union)


def deduplicate_records(records: list) -> (list, list):
    seen_email_ids = set()
    seen_content_hashes = {}
    seen_norm_texts = []  # List[Tuple[email_id, filename, cleaned_text]]
    deduped = []
    removed = []

    for record in records:
        email_id = record.get("email_id")

        # Dedup by email_id
        if email_id and email_id in seen_email_ids:
            removed.append({"email_id": email_id, "reason": "duplicate_email_id"})
            continue

        # Dedup by content hash + text similarity per attachment
        for att in record.get("attachments", []):
            content_hash = att.get("content_hash")
            cleaned_text = att.get("cleaned_text", "")

            # Hard dedup: exact SHA256 match
            if content_hash:
                if content_hash in seen_content_hashes:
                    removed.append({
                        "email_id": email_id,
                        "filename": att.get("filename"),
                        "reason": "duplicate_content_exact_hash",
                        "hash": content_hash,
                    })
                    att["duplicate"] = True
                    continue

            # Soft dedup: text similarity > 90%
            if cleaned_text and len(cleaned_text) > 50:
                is_dup = False
                for (seen_eid, seen_fn, seen_text) in seen_norm_texts:
                    sim = compute_text_similarity(cleaned_text, seen_text)
                    if sim > 0.90:
                        removed.append({
                            "email_id": email_id,
                            "filename": att.get("filename"),
                            "reason": "duplicate_text_similarity",
                            "similar_to": seen_fn,
                            "similarity": round(sim, 4),
                        })
                        att["duplicate"] = True
                        is_dup = True
                        break

                if not is_dup:
                    seen_norm_texts.append((
                        email_id,
                        att.get("filename"),
                        cleaned_text,
                    ))

            if content_hash and not att.get("duplicate"):
                seen_content_hashes[content_hash] = email_id

        # If all attachments are duplicates, skip entire record
        attachments = record.get("attachments", [])
        if attachments and all(a.get("duplicate") for a in attachments):
            removed.append({
                "email_id": email_id,
                "reason": "all_attachments_are_duplicates",
            })
            continue

        seen_email_ids.add(email_id)
        deduped.append(record)

    return deduped, removed


# ============================================================
# Stage 5: Content Enrichment
# ============================================================

def extract_keywords(text: str, top_n: int = 10) -> list:
    if not text or len(text.strip()) < 20:
        return []

    words = re.findall(r"\b\w{3,}\b", text.lower())
    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
        "her", "was", "one", "our", "out", "has", "have", "been", "some",
        "them", "than", "its", "over", "such", "that", "this", "with",
        "from", "they", "will", "each", "make", "like", "more", "also",
        "và", "của", "các", "có", "cho", "với", "được", "trong", "một",
        "những", "khi", "về", "đến", "làm", "này", "nên", "nhiều", "theo",
        "sau", "trên", "dưới", "giữa", "hoặc", "không", "nếu", "rằng",
        "từ", "đã", "sẽ", "đang", "bị", "bởi", "tại", "vào", "ra", "lên",
        "xuống", "qua", "lại", "cùng", "ngày", "tháng", "năm",
    }
    words = [w for w in words if w not in stop_words and not w.isdigit()]

    if not words:
        return []

    most_common = Counter(words).most_common(top_n)
    return [{"word": w, "count": c} for w, c in most_common]


def detect_dates(text: str) -> list:
    if not text:
        return []

    dates = set()
    patterns = [
        (r"\d{1,2}/\d{1,2}/\d{2,4}", None),
        (r"\d{4}-\d{2}-\d{2}", None),
        (r"\d{1,2}-\d{1,2}-\d{4}", None),
        (
            r"(Ngày|ngày|Date|date)\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})",
            None,
        ),
    ]
    for pat, _ in patterns:
        for m in re.finditer(pat, text):
            dates.add(m.group(0))

    # Also find Vietnamese date patterns
    month_names_en = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    month_names_vi = r"(Tháng|thang|Thg|thg)\s*\d{1,2}"
    for pat in [month_names_en, month_names_vi]:
        for m in re.finditer(pat, text, re.IGNORECASE):
            dates.add(m.group(0))

    return sorted(dates)[:20]


def chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list:
    if not text:
        return []

    # Split by paragraphs first
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 1 > max_chars and current_chunk:
            chunks.append(current_chunk.strip())
            # Overlap: take last 'overlap' chars
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
            current_chunk = overlap_text + "\n" + para if overlap_text else para
        else:
            current_chunk = (current_chunk + "\n" + para).strip()

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def detect_language(text: str) -> str:
    if not text or len(text.strip()) < 10:
        return "unknown"

    vietnamese_chars = len(re.findall(
        r"[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩị"
        r"òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        r"ÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊ"
        r"ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]",
        text,
    ))

    if vietnamese_chars > 2:
        return "vi"

    return "en"


def classify_content_type(subject: str, text: str) -> str:
    combined = f"{subject} {text[:500]}".lower()

    keywords = {
        "schedule": [
            "lịch", "schedule", "meeting", "appointment", "calendar",
            "work plan", "lam viec", "lich", "thời gian", "kế hoạch",
            "lịch trình", "agenda",
        ],
        "invoice": [
            "invoice", "hóa đơn", "bill", "payment", "thanh toán",
            "receipt", "hoa don", "total", "subtotal", "vat",
        ],
        "report": [
            "report", "báo cáo", "summary", "baocao", "kpi",
            "analysis", "tong hop", "kết quả", "result",
        ],
        "contract": [
            "contract", "hợp đồng", "agreement", "thỏa thuận",
            "hopdong", "signed", "ký kết", "điều khoản",
        ],
        "personal": [
            "personal", "cá nhân", "letter", "thư", "giới thiệu",
            "cv", "resume", "sơ yếu",
        ],
    }

    scores = {}
    for ctype, words in keywords.items():
        scores[ctype] = sum(1 for w in words if w in combined)

    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "other"


def compute_readability_stats(text: str) -> dict:
    if not text:
        return {"sentence_count": 0, "avg_sentence_length": 0, "avg_word_length": 0}

    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    sentence_count = len(sentences)
    avg_sentence_len = (
        round(sum(len(s.split()) for s in sentences) / sentence_count, 1)
        if sentence_count
        else 0
    )

    words = re.findall(r"\b\w+\b", text)
    avg_word_len = (
        round(sum(len(w) for w in words) / len(words), 2) if words else 0
    )

    return {
        "sentence_count": sentence_count,
        "avg_sentence_length": avg_sentence_len,
        "avg_word_length": avg_word_len,
    }


# ============================================================
# ORCHESTRATOR: apply all 5 stages to one record
# ============================================================

def process_email(email: dict, attachments: list, raw_attachments: list) -> dict:
    """Apply all 5 stages: Validation -> Cleaning -> Normalization -> Deduplication -> Enrichment
    to BOTH metadata and text content."""

    result = {
        "email_id": email["id"],
        "thread_id": email.get("thread_id", ""),
        "pipeline_version": "silver-v2",
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── STAGE 1: VALIDATION ──
    # Validate metadata
    result["metadata_validation"] = validate_metadata(email, attachments)

    # Extract raw text from all attachments
    result["raw_attachments"] = []
    for i, att in enumerate(attachments):
        raw = raw_attachments[i] if i < len(raw_attachments) else None
        if raw:
            raw_text = extract_raw_text(att["filename"], raw["data"])
        else:
            raw_text = ""

        # Validate content
        content_validation = validate_raw_text(raw_text)
        result["raw_attachments"].append({
            "attachment_id": att["id"],
            "filename": att["filename"],
            "object_key": att["object_key"],
            "raw_text": raw_text,
            "content_validation": content_validation,
            "raw_data": raw,
        })

    # ── STAGE 2: CLEANING ──
    result["subject"] = clean_subject(email.get("subject", ""))
    result["sender"] = clean_sender(email.get("sender", ""))
    result["received_at"] = clean_date(email.get("received_at", ""))

    result["attachments"] = []
    for ra in result["raw_attachments"]:
        raw_text = ra["raw_text"]
        cleaned_text = clean_text(raw_text)

        # Categorize cleaning operations
        cleaning_ops = []
        if raw_text != cleaned_text:
            if len(raw_text) != len(cleaned_text):
                cleaning_ops.append("removed_control_chars")
            if "\r\n" in raw_text:
                cleaning_ops.append("normalized_line_endings")
            if re.search(r"&[#a-zA-Z0-9]+;", raw_text):
                cleaning_ops.append("removed_html_entities")

        result["attachments"].append({
            "attachment_id": ra["attachment_id"],
            "filename": clean_filename(ra["filename"]),
            "cleaning_ops": cleaning_ops,
            "cleaned_text": cleaned_text,
        })

    # ── STAGE 3: NORMALIZATION ──
    for att in result["attachments"]:
        cleaned = att["cleaned_text"]

        # Normalize text content
        normalized = normalize_text(cleaned)
        normalized_numbers = normalize_number_text(normalized)

        att["normalized_text"] = normalized_numbers
        att["normalized_filename"] = normalize_filename(att["filename"])
        att["file_category"] = classify_file_type(att["filename"])
        att["size_kb"] = round(
            sum(
                ra["raw_data"]["size"]
                for ra in result["raw_attachments"]
                if ra["attachment_id"] == att["attachment_id"]
            )
            / 1024,
            2,
        )

    # ── STAGE 4: DEDUPLICATION ──
    # Compute hashes for dedup
    for i, att in enumerate(result["attachments"]):
        raw = result["raw_attachments"][i]
        if raw["raw_data"]:
            att["content_hash"] = compute_content_hash(raw["raw_data"]["data"])
        else:
            att["content_hash"] = ""
        att["duplicate"] = False

    # Collect all text for enrichment (already normalized)
    all_text = " ".join(
        a.get("normalized_text", "") for a in result["attachments"]
    )
    result["all_text"] = all_text

    # ── STAGE 5: ENRICHMENT ──
    # Language
    result["language"] = detect_language(all_text)

    # Content type
    result["content_type"] = classify_content_type(
        result.get("subject", ""), all_text
    )

    # Keyword extraction
    result["keywords"] = extract_keywords(all_text)

    # Date detection
    result["detected_dates"] = detect_dates(all_text)

    # Text chunking (for downstream processing)
    result["text_chunks"] = chunk_text(all_text)

    # Readability stats
    result["readability"] = compute_readability_stats(all_text)

    # Per-attachment enrichment
    for att in result["attachments"]:
        nt = att.get("normalized_text", "")
        att["language"] = detect_language(nt)
        att["text_length"] = len(nt)
        att["text_word_count"] = len(re.findall(r"\b\w+\b", nt))
        att["keywords"] = extract_keywords(nt, top_n=5)
        att["content_type"] = classify_content_type(
            result.get("subject", ""), nt
        )

    # Stats
    result["attachment_count"] = len(result["attachments"])
    result["total_text_length"] = len(all_text)
    result["total_word_count"] = len(re.findall(r"\b\w+\b", all_text))

    # Remove raw binary data from result (keep only what we need)
    for ra in result["raw_attachments"]:
        ra.pop("raw_data", None)
        ra.pop("raw_text", None)

    return result


def validate_metadata(email: dict, attachments: list) -> dict:
    v = {"valid": True, "errors": [], "warnings": []}

    if not email.get("id"):
        v["valid"] = False
        v["errors"].append("email_id is empty")
    if not email.get("subject"):
        v["warnings"].append("subject is empty")
    if not email.get("sender"):
        v["warnings"].append("sender is empty")

    for att in attachments:
        if not att.get("filename"):
            v["valid"] = False
            v["errors"].append(f"attachment {att.get('id')}: filename is empty")
        if att.get("size", 0) <= 0:
            v["warnings"].append(
                f"attachment {att.get('id')}: size is 0 or negative"
            )

    return v


# ============================================================
# DATA ACCESS
# ============================================================

BRONZE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "bronze", "minio"
)
DOCUMENTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "documents"
)


def fetch_raw_data_from_minio(attachment: dict) -> Optional[dict]:
    try:
        client = get_client()
        response = client.get_object(attachment["bucket"], attachment["object_key"])
        data = response.read()
        response.close()
        response.release_conn()
        return {"data": data, **attachment}
    except Exception:
        pass

    try:
        local_path = os.path.join(
            BRONZE_DIR, attachment["bucket"], attachment["object_key"]
        )
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                data = f.read()
            return {"data": data, **attachment}
    except Exception:
        pass

    try:
        email_id = attachment.get("object_key", "").split("/")[0]
        filename = attachment.get("filename", "")
        doc_path = os.path.join(DOCUMENTS_DIR, f"{email_id}_{filename}")
        if os.path.exists(doc_path):
            with open(doc_path, "rb") as f:
                data = f.read()
            return {"data": data, **attachment}
    except Exception:
        pass

    return None


# ============================================================
# POSTGRESQL OUTPUT (primary)
# ============================================================

def save_to_postgres(processed: list, run_id: int):
    from scripts.database_pg import (
        init_db, get_conn, put_conn,
        save_silver_record, save_silver_attachments,
        save_silver_texts, save_silver_chunks,
    )

    init_db()
    conn = get_conn()
    try:
        for rec in processed:
            save_silver_record(conn, rec)
            save_silver_attachments(conn, rec)
            save_silver_texts(conn, rec)
            save_silver_chunks(conn, rec)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# ============================================================
# JSONL BACKUP (fallback when PostgreSQL unavailable)
# ============================================================

SILVER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "silver"
)
TEXT_DIR = os.path.join(SILVER_DIR, "extracted_text")


def _sanitize_filename(fn: str) -> str:
    return re.sub(r"[^\w\-\.]", "_", fn)


def save_to_sqlite(processed: list, run_id: int):
    """Fallback: store in SQLite + JSONL when PostgreSQL is not available."""
    from scripts.database import get_conn as get_sqlite_conn

    conn = get_sqlite_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silver_records (
            email_id TEXT PRIMARY KEY,
            subject TEXT,
            sender_name TEXT,
            sender_email TEXT,
            received_at TEXT,
            content_type TEXT,
            language TEXT,
            attachment_count INTEGER,
            total_text_length INTEGER,
            keyword_count INTEGER,
            processed_at TEXT,
            pipeline_run_id INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silver_processing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            status TEXT,
            processed INTEGER,
            failed INTEGER,
            errors TEXT
        )
    """)

    for rec in processed:
        conn.execute(
            """INSERT OR REPLACE INTO silver_records
               (email_id, subject, sender_name, sender_email, received_at,
                content_type, language, attachment_count, total_text_length,
                keyword_count, processed_at, pipeline_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec["email_id"],
                rec.get("subject", ""),
                rec.get("sender", {}).get("name", ""),
                rec.get("sender", {}).get("email", ""),
                rec.get("received_at", ""),
                rec.get("content_type", ""),
                rec.get("language", ""),
                rec.get("attachment_count", 0),
                rec.get("total_text_length", 0),
                len(rec.get("keywords", [])),
                rec.get("processed_at", ""),
                run_id,
            ),
        )

    save_jsonl_backup(processed, run_id)
    conn.commit()
    conn.close()


def save_jsonl_backup(processed: list, run_id: int):
    os.makedirs(SILVER_DIR, exist_ok=True)
    os.makedirs(TEXT_DIR, exist_ok=True)

    for rec in processed:
        jsonl_path = os.path.join(SILVER_DIR, "records.jsonl")
        json_record = {k: v for k, v in rec.items()
                       if k not in ("raw_attachments", "attachments", "all_text", "text_chunks")}
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(json_record, ensure_ascii=False) + "\n")

        jsonl_att = os.path.join(SILVER_DIR, "attachments.jsonl")
        for att in rec.get("attachments", []):
            att_json = {
                "email_id": rec["email_id"],
                "filename": att.get("filename", ""),
                "normalized_filename": att.get("normalized_filename", ""),
                "file_category": att.get("file_category", ""),
                "size_kb": att.get("size_kb", 0),
                "language": att.get("language", ""),
                "content_hash": att.get("content_hash", ""),
                "text_length": att.get("text_length", 0),
                "text_word_count": att.get("text_word_count", 0),
                "content_type": att.get("content_type", ""),
                "keywords": att.get("keywords", []),
                "cleaning_ops": att.get("cleaning_ops", []),
            }
            with open(jsonl_att, "a", encoding="utf-8") as f:
                f.write(json.dumps(att_json, ensure_ascii=False) + "\n")

            normalized_text = att.get("normalized_text", "")
            if normalized_text:
                safe = _sanitize_filename(
                    att.get("normalized_filename", att.get("filename", "unknown"))
                )
                with open(os.path.join(TEXT_DIR, f"{rec['email_id']}_{safe}.txt"),
                          "w", encoding="utf-8") as f:
                    f.write(normalized_text)

        chunks_path = os.path.join(SILVER_DIR, "chunks.jsonl")
        for i, chunk in enumerate(rec.get("text_chunks", [])):
            with open(chunks_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "email_id": rec["email_id"],
                    "chunk_index": i,
                    "text": chunk,
                    "length": len(chunk),
                }, ensure_ascii=False) + "\n")


# ============================================================
# RUNNER
# ============================================================

def _get_storage():
    try:
        from scripts.database_pg import init_db, get_conn, put_conn
        init_db()
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        put_conn(conn)
        return "postgres"
    except Exception as e:
        return "sqlite"


def _get_pending(storage: str):
    if storage == "postgres":
        from scripts.database_pg import get_pending_email_ids
        return get_pending_email_ids()

    from scripts.database import get_conn
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id FROM emails"
        ).fetchall()]
        return [r["id"] for r in rows]
    finally:
        conn.close()


def _get_email_data(storage: str, email_id: str):
    if storage == "postgres":
        from scripts.database_pg import get_email_attachments
        return get_email_attachments(email_id)

    from scripts.database import get_conn
    conn = get_conn()
    try:
        email = dict(conn.execute(
            "SELECT * FROM emails WHERE id = ?", (email_id,)
        ).fetchone() or {})
        attachments = [dict(r) for r in conn.execute(
            "SELECT * FROM attachments WHERE email_id = ?", (email_id,)
        ).fetchall()]
        return email, attachments
    finally:
        conn.close()


def _save_pipeline_run(processed_count: int, errors: list) -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    try:
        from scripts.database_pg import save_pipeline_run as pg_save
        return pg_save(processed_count, len(errors), errors)
    except Exception:
        pass

    from scripts.database import get_conn
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silver_processing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            status TEXT,
            processed INTEGER,
            failed INTEGER,
            errors TEXT
        )
    """)
    cur = conn.execute(
        "INSERT INTO silver_processing (run_at, status, processed, failed, errors) VALUES (?, ?, ?, ?, ?)",
        (now, "success", processed_count, len(errors), json.dumps(errors[:100])),
    )
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def _save_output(storage: str, processed: list, run_id: int):
    if storage == "postgres":
        save_to_postgres(processed, run_id)
    save_jsonl_backup(processed, run_id)


def run():
    print("=" * 70)
    print("  SILVER PIPELINE v2 - Bronze -> Silver")
    print("  Validation -> Cleaning -> Normalization -> Deduplication -> Enrichment")
    print("=" * 70)

    print("\n[0] Detecting storage backend...")
    storage = _get_storage()
    print("    Using: %s" % storage)

    print("\n[1] Fetching pending emails...")
    pending_ids = _get_pending(storage)
    print("    Found %d new email(s)" % len(pending_ids))

    if not pending_ids:
        print("\n All emails already processed.")
        return

    processed = []
    errors = []

    for email_id in pending_ids:
        email, attachments = _get_email_data(storage, email_id)
        if not email:
            errors.append("%s: email not found" % email_id)
            continue

        print("\n  [%s] %s" % (email_id, email.get("subject", "")[:60]))

        raw_attachments = []
        for att in attachments:
            raw = fetch_raw_data_from_minio(att)
            if raw:
                raw_attachments.append(raw)

        if not raw_attachments:
            errors.append("%s: no attachment data" % email_id)
            print("    SKIP")
            continue

        result = process_email(email, attachments, raw_attachments)
        processed.append(result)
        print("    Done - %d attachment(s), %d text chars" % (
            result["attachment_count"],
            result["total_text_length"],
        ))

    if processed:
        print("\n[4] Cross-record deduplication...")
        deduped, removed = deduplicate_records(processed)
        if removed:
            print("    Removed %d duplicate(s):" % len(removed))
            for r in removed:
                print("      - %s: %s" % (r['email_id'], r['reason']))
                if 'similarity' in r:
                    print("        (similarity: %.2f%%, with: %s)" % (
                        r['similarity'] * 100, r.get('similar_to', '?')
                    ))

        run_id = _save_pipeline_run(len(deduped), errors)

        print("\n[5] Saving to %s..." % storage.upper())
        _save_output(storage, deduped, run_id)

        print("\n Silver pipeline v2 completed!")
        print("   Processed: %d" % len(deduped))
        print("   Failed: %d" % len(errors))
        print("   Run ID: %d" % run_id)
        print("   Storage: %s + JSONL backup" % storage)
    else:
        print("\n No records were processed successfully.")


if __name__ == "__main__":
    run()
