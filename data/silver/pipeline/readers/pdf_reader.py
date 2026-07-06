import hashlib
import io
import os

from data.silver.pipeline.readers.base import BaseReader
from data.silver.schemas.source import SourceData


class PdfReader(BaseReader):
    def can_handle(self, source: SourceData) -> bool:
        return os.path.splitext(source.filename.lower())[1] == ".pdf"

    def read(self, source: SourceData) -> dict:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(source.raw_data))
            pages = [p.extract_text() for p in reader.pages if p.extract_text().strip()]
            content = "\n\n".join(pages)
            page_count = len(reader.pages)
        except Exception:
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(source.raw_data)) as pdf:
                    pages = [p.extract_text() for p in pdf.pages if p.extract_text()]
                    content = "\n\n".join(pages)
                    page_count = len(pdf.pages)
            except Exception:
                content = ""
                page_count = 0
        return {"content": content, "page_count": page_count}

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
            "mime_type": "application/pdf",
        }
