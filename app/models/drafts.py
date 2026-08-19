"""Pydantic models for drafts and feedback."""

from typing import Literal

from pydantic import BaseModel, Field

DraftStyle = Literal[
    "insightful_contribution",
    "facilitative_question",
    "synthesis_of_viewpoints",
    "constructive_challenge",
]

DraftStatus = Literal["pending", "approved", "edited", "rejected", "saved", "posted"]


class EditAndApproveBody(BaseModel):
    edited_content: str = Field(min_length=1)


class RejectBody(BaseModel):
    rejection_reason: str | None = None


class FeedbackSummary(BaseModel):
    total_drafts_generated: int
    approval_rate: float
    edit_rate: float
    rejection_rate: float
    most_common_rejection_reasons: list[dict]
    best_performing_styles: list[dict]
    average_edit_length_vs_original: float
