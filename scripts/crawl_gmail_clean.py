#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.gmail_client import crawl_emails_with_attachments
from scripts.database import (
    init_db, get_all_crawled_email_ids, save_email,
    save_attachment, save_crawl_result, get_last_crawl_time,
)
from scripts.storage import upload_file
def run():
    init_db()

    last_crawl = get_last_crawl_time()
    if last_crawl:
        dt = datetime.fromisoformat(last_crawl)
        query = f"in:inbox after:{dt.strftime('%Y/%m/%d')} has:attachment"
        print(f"Lần crawl trước: {last_crawl}")
    else:
        query = "in:inbox has:attachment"
        print("Lần crawl đầu tiên (toàn bộ inbox)")

    print(f"Query: {query}")
    known_ids = get_all_crawled_email_ids()
    print(f"Đã có {len(known_ids)} emails trong DB")

    try:
        results = crawl_emails_with_attachments(query=query, max_results=200)
    except Exception as e:
        save_crawl_result("failed", 0, 0, error=str(e))
        print(f"Lỗi: {e}")
        return

    new_email_count = 0
    new_file_count = 0

    for email in results:
        if email["id"] in known_ids:
            continue

        file_count = len(email["attachments"])

        save_email(
            email_id=email["id"],
            thread_id=email["thread_id"],
            subject=email["subject"],
            sender=email["from"],
            received_at=email["date"],
            file_count=file_count,
        )
        new_email_count += 1

        for att in email["attachments"]:
            info = upload_file(email["id"], att["filename"], att["data"])
            save_attachment(
                email_id=email["id"],
                filename=att["filename"],
                bucket=info["bucket"],
                object_key=info["object_key"],
                size=att["size"],
                mime_type=att["mime_type"],
            )
            new_file_count += 1

    save_crawl_result("success", new_email_count, new_file_count)
    print(f"\nHoàn tất!")
    print(f"  Email mới: {new_email_count}")
    print(f"  File mới: {new_file_count}")
if __name__ == "__main__":
    run()