import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_FILE = os.path.join(DB_DIR, "pipeline.db")


def get_conn():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crawl_state (
            id INTEGER PRIMARY KEY,
            last_crawl_at TEXT NOT NULL,
            status TEXT NOT NULL,
            new_emails INTEGER DEFAULT 0,
            new_attachments INTEGER DEFAULT 0,
            error TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            thread_id TEXT,
            subject TEXT,
            sender TEXT,
            received_at TEXT,
            file_count INTEGER DEFAULT 0,
            crawled_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL,
            filename TEXT,
            bucket TEXT,
            object_key TEXT,
            size INTEGER,
            mime_type TEXT,
            crawled_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (email_id) REFERENCES emails(id)
        );
    """)
    conn.commit()
    conn.close()


def get_last_crawl_time() -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT last_crawl_at FROM crawl_state ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row["last_crawl_at"] if row else None


def get_all_crawled_email_ids() -> set:
    conn = get_conn()
    rows = conn.execute("SELECT id FROM emails").fetchall()
    conn.close()
    return {r["id"] for r in rows}


def save_crawl_result(status: str, new_emails: int, new_attachments: int, error: str = ""):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO crawl_state (last_crawl_at, status, new_emails, new_attachments, error) VALUES (?, ?, ?, ?, ?)",
        (now, status, new_emails, new_attachments, error),
    )
    conn.commit()
    conn.close()


def save_email(email_id: str, thread_id: str, subject: str, sender: str, received_at: str, file_count: int):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO emails (id, thread_id, subject, sender, received_at, file_count) VALUES (?, ?, ?, ?, ?, ?)",
        (email_id, thread_id, subject, sender, received_at, file_count),
    )
    conn.commit()
    conn.close()


def save_attachment(email_id: str, filename: str, bucket: str, object_key: str, size: int, mime_type: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO attachments (email_id, filename, bucket, object_key, size, mime_type) VALUES (?, ?, ?, ?, ?, ?)",
        (email_id, filename, bucket, object_key, size, mime_type),
    )
    conn.commit()
    conn.close()
