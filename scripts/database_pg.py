"""
PostgreSQL module for Silver layer storage.
Replaces SQLite-based database.py for processed data.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool

# Connection config from env with defaults
PG_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5433")),
    "dbname": os.getenv("PG_DB", "ai_platform"),
    "user": os.getenv("PG_USER", "platform"),
    "password": os.getenv("PG_PASSWORD", "platform123"),
}

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=5, **PG_CONFIG
        )
    return _pool


def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    return conn


def put_conn(conn):
    pool = get_pool()
    pool.putconn(conn)


def init_db():
    """Create schema if not exists (run once at startup)."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(open(
                os.path.join(
                    os.path.dirname(__file__),
                    "..", "infrastructure", "docker", "postgres-init.sql"
                ), encoding="utf-8"
            ).read())
        conn.commit()
    finally:
        put_conn(conn)


def save_silver_record(conn, record: dict) -> str:
    email_id = record["email_id"]
    sender = record.get("sender", {})
    metadata = {k: v for k, v in record.items()
                if k in ("pipeline_version", "metadata_validation",
                         "detected_dates", "readability")}

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO silver_records
                (email_id, subject, sender_name, sender_email, received_at,
                 content_type, language, attachment_count, total_text_length,
                 keyword_count, metadata, processed_at, pipeline_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (email_id) DO UPDATE SET
                subject = EXCLUDED.subject,
                content_type = EXCLUDED.content_type,
                language = EXCLUDED.language,
                metadata = EXCLUDED.metadata,
                pipeline_run_id = EXCLUDED.pipeline_run_id
        """, (
            email_id,
            record.get("subject", ""),
            sender.get("name", ""),
            sender.get("email", ""),
            record.get("received_at"),
            record.get("content_type"),
            record.get("language"),
            record.get("attachment_count", 0),
            record.get("total_text_length", 0),
            len(record.get("keywords", [])),
            json.dumps(metadata, ensure_ascii=False),
            record.get("processed_at"),
            record.get("pipeline_run_id"),
        ))
    return email_id


def save_silver_attachments(conn, record: dict):
    for att in record.get("attachments", []):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver_attachments
                    (email_id, filename, normalized_filename, file_category,
                     size_kb, language, content_hash, text_length,
                     text_word_count, content_type, keywords, cleaning_ops)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                record["email_id"],
                att.get("filename", ""),
                att.get("normalized_filename", ""),
                att.get("file_category", ""),
                att.get("size_kb", 0),
                att.get("language", ""),
                att.get("content_hash", ""),
                att.get("text_length", 0),
                att.get("text_word_count", 0),
                att.get("content_type", ""),
                [k["word"] for k in att.get("keywords", [])],
                att.get("cleaning_ops", []),
            ))


def save_silver_texts(conn, record: dict):
    for att in record.get("attachments", []):
        normalized_text = att.get("normalized_text", "")
        if normalized_text:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO silver_texts
                        (email_id, filename, normalized_text)
                    VALUES (%s, %s, %s)
                """, (
                    record["email_id"],
                    att.get("filename", ""),
                    normalized_text,
                ))


def save_silver_chunks(conn, record: dict):
    for i, chunk in enumerate(record.get("text_chunks", [])):
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver_chunks
                    (email_id, chunk_index, text, length)
                VALUES (%s, %s, %s, %s)
            """, (
                record["email_id"],
                i,
                chunk,
                len(chunk),
            ))


def save_pipeline_run(processed: int, failed: int, errors: list) -> int:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO silver_processing
                    (run_at, status, processed, failed, errors)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                datetime.now(timezone.utc).isoformat(),
                "success",
                processed,
                failed,
                json.dumps(errors[:100]),
            ))
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id
    finally:
        put_conn(conn)


def get_pending_email_ids() -> list:
    """Get email IDs in bronze that are not yet in silver."""
    import sqlite3
    bronze_db = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "pipeline.db"
    )
    bconn = sqlite3.connect(bronze_db)
    bconn.row_factory = sqlite3.Row
    bronze_ids = {
        r["id"] for r in bconn.execute("SELECT id FROM emails").fetchall()
    }
    bconn.close()

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email_id FROM silver_records")
            silver_ids = {r[0] for r in cur.fetchall()}
    finally:
        put_conn(conn)

    pending = list(bronze_ids - silver_ids)
    return pending


def get_email_attachments(email_id: str):
    """Fetch email + attachments from Bronze SQLite for processing."""
    import sqlite3
    bronze_db = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "pipeline.db"
    )
    bconn = sqlite3.connect(bronze_db)
    bconn.row_factory = sqlite3.Row

    email = dict(bconn.execute(
        "SELECT * FROM emails WHERE id = ?", (email_id,)
    ).fetchone() or {})
    attachments = [
        dict(r) for r in bconn.execute(
            "SELECT * FROM attachments WHERE email_id = ?", (email_id,)
        ).fetchall()
    ]
    bconn.close()
    return email, attachments
