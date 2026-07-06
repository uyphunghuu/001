"""Classify Silver records into Gold node types."""

DOCUMENT_TYPE_MAP = {
    ".docx": ("document", "report"),
    ".doc": ("document", "report"),
    ".pdf": ("document", "report"),
    ".txt": ("document", "note"),
    ".csv": ("resource", "dataset"),
    ".xlsx": ("resource", "spreadsheet"),
    ".xls": ("resource", "spreadsheet"),
    ".json": ("document", "data"),
    ".md": ("document", "note"),
    ".pptx": ("document", "presentation"),
    ".ppt": ("document", "presentation"),
    ".html": ("document", "webpage"),
    ".htm": ("document", "webpage"),
}


def _get_extension(filename: str) -> str:
    import os
    return os.path.splitext(filename.lower())[1]


def classify_document(doc) -> dict:
    ext = _get_extension(doc.title or doc.source_object_id or "")
    doc_type, subtype = DOCUMENT_TYPE_MAP.get(ext, ("document", "generic"))

    meta = doc.metadata_ or {}
    props = {
        "mime_type": doc.mime_type,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "extension": ext,
        "author": doc.author,
        "minio_bucket": doc.minio_bucket,
        "minio_path": doc.minio_path,
        "language": doc.language,
    }
    props = {k: v for k, v in props.items() if v is not None}

    return {
        "type": doc_type,
        "subtype": subtype,
        "name": doc.title or f"Document {doc.source_object_id}",
        "content": doc.content,
        "properties": props,
        "source_ref": {
            "table": "documents",
            "id": str(doc.id),
            "source": doc.source,
            "source_type": doc.source_type,
            "checksum": doc.checksum,
        },
        "effective_start": doc.created_time or doc.processed_at or doc.created_at,
        "status": "active",
        "importance": 1 if doc_type == "resource" else 2,
        "confidence": 0.95,
    }


def classify_communication(comm) -> dict:
    recipients_list = []
    for r in (comm.recipients or []):
        if isinstance(r, dict):
            recipients_list.append({"email": r.get("email", ""), "type": r.get("type", "to")})
        elif isinstance(r, str):
            recipients_list.append({"email": r, "type": "to"})

    cc_list = []
    for c in (comm.cc or []):
        if isinstance(c, dict):
            cc_list.append({"email": c.get("email", ""), "type": "cc"})
        elif isinstance(c, str):
            cc_list.append({"email": c, "type": "cc"})

    return {
        "type": "communication",
        "subtype": "email",
        "name": comm.subject or f"Email {comm.source_object_id}",
        "content": comm.body,
        "properties": {
            "subject": comm.subject,
            "from_name": comm.sender_name,
            "from_email": comm.sender_email,
            "to": recipients_list,
            "cc": cc_list,
            "thread_id": comm.thread_id,
            "has_attachments": comm.has_attachments,
            "attachment_count": comm.attachment_count,
            "message_id": comm.message_id,
            "in_reply_to": comm.in_reply_to,
        },
        "source_ref": {
            "table": "communications",
            "id": str(comm.id),
            "source": comm.source,
            "source_type": comm.source_type,
            "checksum": comm.checksum,
        },
        "effective_start": comm.received_at or comm.sent_at or comm.processed_at or comm.created_at,
        "status": "active",
        "importance": 2,
        "confidence": 0.95,
    }


def classify_event(event) -> dict:
    attendees_list = []
    for a in (event.attendees or []):
        if isinstance(a, dict):
            attendees_list.append({
                "name": a.get("name", "") or a.get("displayName", ""),
                "email": a.get("email", ""),
                "response": a.get("response", "") or a.get("responseStatus", ""),
            })
        elif isinstance(a, str):
            attendees_list.append({"email": a, "name": "", "response": ""})

    props = {
        "location": event.location,
        "start_time": event.start_time.isoformat() if event.start_time else None,
        "end_time": event.end_time.isoformat() if event.end_time else None,
        "is_all_day": event.is_all_day,
        "has_recurrence": bool(event.recurrence),
        "recurrence_rule": event.recurrence,
        "organizer_name": event.organizer_name,
        "organizer_email": event.organizer_email,
        "attendees": attendees_list,
    }
    props = {k: v for k, v in props.items() if v is not None and v != []}

    importance = 1
    if event.organizer_name:
        importance = 2
    if event.organizer_name and (event.start_time and event.end_time):
        importance = 3

    return {
        "type": "activity",
        "subtype": "meeting",
        "name": event.title or f"Event {event.source_object_id}",
        "content": event.description,
        "properties": props,
        "source_ref": {
            "table": "events",
            "id": str(event.id),
            "source": event.source,
            "source_type": event.source_type,
            "checksum": event.checksum,
        },
        "effective_start": event.start_time or event.processed_at or event.created_at,
        "effective_end": event.end_time,
        "status": event.status or "active",
        "importance": importance,
        "confidence": 0.95,
    }
