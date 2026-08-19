"""Module 1 — document ingestion pipeline.

Runs as a FastAPI BackgroundTask: parse → chunk → embed → store.
Every failure updates the document status to error and logs to
processing_logs.
"""

import asyncio
import io
import os
import re
import shutil
import subprocess
import tempfile

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_embeddings, settings
from app.database import get_supabase, log_task

EMBED_BATCH_SIZE = 50
EMBED_MAX_RETRIES = 3


# ─────────────────────────────────────
# Parsing
# ─────────────────────────────────────

def _parse_pdf(data: bytes) -> str:
    import fitz

    text_parts = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _parse_docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _parse_doc(data: bytes) -> str:
    """Parse a legacy binary .doc file.

    There is no reliable pure-Python reader for the old OLE .doc format, so we
    convert via an external engine, tried in order of portability:
      1. LibreOffice headless (`soffice`) — cross-platform, no MS Office needed.
      2. Microsoft Word COM automation — Windows-only, needs Word installed.
    Whichever is available on the host is used; if neither is, a clear error is
    raised so the document is marked with an actionable message.
    """
    tmp_dir = tempfile.mkdtemp(prefix="doc_ingest_")
    src_path = os.path.join(tmp_dir, "input.doc")
    with open(src_path, "wb") as fh:
        fh.write(data)
    try:
        # 1 — LibreOffice
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp_dir, src_path],
                check=True,
                capture_output=True,
                timeout=120,
            )
            out_path = os.path.join(tmp_dir, "input.txt")
            if os.path.exists(out_path):
                with open(out_path, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read()

        # 2 — Microsoft Word COM (Windows + Word installed)
        text = _parse_doc_via_word(src_path)
        if text is not None:
            return text

        raise RuntimeError(
            "Cannot parse .doc: no converter available. Install LibreOffice "
            "(soffice) or Microsoft Word, or convert the file to .docx."
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _parse_doc_via_word(src_path: str) -> str | None:
    """Convert a .doc to text using Word COM automation. Returns None if Word
    or pywin32 is unavailable on the host."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None

    pythoncom.CoInitialize()
    word = None
    doc = None
    txt_path = src_path + ".txt"
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        doc = word.Documents.Open(src_path, ReadOnly=True)
        # 2 == wdFormatText
        doc.SaveAs(txt_path, FileFormat=2)
        doc.Close(False)
        doc = None
        with open(txt_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception as exc:  # Word present but conversion failed
        raise RuntimeError(f"Word COM conversion failed: {exc}") from exc
    finally:
        if doc is not None:
            try:
                doc.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        if os.path.exists(txt_path):
            os.remove(txt_path)


def _parse_html(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def _parse_plain(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


PARSERS = {
    "pdf": _parse_pdf,
    "docx": _parse_docx,
    "doc": _parse_doc,
    "html": _parse_html,
    "txt": _parse_plain,
    "md": _parse_plain,
}


def _clean_text(text: str) -> str:
    """Strip extra whitespace, fix encoding artefacts, drop lines repeated
    across the document (headers/footers)."""
    text = text.replace("\x00", "").replace("﻿", "")
    lines = [ln.strip() for ln in text.splitlines()]

    # Lines that repeat many times are almost certainly page headers/footers.
    counts: dict[str, int] = {}
    for ln in lines:
        if ln:
            counts[ln] = counts.get(ln, 0) + 1
    repeated = {ln for ln, c in counts.items() if c >= 4 and len(ln) < 100}

    kept = [ln for ln in lines if ln not in repeated]
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ─────────────────────────────────────
# Pipeline
# ─────────────────────────────────────

async def run_ingestion(document_id: str, storage_path: str, file_type: str) -> None:
    supabase = get_supabase()
    try:
        # Step 1 — parse
        data = supabase.storage.from_(settings.STORAGE_BUCKET).download(storage_path)
        raw_text = PARSERS[file_type](data)
        text = _clean_text(raw_text)
        if not text:
            raise ValueError("Document parsed to empty text")

        word_count = len(text.split())
        supabase.table("documents").update({"word_count": word_count}).eq(
            "id", document_id
        ).execute()

        # Step 2 — chunk
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_text(text)
        if not chunks:
            raise ValueError("Chunking produced no chunks")

        # Step 3 — embed in batches of 50 with retry + exponential backoff
        embeddings_model = get_embeddings()
        all_vectors: list[list[float]] = []
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            for attempt in range(EMBED_MAX_RETRIES):
                try:
                    vectors = await embeddings_model.aembed_documents(batch)
                    all_vectors.extend(vectors)
                    break
                except Exception:
                    if attempt == EMBED_MAX_RETRIES - 1:
                        raise
                    await asyncio.sleep(2 ** (attempt + 1))

        # Step 4 — store
        rows = [
            {
                "document_id": document_id,
                "chunk_index": i,
                "content": chunk,
                "token_count": _estimate_tokens(chunk),
                "embedding": vector,
            }
            for i, (chunk, vector) in enumerate(zip(chunks, all_vectors))
        ]
        supabase.table("document_chunks").insert(rows).execute()

        supabase.table("documents").update({"status": "ready", "error_message": None}).eq(
            "id", document_id
        ).execute()
        log_task("ingestion", document_id, "completed", f"{len(chunks)} chunks stored")

    except Exception as exc:
        supabase.table("documents").update(
            {"status": "error", "error_message": str(exc)[:1000]}
        ).eq("id", document_id).execute()
        log_task("ingestion", document_id, "failed", str(exc))
