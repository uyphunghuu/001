"""Show each normalization step for Silver pipeline."""
import sys, os, json, io, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from minio import Minio

# ── STEP 0: Read raw from MinIO ──
print('='*70)
print('  STEP 0: BRONZE RAW DATA (MinIO)')
print('='*70)

client = Minio('localhost:9000', access_key='minioadmin', secret_key='minioadmin', secure=False)
resp = client.get_object('gmail-raw', '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx')
raw_bytes = resp.read()
resp.close(); resp.release_conn()

print(f'  File: LỊCH LÀM VIỆC THÁNG 07.docx')
print(f'  Size: {len(raw_bytes):,} bytes')
print(f'  Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document')
print(f'  SHA256: {hashlib.sha256(raw_bytes).hexdigest()}')
print()

# ── STEP 1: Reader (DOCX → raw text) ──
print('='*70)
print('  STEP 1: READER (python-docx extract)')
print('='*70)

from docx import Document as DocxDoc
doc = DocxDoc(io.BytesIO(raw_bytes))
paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
tables = []
for t in doc.tables:
    for row in t.rows:
        cells = [c.text.strip() for c in row.cells]
        tables.append(' | '.join(cells))

raw_text = '\n'.join(paragraphs)
if tables:
    raw_text += '\n\n' + '\n'.join(tables)

print(f'  Paragraphs: {len(paragraphs)}')
print(f'  Tables: {len(tables)}')
print(f'  Raw text length: {len(raw_text):,} chars')
print(f'\n  📝 Raw text (first 400 chars):')
print(f'  {"─"*50}')
print(raw_text[:400])
print()

# ── STEP 2: Cleaner ──
print('='*70)
print('  STEP 2: TEXT CLEANER')
print('='*70)

from data.silver.pipeline.cleaners import TextCleaner
cleaner = TextCleaner()

# Show each sub-step
step1 = cleaner._remove_html(raw_text)
step2 = cleaner._normalize_unicode(step1)
step3 = cleaner._normalize_newlines(step2)
step4 = cleaner._remove_control_chars(step3)
step5 = cleaner._normalize_punctuation(step4)
step6 = cleaner._normalize_whitespace(step5)

print(f'  After HTML removal:     {len(step1):,} chars')
print(f'  After Unicode NFC:      {len(step2):,} chars')
print(f'  After newline normalize: {len(step3):,} chars')
print(f'  After control char rm:   {len(step4):,} chars')
print(f'  After punctuation norm:  {len(step5):,} chars')
print(f'  After whitespace norm:   {len(step6):,} chars')
print(f'\n  📝 Cleaned text (first 400 chars):')
print(f'  {"─"*50}')
print(step6[:400])
print()

# ── STEP 3: Normalizer ──
print('='*70)
print('  STEP 3: NORMALIZER (document)')
print('='*70)

normalized = {
    'source': 'gmail-raw',
    'source_type': 'document',
    'source_object_id': '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx',
    'title': 'LỊCH LÀM VIỆC THÁNG 07.docx',
    'content': step6,
    'checksum': hashlib.sha256(raw_bytes).hexdigest(),
    'mime_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'size_bytes': len(raw_bytes),
    'minio_bucket': 'gmail-raw',
    'minio_path': '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx',
    'language': 'vi',
    'page_count': None,
    'author': None,
    'created_time': None,
    'updated_time': None,
    'processing_status': 'completed',
    'metadata': {},
}

print(f'  Final normalized fields: {len(normalized)}')
print(f'  Title:        {normalized["title"]}')
print(f'  Source:       {normalized["source"]}')
print(f'  Content len:  {len(normalized["content"]):,} chars')
print(f'  Checksum:     {normalized["checksum"][:24]}...')
print()

# ── STEP 4: PostgreSQL ──
print('='*70)
print('  STEP 4: POSTGRESQL (saved data)')
print('='*70)

from data.silver.repositories.base import BaseRepository
from sqlalchemy import text

repo = BaseRepository()
with repo.session as s:
    rows = s.execute(text("""
        SELECT id, title, source, source_type, checksum,
               LENGTH(content) as content_len,
               LEFT(content, 300) as preview,
               minio_bucket, minio_path, created_at
        FROM documents
        WHERE title LIKE 'LỊCH%'
        ORDER BY created_at DESC LIMIT 1
    """)).fetchall()

    if rows:
        r = rows[0]
        print(f'  ID:           {r[0]}')
        print(f'  Title:        {r[1]}')
        print(f'  Source:       {r[2]}')
        print(f'  Checksum:     {str(r[4])[:24]}...')
        print(f'  Content len:  {r[5]:,} chars')
        print(f'  MinIO:        {r[7]}/{r[8]}')
        print(f'  Created:      {r[9]}')
        print(f'\n  📝 Final content in DB (first 500 chars):')
        print(f'  {"─"*50}')
        print(r[6])
        print()

print('='*70)
print('  ✅ PIPELINE COMPLETE')
print(f'  Total chars extracted: {len(raw_text):,} → cleaned: {len(step6):,}')
print(f'  Compression ratio: {len(raw_text)/len(step6):.1f}x')
print('='*70)
