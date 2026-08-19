"""Module 1 — knowledge base endpoints."""

import hashlib
from datetime import date

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from app.config import settings
from app.database import get_supabase, log_task
from app.envelope import fail, ok
from app.models.documents import ALLOWED_FILE_TYPES
from app.services.ingestion import run_ingestion

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _file_type(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in ALLOWED_FILE_TYPES else None


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    source_type: str | None = Form(None),
    author: str | None = Form(None),
    published_date: date | None = Form(None),
):
    file_type = _file_type(file.filename or "")
    if not file_type:
        return fail(
            f"Unsupported file type. Accepted: {', '.join(sorted(ALLOWED_FILE_TYPES))}", 422
        )

    try:
        supabase = get_supabase()
        data = await file.read()

        # Deduplicate by content hash. The hash is embedded in the storage path
        # so identical bytes always map to the same path, letting us detect a
        # duplicate with a single prefix lookup — no extra schema needed.
        digest = hashlib.sha256(data).hexdigest()
        existing = (
            supabase.table("documents")
            .select("id, title, status")
            .like("filename", f"documents/{digest}%")
            .limit(1)
            .execute()
        ).data
        if existing:
            dup = existing[0]
            return ok(
                {
                    "document_id": dup["id"],
                    "status": dup.get("status") or "ready",
                    "duplicate": True,
                    "existing_title": dup.get("title"),
                },
                200,
            )

        storage_path = f"documents/{digest}_{file.filename}"
        supabase.storage.from_(settings.STORAGE_BUCKET).upload(storage_path, data)

        record = (
            supabase.table("documents")
            .insert(
                {
                    "filename": storage_path,
                    "file_type": file_type,
                    "title": title or file.filename,
                    "source_type": source_type,
                    "author": author,
                    "published_date": published_date.isoformat() if published_date else None,
                    "status": "processing",
                }
            )
            .execute()
        ).data[0]

        log_task("ingestion", record["id"], "started", f"Upload: {file.filename}")
        background_tasks.add_task(run_ingestion, record["id"], storage_path, file_type)
        return ok({"document_id": record["id"], "status": "processing"}, 202)
    except Exception:
        return fail("Failed to upload document", 500)


@router.get("/documents")
async def list_documents():
    try:
        supabase = get_supabase()
        docs = (
            supabase.table("documents")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        ).data or []

        chunks = (
            supabase.table("document_chunks").select("document_id, token_count").execute()
        ).data or []
        chunk_counts: dict[str, int] = {}
        total_tokens = 0
        for c in chunks:
            chunk_counts[c["document_id"]] = chunk_counts.get(c["document_id"], 0) + 1
            total_tokens += c.get("token_count") or 0

        return ok(
            {
                "total_documents": len(docs),
                "total_chunks": len(chunks),
                "total_tokens": total_tokens,
                "documents": [
                    {
                        "id": d["id"],
                        "title": d.get("title"),
                        "filename": d["filename"],
                        "source_type": d.get("source_type"),
                        "status": d["status"],
                        "word_count": d.get("word_count"),
                        "chunk_count": chunk_counts.get(d["id"], 0),
                        "created_at": d["created_at"],
                    }
                    for d in docs
                ],
            }
        )
    except Exception:
        return fail("Failed to list documents", 500)


@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    try:
        supabase = get_supabase()
        docs = (
            supabase.table("documents").select("*").eq("id", document_id).execute()
        ).data
        if not docs:
            return fail("Document not found", 404)

        chunks = (
            supabase.table("document_chunks")
            .select("id, chunk_index, content, token_count")
            .eq("document_id", document_id)
            .order("chunk_index")
            .execute()
        ).data or []

        doc = docs[0]
        doc["chunks"] = chunks
        doc["chunk_count"] = len(chunks)
        return ok(doc)
    except Exception:
        return fail("Failed to fetch document", 500)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    try:
        supabase = get_supabase()
        docs = (
            supabase.table("documents").select("id, filename").eq("id", document_id).execute()
        ).data
        if not docs:
            return fail("Document not found", 404)

        try:
            supabase.storage.from_(settings.STORAGE_BUCKET).remove([docs[0]["filename"]])
        except Exception:
            pass  # storage file may already be gone; DB record is the source of truth

        supabase.table("documents").delete().eq("id", document_id).execute()
        return ok({"deleted": True, "document_id": document_id})
    except Exception:
        return fail("Failed to delete document", 500)


@router.post("/documents/{document_id}/reindex")
async def reindex_document(document_id: str, background_tasks: BackgroundTasks):
    try:
        supabase = get_supabase()
        docs = (
            supabase.table("documents")
            .select("id, filename, file_type")
            .eq("id", document_id)
            .execute()
        ).data
        if not docs:
            return fail("Document not found", 404)
        doc = docs[0]

        supabase.table("document_chunks").delete().eq("document_id", document_id).execute()
        supabase.table("documents").update({"status": "processing"}).eq(
            "id", document_id
        ).execute()

        log_task("ingestion", document_id, "started", "Reindex")
        background_tasks.add_task(run_ingestion, document_id, doc["filename"], doc["file_type"])
        return ok({"document_id": document_id, "status": "reindexing"}, 202)
    except Exception:
        return fail("Failed to reindex document", 500)
