#!/usr/bin/env python3
"""
Gmail → MinIO (Bronze Layer)
Fetches emails from Gmail API, uploads full message JSON + attachments to MinIO.
The Silver pipeline (run_silver.py --source minio) then picks these up.
"""
import io
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from googleapiclient.discovery import build
from minio import Minio

from scripts.auth import authenticate

BUCKET = "gmail-raw"
MINIO_EP = "localhost:9000"
MINIO_AK = "minioadmin"
MINIO_SK = "minioadmin"


def get_gmail_service():
    return build("gmail", "v1", credentials=authenticate())


def get_minio():
    return Minio(MINIO_EP, access_key=MINIO_AK, secret_key=MINIO_SK, secure=False)


def search_messages(service, query: str, max_results: int = 200):
    messages = []
    page_token = None
    while True:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=min(max_results, 500),
            pageToken=page_token
        ).execute()
        messages.extend(result.get("messages", []))
        page_token = result.get("nextPageToken")
        if not page_token or len(messages) >= max_results:
            break
    return messages


def get_attachments(service, msg_id: str, parts: list):
    attachments = []
    allowed = {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".xls", ".csv", ".pptx"}
    for part in parts:
        filename = part.get("filename", "")
        ext = os.path.splitext(filename.lower())[1]
        data = part.get("body", {})
        attachment_id = data.get("attachmentId")

        if attachment_id and ext in allowed:
            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()
            import base64
            raw_bytes = base64.urlsafe_b64decode(att["data"])
            attachments.append({
                "filename": filename,
                "mime_type": part.get("mimeType", ""),
                "size": att.get("size", 0),
                "data": raw_bytes,
            })

        if "parts" in part:
            attachments.extend(get_attachments(service, msg_id, part["parts"]))
    return attachments


def upload_to_minio(minio, email_id: str, object_key: str, data: bytes, content_type: str):
    if not minio.bucket_exists(BUCKET):
        minio.make_bucket(BUCKET)
    minio.put_object(
        BUCKET, object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def email_exists(minio, email_id: str) -> bool:
    try:
        minio.stat_object(BUCKET, f"{email_id}/email.json")
        return True
    except Exception:
        return False


def run(query: str = "in:inbox has:attachment", max_results: int = 200):
    service = get_gmail_service()
    minio = get_minio()

    print(f"Searching: {query}")
    msg_refs = search_messages(service, query, max_results)
    print(f"Found {len(msg_refs)} messages")

    new_emails = 0
    new_attachments = 0

    for i, ref in enumerate(msg_refs):
        email_id = ref["id"]

        if email_exists(minio, email_id):
            print(f"  [{i+1}] {email_id} — already in MinIO, skip")
            continue

        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "(No Subject)")[:60]

        # Upload full message JSON
        raw_json = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        upload_to_minio(minio, email_id, f"{email_id}/email.json", raw_json, "application/json")
        new_emails += 1

        # Download and upload attachments
        all_parts = msg["payload"].get("parts", [])
        attachments = get_attachments(service, email_id, all_parts)

        for att in attachments:
            upload_to_minio(
                minio, email_id,
                f"{email_id}/{att['filename']}",
                att["data"],
                att["mime_type"],
            )
            new_attachments += 1

        print(f"  [{i+1}] {subject} ({email_id}) — email.json + {len(attachments)} attachment(s)")

    print(f"\nDone! New: {new_emails} emails, {new_attachments} attachments")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gmail → MinIO")
    parser.add_argument("--query", default="in:inbox has:attachment",
                        help="Gmail search query")
    parser.add_argument("--max-results", type=int, default=200)
    args = parser.parse_args()
    run(args.query, args.max_results)
