"""Extract calendar events from document content (DOCX schedules).

Silver da xu ly DOCX thanh text, nhung Gold chi luu nguyen van.
Extractor nay doc text content, phat hien lich trinh,
va tao event nodes rieng voi effective_start/day chinh xac.
"""
import re
from datetime import datetime, timedelta
from typing import Optional


# ─── Pattern: Date headers ──────────────────────────────────────────────────

# "Ngay 01/06/2026" or "Ngay 01/06"
RE_DATE_VN = re.compile(r"Ng[àa]y\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?")

# "Thứ Tư - 01/07/2026" or "Thu 2 - 01/07/2026"
RE_THU_VN = re.compile(
    r"Th[ứứ]\s+\S+\s*[-–—]\s*(\d{1,2})/(\d{1,2})/(\d{4})"
)

# Plain "DD/MM/YYYY" at start of line
RE_DATE_PLAIN = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")

# ─── Pattern: Time ranges ───────────────────────────────────────────────────

# "08:30-09:00 | Cong viec" or "08:30 - 09:00 Cong viec" or "08:30 - 09:00 | Cong viec"
RE_TIME_EVENT = re.compile(
    r"(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*[|]?\s*(.+)"
)

# "08:30 | Cong viec" (not a range, just a time + task)
RE_SINGLE_TIME = re.compile(r"^(\d{1,2}):(\d{2})\s*[|]\s*(.+)")


def parse_date(day: int, month: int, year: Optional[int] = None) -> Optional[datetime]:
    if year is None:
        year = 2026
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def extract_events_from_text(
    content: str,
    source_node_id: str,
    source_name: str = "",
) -> list[dict]:
    """Parse document content and extract calendar events.

    Handles 2 formats:
      - Format VN: "Thứ Tư - 01/07/2026" / "08:30 - 09:00 Event title"
      - Format VN2: "Ngày 01/06/2026" / "08:30-09:00 | Event title"
    """
    events = []
    current_date: Optional[datetime] = None
    pending_dates: list[datetime] = []
    in_date_listing = False
    default_year = 2026
    non_date_count = 0  # count consecutive non-date lines after a date listing
    event_pattern_hit = False  # have we seen any time+event line?

    for line_num, line in enumerate(content.split("\n"), 1):
        line = line.strip()
        if not line:
            continue

        # Skip header / separator lines
        lower = line.lower()
        if lower.startswith("lịch") or lower.startswith("mục đích"):
            continue
        if re.match(r"^[-–—=| ]+$", line):
            continue
        if "thời gian" in lower and "công việc" in lower:
            continue

        # Detect date: "Thứ Tư - 01/07/2026"
        m = RE_THU_VN.search(line)
        if m:
            dt = parse_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if dt:
                if in_date_listing or pending_dates:
                    pending_dates.append(dt)
                else:
                    current_date = dt
                continue

        # Detect date: "Ngày 01/06/2026" or "Ngay 01/06/2026"
        m = RE_DATE_VN.search(line)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            year = int(m.group(3)) if m.group(3) else default_year
            dt = parse_date(day, month, year)
            if dt:
                if event_pattern_hit and not in_date_listing:
                    current_date = dt
                else:
                    pending_dates.append(dt)
                    in_date_listing = True
                continue

        # Detect date: "DD/MM/YYYY" at line start
        m = RE_DATE_PLAIN.match(line)
        if m:
            dt = parse_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if dt:
                current_date = dt
                continue

        # Parse time range + event
        m = RE_TIME_EVENT.match(line)
        if m:
            start_h, start_m = int(m.group(1)), int(m.group(2))
            end_h, end_m = int(m.group(3)), int(m.group(4))
            title = m.group(5).strip()
            event_pattern_hit = True

            # Choose dates: pending (date-list format) or current_date
            target_dates = pending_dates if pending_dates else [current_date]
            target_dates = [d for d in target_dates if d is not None]
            if not target_dates:
                continue

            for target_date in target_dates:
                event_start = target_date.replace(hour=start_h, minute=start_m)
                event_end = target_date.replace(hour=end_h, minute=end_m)
                if event_end <= event_start:
                    event_end += timedelta(hours=1)

                events.append({
                    "type": "event",
                    "subtype": "calendar_entry",
                    "name": title,
                    "summary": title,
                    "content": f"{title}\nSource: {source_name}\nLine: {line_num}",
                    "effective_start": event_start.isoformat(),
                    "effective_end": event_end.isoformat(),
                    "importance": 2,
                    "status": "active",
                    "properties": {
                        "source_document_id": source_node_id,
                        "source_document_name": source_name,
                        "line_number": line_num,
                        "raw_text": line,
                        "duration_minutes": int((event_end - event_start).total_seconds() / 60),
                    },
                    "source_ref": {
                        "table": "gold_nodes",
                        "id": source_node_id,
                    },
                })

            if pending_dates:
                current_date = pending_dates[0]
                pending_dates.clear()
            continue

        # Lines without time under a date (e.g. "Sprint Planning")
        if not re.match(r"^\d", line) and len(line) > 3:
            target_date = current_date
            # If we have pending dates, this task applies to the first one
            if pending_dates and not event_pattern_hit:
                target_date = pending_dates[0]
            if target_date and not any(skip in lower for skip in ["nghỉ", "tự học", "đọc sách", "đọc tài liệu", "gym"]):
                events.append({
                    "type": "event",
                    "subtype": "calendar_entry",
                    "name": line,
                    "summary": line,
                    "content": f"{line}\nSource: {source_name}\nLine: {line_num}",
                    "effective_start": target_date.isoformat(),
                    "effective_end": None,
                    "importance": 1,
                    "status": "tentative",
                    "properties": {
                        "source_document_id": source_node_id,
                        "source_document_name": source_name,
                        "line_number": line_num,
                        "raw_text": line,
                        "no_time": True,
                    },
                    "source_ref": {
                        "table": "gold_nodes",
                        "id": source_node_id,
                    },
                })

    # Dedup by (date, name) - same event may appear in repeated blocks
    seen = set()
    deduped = []
    for e in events:
        key = (e["effective_start"][:19], e["name"])
        if key not in seen:
            seen.add(key)
            deduped.append(e)
    return deduped
