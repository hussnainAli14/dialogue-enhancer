"""Pydantic models and dataclasses for Module 4 — discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field


# ── Settings ──────────────────────────────────────────

@dataclass
class DiscoverySettings:
    id: str | None = None
    is_enabled: bool = True
    schedule_interval_minutes: int = 30
    max_posts_per_run: int = 50
    max_conversations_per_day: int = 5
    min_relevance_score: float = 0.65
    scoring_batch_size: int = 10


class DiscoverySettingsUpdate(BaseModel):
    is_enabled: bool | None = None
    schedule_interval_minutes: int | None = Field(default=None, ge=1)
    max_posts_per_run: int | None = Field(default=None, ge=1)
    max_conversations_per_day: int | None = Field(default=None, ge=0)
    min_relevance_score: float | None = Field(default=None, ge=0, le=1)
    scoring_batch_size: int | None = Field(default=None, ge=1)


# ── Scoring ───────────────────────────────────────────

@dataclass
class ScoredPost:
    """A UniversalPost carried alongside its relevance scoring."""

    post: object  # UniversalPost — avoid import cycle
    final_score: float = 0.0
    topic_relevance: float = 0.0
    contribution_opportunity: float = 0.0
    discussion_quality: float = 0.0
    audience_fit: float = 0.0
    reasoning: str = ""


# ── Run result ────────────────────────────────────────

@dataclass
class DiscoveryRunResult:
    run_id: str
    status: str
    platforms_checked: list[str] = field(default_factory=list)
    posts_fetched: int = 0
    posts_scored: int = 0
    posts_submitted: int = 0
    posts_filtered: int = 0
    posts_duplicated: int = 0
    message: str = ""


@dataclass
class SchedulerStatus:
    scheduler_running: bool
    next_run_at: datetime | None
    schedule_interval_minutes: int


# ── Community API models ──────────────────────────────

class CommunityCreate(BaseModel):
    platform: str
    community_id: str
    community_name: str
    keywords: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=5)


class CommunityUpdate(BaseModel):
    community_name: str | None = None
    keywords: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    is_active: bool | None = None
