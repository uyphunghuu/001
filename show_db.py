"""Show Silver data from PostgreSQL."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from silver.repositories import PostgresRepository
from sqlalchemy import text

repo = PostgresRepository()
with repo.session as s:
    rows = s.execute(text("SELECT id, filename, content_length, LEFT(content, 500) FROM documents ORDER BY created_at")).fetchall()
    print(f'=== {len(rows)} DOCUMENTS ===')
    for r in rows:
        print(f'\nID: {r[0]}')
        print(f'File: {r[1]}')
        print(f'Length: {r[2]} chars')
        print(f'Content (first 500 chars):')
        print(r[3])
        print('---')

    rows = s.execute(text("SELECT COUNT(*) FROM emails")).fetchall()
    print(f'\nEmails: {rows[0][0]}')
    rows = s.execute(text("SELECT COUNT(*) FROM calendar_events")).fetchall()
    print(f'Calendar Events: {rows[0][0]}')
