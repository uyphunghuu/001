#!/usr/bin/env python3
"""
View Silver layer data from PostgreSQL (or fallback to SQLite + JSONL).
"""
import json
import os
import sys
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def print_header(title):
    print()
    print("=" * 70)
    print("  %s" % title)
    print("=" * 70)


def print_row(label, value):
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value[:10])
        if len(value) > 80:
            value = value[:80] + "..."
    print("  %-20s %s" % (label + ":", str(value)))


def view_from_postgres():
    from scripts.database_pg import get_conn, put_conn

    conn = get_conn()
    c = conn.cursor()

    # Pipeline runs
    c.execute("SELECT id, run_at, status, processed, failed FROM silver_processing ORDER BY id DESC")
    runs = c.fetchall()
    if runs:
        print_header("Pipeline Runs")
        for r in runs:
            print("  Run #%d | %s | %s | processed=%d failed=%d" % r)

    # Records
    c.execute("""
        SELECT email_id, subject, sender_name, sender_email,
               received_at, content_type, language,
               attachment_count, total_text_length, keyword_count,
               processed_at
        FROM silver_records ORDER BY received_at DESC
    """)
    records = c.fetchall()
    if records:
        print_header("Silver Records (%d total)" % len(records))
        for row in records:
            print()
            print("  Email: %s" % row[0])
            print("  Subject: %s" % row[1])
            print("  From: %s <%s>" % (row[2], row[3]))
            print("  Received: %s" % row[4])
            print("  Type: %s | Lang: %s | Attachments: %d" % (row[5], row[6], row[7]))
            print("  Text: %d chars | Keywords: %d" % (row[8], row[9]))
            print("  Processed: %s" % row[10])

    # Attachments
    c.execute("""
        SELECT email_id, filename, file_category, language, size_kb,
               text_length, text_word_count, content_type, keywords, content_hash
        FROM silver_attachments ORDER BY email_id
    """)
    attachments = c.fetchall()
    if attachments:
        print_header("Attachments (%d total)" % len(attachments))
        for row in attachments:
            print()
            print("  %s / %s" % (row[0], row[1]))
            print("  Category: %s | Lang: %s | Size: %.2f KB" % (row[2], row[3], row[4] if row[4] else 0))
            print("  Text: %d chars | Words: %d | Type: %s" % (row[5], row[6], row[7]))
            print("  Keywords: %s" % (", ".join(row[8][:5]) if row[8] else "none"))
            print("  Hash: %s" % (row[9][:20] + "..." if row[9] else ""))

    # Chunks
    c.execute("SELECT COUNT(1), SUM(length) FROM silver_chunks")
    chunk_count, chunk_total = c.fetchone()
    if chunk_count:
        print_header("Chunks")
        print("  Total chunks: %d | Total size: %d chars" % (chunk_count, chunk_total or 0))

        c.execute("""
            SELECT email_id, chunk_index, LEFT(text, 120), length
            FROM silver_chunks ORDER BY email_id, chunk_index LIMIT 10
        """)
        for row in c.fetchall():
            print()
            print("  [%s chunk:%d] (%d chars)" % (row[0], row[1], row[3]))
            print("    %s..." % row[2].replace("\n", " | "))

    put_conn(conn)


def view_from_jsonl():
    silver_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "silver"
    )

    if not os.path.exists(silver_dir):
        print("No silver data found at: %s" % silver_dir)
        return

    # Records
    records_path = os.path.join(silver_dir, "records.jsonl")
    if os.path.exists(records_path):
        records = []
        with open(records_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))

        print_header("Silver Records (%d total) - JSONL backup" % len(records))
        for rec in records:
            print()
            print("  Email: %s" % rec.get("email_id", ""))
            print("  Subject: %s" % rec.get("subject", ""))
            sender = rec.get("sender", {})
            print("  From: %s <%s>" % (sender.get("name", ""), sender.get("email", "")))
            print("  Received: %s" % rec.get("received_at", ""))
            print("  Type: %s | Lang: %s" % (rec.get("content_type", ""), rec.get("language", "")))
            print("  Attachments: %d | Text: %d chars" % (
                rec.get("attachment_count", 0), rec.get("total_text_length", 0)
            ))

    # Attachments
    att_path = os.path.join(silver_dir, "attachments.jsonl")
    if os.path.exists(att_path):
        attachments = []
        with open(att_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    attachments.append(json.loads(line))

        print_header("Attachments (%d total) - JSONL backup" % len(attachments))
        for att in attachments:
            print()
            print("  %s / %s" % (att.get("email_id", ""), att.get("filename", "")))
            print("  Category: %s | Lang: %s | Size: %.2f KB" % (
                att.get("file_category", ""), att.get("language", ""), att.get("size_kb", 0)
            ))
            print("  Text: %d chars | Words: %d | Hash: %s" % (
                att.get("text_length", 0), att.get("text_word_count", 0),
                (att.get("content_hash", "")[:16] + "...") if att.get("content_hash") else ""
            ))
            print("  Keywords: %s" % (", ".join(att.get("keywords", [])[:5]) or "none"))

    # Chunks
    chunks_path = os.path.join(silver_dir, "chunks.jsonl")
    if os.path.exists(chunks_path):
        chunks = []
        with open(chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    chunks.append(json.loads(line))
        print_header("Chunks (%d total) - JSONL backup" % len(chunks))
        total_chars = sum(c.get("length", 0) for c in chunks)
        print("  Total size: %d chars" % total_chars)
        for c in chunks[:5]:
            text_preview = c.get("text", "").replace("\n", " | ")[:100]
            print("  [%s chunk:%d] %s..." % (c.get("email_id", ""), c.get("chunk_index", 0), text_preview))

    # Extracted text files
    text_dir = os.path.join(silver_dir, "extracted_text")
    if os.path.exists(text_dir):
        files = [f for f in os.listdir(text_dir) if f.endswith(".txt")]
        if files:
            print_header("Extracted Text Files")
            for fname in files:
                fpath = os.path.join(text_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                preview = content[:200].replace("\n", " | ")
                print()
                print("  %s (%d chars)" % (fname, len(content)))
                print("  %s..." % preview)


def view_compare():
    """Show Bronze vs Silver side by side for each email."""
    from scripts.database import get_conn as sqlite_conn

    print_header("Bronze vs Silver Comparison")

    conn = sqlite_conn()
    emails = [dict(r) for r in conn.execute("SELECT * FROM emails").fetchall()]
    conn.close()

    if not emails:
        print("  No Bronze data found.")
        return

    for email in emails:
        print()
        print("  Email: %s" % email["id"])
        print("  " + "-" * 60)
        print("  BRONZE:")
        print("    subject:     %s" % email.get("subject", ""))
        print("    sender:      %s" % email.get("sender", ""))
        print("    received_at: %s" % email.get("received_at", ""))
        print("    files:       %d" % email.get("file_count", 0))

        # Try to get silver version
        try:
            from scripts.database_pg import get_conn as pg_conn, put_conn
            conn2 = pg_conn()
            c = conn2.cursor()
            c.execute(
                "SELECT subject, sender_name, sender_email, received_at, content_type, language FROM silver_records WHERE email_id = %s",
                (email["id"],),
            )
            row = c.fetchone()
            if row:
                print("  SILVER (PostgreSQL):")
                print("    subject:     %s" % row[0])
                print("    sender:      %s <%s>" % (row[1], row[2]))
                print("    received_at: %s" % row[3])
                print("    type:        %s" % row[4])
                print("    language:    %s" % row[5])
            put_conn(conn2)
        except Exception:
            pass

        # Check JSONL
        silver_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data", "silver"
        )
        records_path = os.path.join(silver_dir, "records.jsonl")
        if os.path.exists(records_path):
            with open(records_path, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    if rec.get("email_id") == email["id"]:
                        print("  SILVER (JSONL):")
                        print("    subject:     %s" % rec.get("subject", ""))
                        print("    type:        %s" % rec.get("content_type", ""))
                        print("    language:    %s" % rec.get("language", ""))
                        break


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="View Silver layer data")
    parser.add_argument(
        "source", nargs="?", default="auto",
        choices=["postgres", "jsonl", "compare", "auto"],
        help="Data source: postgres, jsonl, compare, or auto (default)"
    )
    parser.add_argument("--limit", type=int, default=20, help="Max records to show")

    args = parser.parse_args()

    if args.source == "compare":
        view_compare()
    elif args.source == "jsonl":
        view_from_jsonl()
    elif args.source == "postgres":
        view_from_postgres()
    else:
        # auto: try postgres first
        try:
            view_from_postgres()
        except Exception as e:
            print("PostgreSQL unavailable (%s), falling back to JSONL..." % e)
            view_from_jsonl()
