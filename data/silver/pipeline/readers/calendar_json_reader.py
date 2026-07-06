import hashlib
import json
import os
from datetime import datetime, timezone

from data.silver.pipeline.readers.base import BaseReader
from data.silver.schemas.source import SourceData


class CalendarJsonReader(BaseReader):
    """Reads Google Calendar JSON exports."""

    def can_handle(self, source: SourceData) -> bool:
        st = source.metadata.get("source_type", "")
        if st == "calendar":
            return True
        try:
            preview = json.loads(source.raw_data[:4096].decode("utf-8", errors="replace"))
            return "summary" in preview or "items" in preview
        except Exception:
            return False

    def read(self, source: SourceData) -> dict:
        try:
            data = json.loads(source.raw_data.decode("utf-8", errors="replace"))
        except Exception:
            return {"events": []}

        items = data.get("items", [data])
        results = []
        for item in items:
            result = {
                "event_id": item.get("id", ""),
                "title": item.get("summary", ""),
                "description": item.get("description", ""),
                "location": item.get("location", ""),
                "organizer_name": item.get("organizer", {}).get("displayName", ""),
                "organizer_email": item.get("organizer", {}).get("email", ""),
                "attendees": [
                    {"name": a.get("displayName", ""), "email": a.get("email", ""), "response": a.get("responseStatus", "")}
                    for a in item.get("attendees", [])
                ],
                "start_time": item.get("start", {}).get("dateTime") or item.get("start", {}).get("date"),
                "end_time": item.get("end", {}).get("dateTime") or item.get("end", {}).get("date"),
                "is_all_day": "date" in item.get("start", {}),
                "recurrence": item.get("recurrence", []),
                "status": item.get("status", "confirmed"),
            }
            results.append(result)

        return {"events": results}

    def extract_metadata(self, source: SourceData) -> dict:
        checksum = hashlib.sha256(source.raw_data).hexdigest()
        return {
            "checksum": checksum,
            "size_bytes": source.size_bytes,
            "object_key": source.object_key,
            "bucket": source.bucket,
            "source": f"minio://{source.bucket}/{source.object_key}",
            "source_type": "google_calendar",
        }
