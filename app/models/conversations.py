"""Pydantic models for conversations and analysis."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Platform = Literal[
    "reddit",
    "bluesky",
    "mastodon",
    "discord",
    "telegram",
    "threads",
    "youtube",
    "facebook",
    "linkedin",
    "instagram",
    "twitter",
]

ALLOWED_PLATFORMS = {
    "reddit", "bluesky", "mastodon", "discord", "telegram",
    "threads", "youtube", "facebook", "linkedin", "instagram", "twitter",
}


class ConversationSubmit(BaseModel):
    platform: Platform
    post_url: str | None = None
    post_author: str | None = None
    original_post: str = Field(min_length=1)
    full_thread: str | None = None


class AnalysisResult(BaseModel):
    central_topic: str
    key_tensions: list[str]
    viewpoints_represented: list[str]
    emotional_sensitivities: str
    can_add_value: bool
    value_reasoning: str
    participation_recommendation: Literal["COMMENT", "DO_NOT_COMMENT"]
    recommendation_reason: str
    relevance_score: float = Field(ge=0, le=1)


class ConversationListItem(BaseModel):
    id: UUID
    platform: str
    post_author: str | None = None
    original_post: str = ""
    central_topic: str | None = None
    analysis_status: str
    relevance_score: float | None = None
    submitted_at: datetime
    draft_count: int = 0
    has_posted_reply: bool = False


class ConversationList(BaseModel):
    page: int
    page_size: int
    total: int
    conversations: list[ConversationListItem]
