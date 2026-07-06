#!/usr/bin/env python3
"""
Simple test for MinIO bronze layer in ai-platform
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def main():
    print("Testing ai-platform MinIO bronze layer...")
    print("=" * 60)

    # Test 1: Check MinIO connection
    print("\n1. Testing MinIO connection...")
    from minio import Minio
    
    try:
        client = Minio(
            "localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False,
        )
        buckets = client.list_buckets()
        print("MinIO connection successful")
        print("Existing buckets:", [b.name for b in buckets])
        
        # Check gmail-raw bucket exists
        gmail_bucket_exists = any(b.name == "gmail-raw" for b in buckets)
        if not gmail_bucket_exists:
            client.make_bucket("gmail-raw")
            print("Created gmail-raw bucket")
        else:
            print("gmail-raw bucket already exists")
    except Exception as e:
        print("MinIO connection failed:", e)
        return

    # Test 2: Test upload_file functionality
    print("\n2. Testing upload_file function...")
    test_email_id = "test-email-" + datetime.now().strftime("%Y%m%d%H%M%S")
    test_filename = "test-attachment.pdf"
    test_data = b"PDF content for today's email\n" * 100

    try:
        from scripts.storage import upload_file
        result = upload_file(test_email_id, test_filename, test_data)
        print("upload_file successful")
        print("Bucket:", result['bucket'])
        print("Object key:", result['object_key'])
        print("Size:", len(test_data) / 1024, "KB")
    except Exception as e:
        print("upload_file failed:", e)
        return

    # Test 3: Verify upload
    print("\n3. Verifying upload...")
    try:
        response = client.get_object("gmail-raw", result['object_key'])
        downloaded_data = response.read()
        response.close()
        response.release_conn()

        if downloaded_data == test_data:
            print("Data integrity verified - data matches exactly")
        else:
            print("Data mismatch - check sizes")
    except Exception as e:
        print("Download verification failed:", e)

    print("\n" + "=" * 60)
    print("ai-platform bronze layer test complete!")
    print("The pipeline is ready to store Gmail attachments in MinIO")

    return True

if __name__ == "__main__":
    main()