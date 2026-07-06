import hashlib
import json
import os
from datetime import datetime, timezone

from data.silver.pipeline.readers.base import BaseReader
from data.silver.schemas.source import SourceData


class EmailJsonReader(BaseReader):
    """Reads Gmail JSON format exports."""

    def can_handle(self, source: SourceData) -> bool:
        st = source.metadata.get("source_type", "")
        if st == "gmail" or st == "email":
            return True
        try:
            preview = json.loads(source.raw_data[:4096].decode("utf-8", errors="replace"))
            return "id" in preview and "threadId" in preview
        except Exception:
            return False

    def read(self, source: SourceData) -> dict:
        try:
            data = json.loads(source.raw_data.decode("utf-8", errors="replace"))
        except Exception:
            return {"emails": [], "content": ""}

        emails = data if isinstance(data, list) else [data]
        results = []
        for msg in emails:
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            body = self._extract_body(msg)

            result = {
                "email_id": msg.get("id", ""),
                "thread_id": msg.get("threadId", ""),
                "subject": headers.get("subject", ""),
                "body": body,
                "sender_name": headers.get("from", ""),
                "sender_email": headers.get("from", ""),
                "recipients": [{"email": headers.get("to", ""), "type": "to"}],
                "cc": [{"email": headers.get("cc", ""), "type": "cc"}] if headers.get("cc") else [],
                "bcc": [{"email": headers.get("bcc", ""), "type": "bcc"}] if headers.get("bcc") else [],
                "received_at": headers.get("date", ""),
                "message_id": headers.get("message-id", ""),
                "in_reply_to": headers.get("in-reply-to", ""),
                "has_attachments": bool(msg.get("payload", {}).get("parts", [])),
                "attachments": self._extract_attachments(msg),
            }
            results.append(result)

        return {"emails": results}

    def extract_metadata(self, source: SourceData) -> dict:
        checksum = hashlib.sha256(source.raw_data).hexdigest()
        return {
            "checksum": checksum,
            "size_bytes": source.size_bytes,
            "object_key": source.object_key,
            "bucket": source.bucket,
            "source": f"minio://{source.bucket}/{source.object_key}",
            "source_type": "gmail",
        }

    def _extract_body(self, msg: dict) -> str:
        payload = msg.get("payload", {})
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            import base64
            try:
                return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            except Exception:
                return ""
        parts = payload.get("parts", [])
        for part in parts:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                import base64
                try:
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                except Exception:
                    return ""
        return ""

    def _extract_attachments(self, msg: dict) -> list:
        attachments = []
        parts = msg.get("payload", {}).get("parts", [])
        for part in parts:
            if part.get("filename"):
                attachments.append({
                    "filename": part.get("filename", ""),
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                })
        return attachments
