import csv
import hashlib
import io
import os

from data.silver.pipeline.readers.base import BaseReader
from data.silver.schemas.source import SourceData


class CsvReader(BaseReader):
    def can_handle(self, source: SourceData) -> bool:
        return os.path.splitext(source.filename.lower())[1] == ".csv"

    def read(self, source: SourceData) -> dict:
        try:
            text = source.raw_data.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            lines = [" | ".join(row) for row in rows]
            content = "\n".join(lines)
        except Exception:
            content = ""
        return {"content": content}

    def extract_metadata(self, source: SourceData) -> dict:
        ext = os.path.splitext(source.filename.lower())[1]
        checksum = hashlib.sha256(source.raw_data).hexdigest()
        return {
            "extension": ext,
            "checksum": checksum,
            "size_bytes": source.size_bytes,
            "object_key": source.object_key,
            "bucket": source.bucket,
            "source": f"minio://{source.bucket}/{source.object_key}",
            "mime_type": "text/csv",
        }
