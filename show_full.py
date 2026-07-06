"""Show actual processed data in full."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from data.silver.repositories.base import BaseRepository
from sqlalchemy import text

repo = BaseRepository()
with repo.session as s:
    rows = s.execute(text("""
        SELECT title, content, checksum, size_bytes, mime_type,
               minio_bucket, minio_path, created_at, metadata::text
        FROM documents ORDER BY created_at
    """)).fetchall()

    for r in rows:
        print(f'{"="*70}')
        print(f'  FILE: {r[0]}')
        print(f'  Checksum: {r[2]}')
        print(f'  Size: {r[3]:,} bytes')
        print(f'  MinIO: {r[5]}/{r[6]}')
        print(f'  Created: {r[7]}')
        print(f'{"="*70}')
        print()
        print(r[1])
        print()
