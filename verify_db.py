"""Verify Silver data in PostgreSQL with proper encoding handling."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from silver.repositories import PostgresRepository
from sqlalchemy import text

repo = PostgresRepository()
with repo.session as s:
    rows = s.execute(text('SELECT id, filename, content_length, LEFT(content, 80) FROM documents')).fetchall()
    print(f'Documents: {len(rows)}')
    for r in rows:
        print(f'  ID={r[0]}, file={r[1]}, len={r[2]}')
        print(f'  Preview: {r[3]}')

    rows = s.execute(text('SELECT COUNT(*) FROM emails')).fetchall()
    print(f'\nEmails: {rows[0][0]}')

    rows = s.execute(text('SELECT COUNT(*) FROM calendar_events')).fetchall()
    print(f'Calendar Events: {rows[0][0]}')

    rows = s.execute(text('SELECT id, status FROM pipeline_runs')).fetchall()
    print(f'\nPipeline runs: {len(rows)}')
    for r in rows:
        print(f'  ID={r[0]}, status={r[1]}')
