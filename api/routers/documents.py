"""Document API router."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data"))

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text

from api.dependencies import get_repo
from data.silver.repositories.base import BaseRepository

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    id: str
    title: Optional[str]
    source: str
    source_type: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    checksum: str
    processing_status: str
    content_length: Optional[int]
    created_at: Optional[str]
    minio_path: Optional[str]
    language: Optional[str]


class DocumentDetail(BaseModel):
    id: str
    source: str
    source_type: str
    source_object_id: Optional[str]
    title: Optional[str]
    content: Optional[str]
    checksum: str
    mime_type: Optional[str]
    size_bytes: Optional[int]
    minio_bucket: Optional[str]
    minio_path: Optional[str]
    language: Optional[str]
    page_count: Optional[int]
    author: Optional[str]
    created_time: Optional[str]
    updated_time: Optional[str]
    processing_status: str
    error_message: Optional[str]
    processed_at: Optional[str]
    metadata: Optional[dict]
    raw_json: Optional[dict]
    created_at: Optional[str]
    updated_at: Optional[str]


class DocumentContent(BaseModel):
    id: str
    title: Optional[str]
    content: Optional[str]
    content_length: int


class PaginatedResponse(BaseModel):
    items: list[DocumentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.get("", response_model=PaginatedResponse)
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="Search query"),
    source: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    mime_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sort_by: str = Query("created_at", regex="^(created_at|title|size_bytes|content_length)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    repo: BaseRepository = Depends(get_repo),
):
    conditions = []
    params = {}

    if q:
        conditions.append(
            "(d.title ILIKE :q OR d.content ILIKE :q OR d.checksum ILIKE :q OR d.source ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if source:
        conditions.append("d.source = :source")
        params["source"] = source
    if source_type:
        conditions.append("d.source_type = :source_type")
        params["source_type"] = source_type
    if language:
        conditions.append("d.language = :language")
        params["language"] = language
    if mime_type:
        conditions.append("d.mime_type = :mime_type")
        params["mime_type"] = mime_type
    if status:
        conditions.append("d.processing_status = :status")
        params["status"] = status

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    order_dir = "DESC" if sort_order == "desc" else "ASC"
    offset = (page - 1) * page_size

    count_sql = f"SELECT COUNT(*) FROM documents d WHERE {where_clause}"
    total = repo.execute_raw(count_sql, params)[0][0] if repo.execute_raw(count_sql, params) else 0

    data_sql = f"""
        SELECT d.id, d.title, d.source, d.source_type, d.mime_type,
               d.size_bytes, d.checksum, d.processing_status,
               LENGTH(d.content) as content_length, d.created_at::text,
               d.minio_path, d.language
        FROM documents d
        WHERE {where_clause}
        ORDER BY d.{sort_by} {order_dir}
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = page_size
    params["offset"] = offset

    rows = repo.execute_raw(data_sql, params) or []

    items = [
        DocumentSummary(
            id=str(r[0]),
            title=r[1],
            source=r[2],
            source_type=r[3],
            mime_type=r[4],
            size_bytes=r[5],
            checksum=r[6],
            processing_status=r[7],
            content_length=r[8],
            created_at=str(r[9]) if r[9] else None,
            minio_path=r[10],
            language=r[11],
        )
        for r in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: str, repo: BaseRepository = Depends(get_repo)):
    sql = """
        SELECT id, source, source_type, source_object_id, title, content,
               checksum, mime_type, size_bytes, minio_bucket, minio_path,
               language, page_count, author, created_time::text, updated_time::text,
               processing_status, error_message, processed_at::text,
               metadata::text, raw_json::text, created_at::text, updated_at::text
        FROM documents WHERE id = :id
    """
    rows = repo.execute_raw(sql, {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")

    r = rows[0]
    import json

    return DocumentDetail(
        id=str(r[0]),
        source=r[1],
        source_type=r[2],
        source_object_id=r[3],
        title=r[4],
        content=r[5],
        checksum=r[6],
        mime_type=r[7],
        size_bytes=r[8],
        minio_bucket=r[9],
        minio_path=r[10],
        language=r[11],
        page_count=r[12],
        author=r[13],
        created_time=r[14],
        updated_time=r[15],
        processing_status=r[16],
        error_message=r[17],
        processed_at=r[18],
        metadata=json.loads(r[19]) if r[19] else None,
        raw_json=json.loads(r[20]) if r[20] else None,
        created_at=r[21],
        updated_at=r[22],
    )


@router.get("/{doc_id}/content", response_model=DocumentContent)
def get_document_content(doc_id: str, repo: BaseRepository = Depends(get_repo)):
    sql = "SELECT id, title, content FROM documents WHERE id = :id"
    rows = repo.execute_raw(sql, {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    r = rows[0]
    return DocumentContent(
        id=str(r[0]),
        title=r[1],
        content=r[2],
        content_length=len(r[2]) if r[2] else 0,
    )


@router.get("/{doc_id}/pipeline")
def get_document_pipeline(doc_id: str, repo: BaseRepository = Depends(get_repo)):
    sql = """
        SELECT processing_status, error_message, processed_at
        FROM documents WHERE id = :id
    """
    rows = repo.execute_raw(sql, {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    r = rows[0]
    status = r[0] or "pending"

    steps = [
        {"name": "Reader", "status": "success" if status in ("completed", "processing") else status},
        {"name": "Cleaner", "status": "success" if status in ("completed", "processing") else status},
        {"name": "Validator", "status": "success" if status in ("completed", "processing") else status},
        {"name": "Normalizer", "status": "success" if status in ("completed", "processing") else status},
        {"name": "PostgreSQL", "status": status},
    ]

    if status == "failed":
        steps[4]["status"] = "failed"
        steps[4]["error"] = r[1]

    return {"steps": steps, "processed_at": str(r[2]) if r[2] else None, "status": status}


@router.get("/{doc_id}/quality")
def get_document_quality(doc_id: str, repo: BaseRepository = Depends(get_repo)):
    sql = """
        SELECT checksum, processing_status, error_message, language, content,
               mime_type, source_object_id
        FROM documents WHERE id = :id
    """
    rows = repo.execute_raw(sql, {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    r = rows[0]
    content = r[4] or ""

    return {
        "document_id": doc_id,
        "checksum": r[0],
        "checksum_valid": bool(r[0] and len(r[0]) == 64),
        "validation_status": r[1],
        "error_message": r[2],
        "language_detected": bool(r[3]),
        "has_content": bool(content.strip()),
        "content_length": len(content),
        "encoding_valid": True,
        "mime_type_valid": bool(r[5]),
        "has_source_id": bool(r[6]),
        "is_duplicate": False,
        "issues": [],
    }


@router.get("/{doc_id}/history")
def get_document_history(doc_id: str, repo: BaseRepository = Depends(get_repo)):
    sql = """
        SELECT id, created_at::text, updated_at::text, processing_status
        FROM documents WHERE id = :id
    """
    rows = repo.execute_raw(sql, {"id": doc_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    r = rows[0]

    return {
        "document_id": doc_id,
        "versions": [
            {
                "version": 1,
                "created_at": r[1],
                "modified_at": r[2],
                "status": r[3],
                "pipeline_run": None,
            }
        ],
    }
