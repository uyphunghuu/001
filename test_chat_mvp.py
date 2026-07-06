#!/usr/bin/env python3
"""Test script cho MVP chat API."""
import urllib.request
import json
import time
import sys

BASE_URL = "http://localhost:8001/chat"

def chat(msg, label=""):
    try:
        data = json.dumps({"message": msg}).encode("utf-8")
        req = urllib.request.Request(
            BASE_URL, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode("utf-8"))
            answer = res["answer"]
            sources = res["sources"]
            print(f"Q: {label or msg}")
            print(f"A: {answer[:500]}")
            src_names = [s['name'][:50] for s in sources[:3]]
            print(f"Sources ({len(sources)}): {src_names}")
            print("-" * 60)
            time.sleep(1)  # tránh rate limit
            return res
    except Exception as e:
        print(f"Q: {label or msg}")
        print(f"ERROR: {e}")
        print("-" * 60)
        return None


print("=" * 60)
print("  MVP CHAT TEST — AI Platform")
print("=" * 60)
print()

# 1. Lịch trình hôm nay
chat("hom nay toi co lich gi?", "Hôm nay có lịch gì?")

# 2. Cuộc họp quan trọng
chat("cuoc hop nao quan trong nhat tuan nay?", "Cuộc họp quan trọng nhất tuần này?")

# 3. Hỏi về người liên lạc
chat("toi thuong lien lac voi ai nhat?", "Tôi thường liên lạc với ai nhất?")

# 4. Hỏi về deadline / công việc cụ thể
chat("toi can hoan thanh nhung viec gi truoc cuoi thang?", "Cần hoàn thành gì trước cuối tháng?")

# 5. Tóm tắt tài liệu
chat("tom tat noi dung lich lam viec thang 6", "Tóm tắt lịch làm việc tháng 6?")

# 6. Hỏi về email cụ thể
chat("co email nao lien quan den bao mat khong?", "Email liên quan bảo mật?")

# 7. Hỏi tổng quan
chat("tuan nay toi da lam gi?", "Tuần này đã làm gì?")

# 8. Câu hỏi không có trong dữ liệu
chat("thoi tiet ha noi hom nay the nao?", "Thời tiết Hà Nội hôm nay? (ngoài data)")

print()
print("Done.")
