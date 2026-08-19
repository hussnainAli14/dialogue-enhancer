"""Pydantic models for documents and chunks."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

SourceType = Literal["blog", "article", "book", "newsletter", "talk", "workshop", "other"]
DocumentStatus = Literal["processing", "ready", "error", "reindexing"]

ALLOWED_FILE_TYPES = {"pdf", "docx", "doc", "html", "txt", "md"}


class DocumentMetadata(BaseModel):
    title: str | None = None
    source_type: SourceType | None = None
    author: str | None = None
    published_date: date | None = None


class ChunkOut(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    token_count: int | None = None


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    file_type: str
    source_type: str | None = None
    title: str | None = None
    author: str | None = None
    published_date: date | None = None
    word_count: int | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    chunk_count: int | None = None


class DocumentDetailOut(DocumentOut):
    chunks: list[ChunkOut] = []


class DocumentListOut(BaseModel):
    total_documents: int
    total_chunks: int
    total_tokens: int
    documents: list[DocumentOut]
