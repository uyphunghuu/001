import io
import os

from minio import Minio

BUCKET = "gmail-raw"
ENDPOINT = "localhost:9000"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"


def get_client() -> Minio:
    return Minio(
        ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=False,
    )


def ensure_bucket():
    client = get_client()
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        print(f"  Created bucket: {BUCKET}")


def upload_file(email_id: str, filename: str, data: bytes) -> dict:
    ensure_bucket()
    client = get_client()

    object_key = f"{email_id}/{filename}"

    client.put_object(
        BUCKET,
        object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=_guess_mime(filename),
    )

    print(f"  Uploaded: {BUCKET}/{object_key} ({len(data) / 1024:.1f} KB)")
    return {
        "bucket": BUCKET,
        "object_key": object_key,
    }


def _guess_mime(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    return {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }.get(ext, "application/octet-stream")
