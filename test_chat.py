import requests
import time
import json

questions = [
    'xin chào',
    'hôm nay có sự kiện gì?',
    'email gần đây nhất?',
    'có tài liệu nào quan trọng?',
    'kế hoạch tuần này?',
    'dự án đang làm gì?',
    'ai là người gửi email nhiều nhất?',
    'công nghệ đang dùng?',
    'deadline sắp tới?',
    'tóm tắt dữ liệu trong hệ thống',
    'cảm ơn',
]

for i, q in enumerate(questions, 1):
    start = time.time()
    try:
        resp = requests.post(
            'http://localhost:8000/chat',
            json={'message': q, 'user_id': 'test'},
            timeout=120,
        )
        elapsed = time.time() - start
        data = resp.json()
        answer = data.get('answer', '')
        truncated = answer[:80] + '...' if len(answer) > 80 else answer
        print(f'[{i}/{len(questions)}] {elapsed:.2f}s - {truncated}')
    except Exception as e:
        print(f'[{i}/{len(questions)}] FAIL: {e}')
