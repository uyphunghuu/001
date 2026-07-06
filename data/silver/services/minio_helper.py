"""MinIO helper with observability.

OBSERVABILITY ADDED (2026-07-03):
    - Object list timing
    - Source read timing
    - MinIO connection health check
    - Object size histogram
"""
import hashlib
import io
import os
import time
from typing import Optional

from minio import Minio
from data.silver.config import get_settings
from data.silver.schemas.source import SourceData
from data.observability import metrics, logger


class MinioHelper:
    def __init__(self):
        settings = get_settings()
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._settings = settings

    def list_objects(self, bucket: str = "gmail-raw", prefix: str = "") -> list[dict]:
        """List objects in a bucket with timing."""
        start = time.monotonic()
        try:
            objects = list(self._client.list_objects(bucket, prefix=prefix, recursive=True))
            elapsed_ms = (time.monotonic() - start) * 1000

            result = []
            for obj in objects:
                result.append({
                    "bucket": bucket,
                    "object_key": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                })

            metrics.histogram("minio_list_duration_ms").observe(elapsed_ms)
            metrics.gauge("minio_object_count", tags={"bucket": bucket}).set(len(result))
            logger.info(f"Listed {len(result)} objects from {bucket}",
                         component="minio_helper", event="list_objects.complete",
                         bucket=bucket, count=len(result), duration_ms=elapsed_ms)
            return result
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error(f"Failed to list objects from {bucket}",
                          component="minio_helper", event="list_objects.failed",
                          bucket=bucket, error=str(e), duration_ms=elapsed_ms)
            raise

    def get_source(self, bucket: str, object_key: str, metadata: dict = None) -> SourceData:
        """Read an object from MinIO and return as SourceData with timing."""
        start = time.monotonic()
        try:
            response = self._client.get_object(bucket, object_key)
            raw_data = response.read()
            response.close()
            response.release_conn()
            elapsed_ms = (time.monotonic() - start) * 1000

            metrics.histogram("minio_read_duration_ms", tags={"bucket": bucket}).observe(elapsed_ms)
            metrics.histogram("minio_object_size_bytes", tags={"bucket": bucket}).observe(len(raw_data))

            filename = os.path.basename(object_key)

            # Checksum for data integrity
            checksum = hashlib.sha256(raw_data).hexdigest()

            md = {
                "checksum": checksum,
                "source": f"minio://{bucket}/{object_key}",
                **(metadata or {}),
            }

            return SourceData(
                bucket=bucket,
                object_key=object_key,
                filename=filename,
                size_bytes=len(raw_data),
                raw_data=raw_data,
                metadata=md,
            )
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error(f"Failed to read {bucket}/{object_key}",
                          component="minio_helper", event="get_source.failed",
                          bucket=bucket, object_key=object_key, error=str(e), duration_ms=elapsed_ms)
            raise

    def iterate_bucket(self, bucket: str = "gmail-raw", prefix: str = "", extension: str = ""):
        """Generator that yields SourceData objects."""
        objects = self.list_objects(bucket, prefix)
        for obj in objects:
            if extension and not obj["object_key"].lower().endswith(extension):
                continue
            yield self.get_source(obj["bucket"], obj["object_key"])

    @staticmethod
    def read_from_disk(filepath: str, metadata: dict = None) -> SourceData:
        """Read a local file and return as SourceData."""
        start = time.monotonic()
        with open(filepath, "rb") as f:
            raw_data = f.read()
        elapsed_ms = (time.monotonic() - start) * 1000

        filename = os.path.basename(filepath)
        checksum = hashlib.sha256(raw_data).hexdigest()

        md = {
            "checksum": checksum,
            "source": f"file://{filepath}",
            **(metadata or {}),
        }

        return SourceData(
            bucket="local",
            object_key=filepath,
            filename=filename,
            size_bytes=len(raw_data),
            raw_data=raw_data,
            metadata=md,
        )

    def health_check(self) -> dict:
        """Check MinIO connectivity."""
        start = time.monotonic()
        try:
            buckets = self._client.list_buckets()
            elapsed_ms = (time.monotonic() - start) * 1000
            bucket_names = [b.name for b in buckets]
            return {
                "status": "healthy",
                "latency_ms": elapsed_ms,
                "buckets": bucket_names,
            }
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("MinIO health check failed", component="minio_helper",
                         event="health_check.failed", error=str(e), latency_ms=elapsed_ms)
            return {"status": "unhealthy", "error": str(e), "latency_ms": elapsed_ms}
