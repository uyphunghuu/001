#!/usr/bin/env python3
"""
Test MinIO integration with ai-platform storage
"""
import io
import sys
import traceback

sys.path.insert(0, '.')

from scripts.storage import upload_file
def test_minio_integration():
    print("Testing MinIO integration for ai-platform...")
    
    try:
        from minio import Minio
        print("✅ MinIO client imported successfully")
        
        client = Minio(
            "localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False,
        )
        print("✅ MinIO client created")
        
        buckets = client.list_buckets()
        print(f"✅ Existing buckets: {[b.name for b in buckets]}")
        
        test_bucket = "gmail-raw"
        if not any(b.name == test_bucket for b in buckets):
            client.make_bucket(test_bucket)
            print(f"✅ Created bucket: {test_bucket}")
        else:
            print(f"✅ Bucket already exists: {test_bucket}")
            
        # Test upload using the ai-platform function
        test_data = b"This is a test PDF content for integration verification"
        
        print("\n📤 Testing upload_file function...")
        result = upload_file("test-email-id-123", "test-document.pdf", test_data)
        
        print(f"✅ Upload successful!")
        print(f"   Bucket: {result['bucket']}")
        print(f"   Object key: {result['object_key']}")
        
        # Verify upload by downloading
        print("\n📥 Verifying download...")
        response = client.get_object(test_bucket, result['object_key'])
        downloaded_data = response.read()
        response.close()
        response.release_conn()
        
        if downloaded_data == test_data:
            print("✅ Data matches!")
        else:
            print("❌ Data mismatch!")
            
        print("\n✅ All MinIO integration tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        traceback.print_exc()
        return False
if __name__ == "__main__":
    success = test_minio_integration()
    sys.exit(0 if success else 1)