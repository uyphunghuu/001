"""Verify Silver data — entity schema."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from data.silver.repositories.base import BaseRepository
from sqlalchemy import text

repo = BaseRepository()
with repo.session as s:
    # Counts
    tables = ['documents', 'communications', 'events', 'contacts', 'files', 'processing_logs', 'ingestion_logs', 'knowledge_objects', 'metadata_registry']
    for t in tables:
        try:
            cnt = s.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f'{t}: {cnt}')
        except Exception as e:
            print(f'{t}: ERROR - {e}')

    # Show documents
    rows = s.execute(text("SELECT id, title, source, source_type, LEFT(content, 200), checksum, minio_bucket, minio_path, created_at FROM documents ORDER BY created_at")).fetchall()
    print(f'\n=== {len(rows)} DOCUMENTS ===')
    for r in rows:
        print(f'\nID: {str(r[0])[:8]}...')
        print(f'File: {r[1]}')
        print(f'Source: {r[2]} / {r[3]}')
        print(f'Preview: {r[4]}')
        print(f'Checksum: {str(r[5])[:20]}...')
        print(f'MinIO: {r[6]}/{r[7]}')
        print(f'Created: {r[8]}')
