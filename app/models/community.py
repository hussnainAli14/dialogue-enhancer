"""Pydantic models for Module 3 — community discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Topics ────────────────────────────────────────────
class TopicCreate(BaseModel):
    topic: str
    keywords: list[str] = Field(default_factory=list)
    description: str | None = None


class TopicUpdate(BaseModel):
    topic: str | None = None
    keywords: list[str] | None = None
    description: str | None = None
    is_active: bool | None = None


# ── People ────────────────────────────────────────────
class PersonCreate(BaseModel):
    name: str
    description: str | None = None
    platform_handles: dict[str, str] = Field(default_factory=dict)


class PersonUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    platform_handles: dict[str, str] | None = None
    is_active: bool | None = None


# ── Discovery trigger ─────────────────────────────────
class DiscoverBody(BaseModel):
    modes: list[str] | None = None      # ["keyword", "people_based"]
    platforms: list[str] | None = None  # default: all connected


# ── Suggestion actions ────────────────────────────────
class ApproveBody(BaseModel):
    keywords: list[str] | None = None  # override the AI-suggested keywords


class RejectBody(BaseModel):
    rejection_reason: str | None = None


class ApproveAllBody(BaseModel):
    min_score: float = Field(ge=0, le=1)


class RejectAllBody(BaseModel):
    max_score: float = Field(ge=0, le=1)
    rejection_reason: str | None = None


# ── Monitored community (manual add / update) ─────────
class MonitoredCreate(BaseModel):
    platform: str
    community_id: str
    community_name: str
    keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=5)


class MonitoredUpdate(BaseModel):
    keywords: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    is_active: bool | None = None
