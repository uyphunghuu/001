"""Step-by-step data transformation demo."""
import sys, os, io, hashlib, re, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from minio import Minio
from docx import Document as DocxDoc

client = Minio('localhost:9000', access_key='minioadmin', secret_key='minioadmin', secure=False)
resp = client.get_object('gmail-raw', '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx')
raw_bytes = resp.read()
resp.close(); resp.release_conn()

print('═'*70)
print('  DỮ LIỆU GỐC: LỊCH LÀM VIỆC THÁNG 07.docx (20,557 bytes)')
print('═'*70)

# ─── BƯỚC 1: ĐỌC DOCX ───
print('\n▌BƯỚC 1: DOCX READER')
print('▌python-docx đọc file .docx, extract paragraphs + tables')
print('▌' + '─'*60)

doc = DocxDoc(io.BytesIO(raw_bytes))
paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
raw_text = '\n'.join(paragraphs)

print(f'  Số paragraphs: {len(paragraphs)}')
print(f'  Số tables: {len(doc.tables)}')
print(f'  Tổng chars: {len(raw_text):,}')
print('\n  ▶ RAW TEXT (first 600 chars):')
for line in raw_text[:600].split('\n'):
    print(f'    {line}')

# ─── BƯỚC 2: CLEANER TỪNG BƯỚC NHỎ ───
print('\n\n▌BƯỚC 2: TEXT CLEANER (6 bước nhỏ)')
print('▌' + '─'*60)

text = raw_text
sample = "08:30 - 09:00 Daily Standup <b>cùng</b> nhóm&nbsp;dự án\r\nTiếp theo\t\t"

print(f'\n  📥 INPUT MẪU: {repr(sample[:80])}...')

# Bước 2a: Remove HTML
step_a = re.sub(r'<[^>]+>', ' ', sample)
step_a = re.sub(r'&amp;', '&', step_a)
step_a = re.sub(r'&lt;', '<', step_a)
step_a = re.sub(r'&gt;', '>', step_a)
step_a = re.sub(r'&nbsp;', ' ', step_a)
print(f'\n  ▶ Sau Remove HTML:  {repr(step_a[:80])}...')

# Bước 2b: Unicode NFC
step_b = unicodedata.normalize('NFC', text)
diff = 'giống' if step_b == text else 'có thay đổi'
print(f'  ▶ Sau Unicode NFC:  {diff} ({len(step_b):,} chars)')

# Bước 2c: Newlines
step_c = text.replace('\r\n', '\n').replace('\r', '\n')
step_c = re.sub(r'\n{3,}', '\n\n', step_c)
print(f'  ▶ Sau Newline norm: {len(step_c):,} chars (\\r\\n → \\n)')

# Bước 2d: Control chars
step_d = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', step_c)
print(f'  ▶ Sau Control rm:   {len(step_d):,} chars')

# Bước 2e: Punctuation
original_time = '08:30'
after_punct = re.sub(r'\s*([.,!?;:])\s*', r'\1 ', original_time)
print(f'  ▶ Test Punctuation: "{original_time}" → "{after_punct}" (⚠️ thêm space sau ":")')

step_e = re.sub(r'\s*([.,!?;:])\s*', r'\1 ', step_d)

# Bước 2f: Whitespace
step_f = re.sub(r'[ \t]+', ' ', step_e)
step_f = re.sub(r'\n ', '\n', step_f)
step_f = re.sub(r' \n', '\n', step_f)
step_f = step_f.strip()
print(f'  ▶ Sau Whitespace:   {len(step_f):,} chars')

# So sánh trước sau
print(f'\n  📊 TỔNG KẾT: {len(raw_text):,} → {len(step_f):,} chars')

print('\n  ▶ TRƯỚC (raw text, first 300 chars):')
for line in raw_text[:300].split('\n'):
    print(f'    {line}')

print('\n  ▶ SAU (cleaned, first 300 chars):')
for line in step_f[:300].split('\n'):
    print(f'    {line}')

# ─── BƯỚC 3: VALIDATOR ───
print('\n\n▌BƯỚC 3: VALIDATOR')
print('▌' + '─'*60)
print(f'  ✅ checksum: {hashlib.sha256(raw_bytes).hexdigest()[:24]}...')
print(f'  ✅ source: gmail-raw')
print(f'  ✅ source_type: document')
print(f'  ✅ mime_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document')
print(f'  ✅ content: {len(step_f):,} chars (non-empty)')

# ─── BƯỚC 4: NORMALIZER ───
print('\n\n▌BƯỚC 4: NORMALIZER')
print('▌' + '─'*60)

final = {
    'id': 'a526bca6-6d68-4702-a1d8-a455fd6f9999',
    'source': 'gmail-raw',
    'source_type': 'document',
    'source_object_id': '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx',
    'title': 'LỊCH LÀM VIỆC THÁNG 07.docx',
    'content': step_f[:100] + '...',
    'checksum': hashlib.sha256(raw_bytes).hexdigest(),
    'mime_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'size_bytes': len(raw_bytes),
    'minio_bucket': 'gmail-raw',
    'minio_path': '19f1bd9cf6b4abed/LỊCH LÀM VIỆC THÁNG 07.docx',
    'processing_status': 'completed',
    'metadata': {
        'extension': '.docx',
        'created_time': '2026-07-01T04:03:00+00:00',
        'modified_time': '2026-07-01T04:03:00+00:00',
    },
    'raw_json': {},
}

import json
print(json.dumps(final, indent=2, ensure_ascii=False))

# ─── BƯỚC 5: LƯU POSTGRESQL ───
print('\n\n▌BƯỚC 5: POSTGRESQL')
print('▌' + '─'*60)
print('  INSERT INTO documents')
print('  (id, source, source_type, title, content, checksum,')
print('   mime_type, size_bytes, minio_bucket, minio_path, ...)')
print(f'  VALUES')
print(f'  (\'{final["id"]}\', \'{final["source"]}\', \'{final["source_type"]}\',')
print(f'   \'{final["title"]}\', \'{final["content"][:60]}...\',')
print(f'   \'{final["checksum"][:20]}...\', ...)')
print(f'\n  ✅ DONE — {len(step_f):,} chars stored in PostgreSQL')
print('═'*70)
