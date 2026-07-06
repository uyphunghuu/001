"""Show processed Silver data."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from data.silver.repositories.base import BaseRepository
from sqlalchemy import text

repo = BaseRepository()
with repo.session as s:
    print('='*70)
    print('  SILVER LAYER - PROCESSED DATA')
    print('='*70)

    rows = s.execute(text("""
        SELECT id, title, source, source_type, checksum, mime_type, size_bytes,
               LENGTH(content) as content_len, LEFT(content, 300) as preview,
               processing_status, created_at
        FROM documents ORDER BY created_at
    """)).fetchall()

    for r in rows:
        print(f'\n{"─"*70}')
        print(f'  📄 Document')
        print(f'{"─"*70}')
        print(f'  ID:             {r[0]}')
        print(f'  Title:          {r[1]}')
        print(f'  Source:         {r[2]}')
        print(f'  Type:           {r[3]}')
        print(f'  MIME:           {r[5]}')
        print(f'  Size:           {r[6]:,} bytes')
        print(f'  Content length: {r[7]:,} chars')
        print(f'  Checksum:       {r[4][:24]}...')
        print(f'  Status:         {r[9]}')
        print(f'  Created:        {r[10]}')
        print(f'\n  📝 Extracted Content (first 300 chars):')
        print(f'  {"─"*50}')
        print(f'{r[8]}')
        print()

    print(f'\n{"="*70}')
    print(f'  Total: {len(rows)} documents')
    print(f'{"="*70}')
