import base64
import os
import sys
from typing import List, Optional

from googleapiclient.discovery import build

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.auth import authenticate


def get_service():
    creds = authenticate()
    return build("gmail", "v1", credentials=creds)


def search_messages(service, query: str, max_results: int = 200) -> List[dict]:
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


def get_message_full(service, msg_id: str) -> dict:
    return service.users().messages().get(
        userId="me", id=msg_id, format="full"
    ).execute()


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}


def get_attachments(service, msg_id: str, parts: list, parent_dir: str = "") -> List[dict]:
    attachments = []
    for part in parts:
        filename = part.get("filename", "")
        ext = os.path.splitext(filename.lower())[1]
        data = part.get("body", {})
        attachment_id = data.get("attachmentId")

        if attachment_id and ext in ALLOWED_EXTENSIONS:
            att = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=attachment_id
            ).execute()

            raw_bytes = base64.urlsafe_b64decode(att["data"])
            attachments.append({
                "filename": filename,
                "mime_type": part.get("mimeType", ""),
                "size": att.get("size", 0),
                "data": raw_bytes,
            })

        if "parts" in part:
            attachments.extend(
                get_attachments(service, msg_id, part["parts"], parent_dir)
            )
    return attachments


def crawl_emails_with_attachments(query: str, max_results: int = 200) -> List[dict]:
    service = get_service()

    print(f"  Searching: {query}")
    msg_refs = search_messages(service, query, max_results)
    print(f"  Found {len(msg_refs)} messages")

    results = []

    for i, ref in enumerate(msg_refs):
        msg = get_message_full(service, ref["id"])
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "(No Subject)")
        sender = headers.get("From", "")

        payload = msg["payload"]
        all_parts = payload.get("parts", [])
        attachments = get_attachments(service, ref["id"], all_parts)

        file_list = []
        for att in attachments:
            file_list.append({
                "filename": att["filename"],
                "data": att["data"],
                "size": att["size"],
                "mime_type": att["mime_type"],
            })

        if file_list:
            print(f"    [{i+1}] {subject[:60]} -> {len(file_list)} file(s)")
            for f in file_list:
                print(f"          {f['filename']} ({f['size']/1024:.1f} KB)")

        results.append({
            "id": ref["id"],
            "thread_id": msg.get("threadId", ""),
            "subject": subject,
            "from": sender,
            "date": headers.get("Date", ""),
            "attachments": file_list,
        })

    return results
