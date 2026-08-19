"""Module 9 — draft approval and storage endpoints; Module 10 summary."""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.database import get_supabase
from app.envelope import fail, ok
from app.models.drafts import EditAndApproveBody, RejectBody
from app.services.feedback import build_edit_diff, feedback_summary, log_feedback
from app.services.posting import publish_reply

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_draft(draft_id: str) -> dict | None:
    data = (
        get_supabase().table("response_drafts").select("*").eq("id", draft_id).execute()
    ).data
    return data[0] if data else None


def _update_draft(draft_id: str, fields: dict) -> dict:
    return (
        get_supabase()
        .table("response_drafts")
        .update(fields)
        .eq("id", draft_id)
        .execute()
    ).data[0]


@router.post("/{draft_id}/approve")
async def approve_draft(draft_id: str):
    try:
        draft = _get_draft(draft_id)
        if not draft:
            return fail("Draft not found", 404)
        if draft["status"] != "pending":
            return fail(f"Draft is not pending (current status: {draft['status']})", 400)

        updated = _update_draft(draft_id, {"status": "approved", "approved_at": _now()})
        log_feedback(
            draft_id,
            draft["conversation_id"],
            "approved",
            original_content=draft["content"],
            final_content=draft["content"],
        )
        return ok(updated)
    except Exception:
        return fail("Failed to approve draft", 500)


@router.post("/{draft_id}/edit-and-approve")
async def edit_and_approve_draft(draft_id: str, body: EditAndApproveBody):
    try:
        draft = _get_draft(draft_id)
        if not draft:
            return fail("Draft not found", 404)
        if draft["status"] != "pending":
            return fail(f"Draft is not pending (current status: {draft['status']})", 400)

        updated = _update_draft(
            draft_id,
            {
                "status": "edited",
                "edited_content": body.edited_content,
                "approved_at": _now(),
            },
        )
        log_feedback(
            draft_id,
            draft["conversation_id"],
            "edited",
            original_content=draft["content"],
            final_content=body.edited_content,
            edit_diff=build_edit_diff(draft["content"], body.edited_content),
        )
        return ok(updated)
    except Exception:
        return fail("Failed to edit and approve draft", 500)


@router.post("/{draft_id}/reject")
async def reject_draft(draft_id: str, body: RejectBody | None = None):
    try:
        draft = _get_draft(draft_id)
        if not draft:
            return fail("Draft not found", 404)

        reason = body.rejection_reason if body else None
        updated = _update_draft(
            draft_id, {"status": "rejected", "rejection_reason": reason}
        )
        log_feedback(
            draft_id,
            draft["conversation_id"],
            "rejected",
            original_content=draft["content"],
            rejection_reason=reason,
        )
        return ok(updated)
    except Exception:
        return fail("Failed to reject draft", 500)


@router.post("/{draft_id}/save")
async def save_draft(draft_id: str):
    try:
        draft = _get_draft(draft_id)
        if not draft:
            return fail("Draft not found", 404)

        updated = _update_draft(draft_id, {"status": "saved"})
        log_feedback(
            draft_id, draft["conversation_id"], "saved", original_content=draft["content"]
        )
        return ok(updated)
    except Exception:
        return fail("Failed to save draft", 500)


@router.post("/{draft_id}/post")
async def post_draft(draft_id: str):
    """Publish an already approved/edited draft to the originating platform."""
    draft = _get_draft(draft_id)
    if not draft:
        return fail("Draft not found", 404)
    if draft["status"] not in ("approved", "edited"):
        return fail(f"Only an approved or edited draft can be posted (status: {draft['status']}).", 400)
    final_content = draft.get("edited_content") or draft["content"]
    try:
        result = await publish_reply(draft["conversation_id"], final_content)
    except Exception as exc:
        return fail(f"Failed to post reply: {exc}", 400)
    updated = _update_draft(draft_id, {"status": "posted", "posted_at": _now()})
    log_feedback(
        draft_id, draft["conversation_id"], "posted",
        original_content=draft["content"], final_content=final_content,
    )
    return ok({"draft": updated, "platform_result": result})


@router.post("/{draft_id}/approve-and-post")
async def approve_and_post(draft_id: str):
    """Approve a pending draft AND publish it. Posts first; only marks the draft
    posted if publishing succeeds, so a failure leaves it cleanly pending."""
    draft = _get_draft(draft_id)
    if not draft:
        return fail("Draft not found", 404)
    if draft["status"] != "pending":
        return fail(f"Draft is not pending (current status: {draft['status']}).", 400)
    try:
        result = await publish_reply(draft["conversation_id"], draft["content"])
    except Exception as exc:
        return fail(f"Not posted — {exc}", 400)
    updated = _update_draft(
        draft_id, {"status": "posted", "approved_at": _now(), "posted_at": _now()}
    )
    log_feedback(
        draft_id, draft["conversation_id"], "approved",
        original_content=draft["content"], final_content=draft["content"],
    )
    log_feedback(
        draft_id, draft["conversation_id"], "posted",
        original_content=draft["content"], final_content=draft["content"],
    )
    return ok({"draft": updated, "platform_result": result})


@router.post("/{draft_id}/unapprove")
async def unapprove_draft(draft_id: str):
    """Revert an approved/edited/saved draft back to pending (undo an approval).
    Cannot un-post something already published."""
    draft = _get_draft(draft_id)
    if not draft:
        return fail("Draft not found", 404)
    if draft["status"] == "posted":
        return fail("This draft was already posted and cannot be reverted.", 400)
    if draft["status"] not in ("approved", "edited", "saved", "rejected"):
        return fail(f"Nothing to revert (status: {draft['status']}).", 400)
    updated = _update_draft(
        draft_id, {"status": "pending", "approved_at": None, "rejection_reason": None}
    )
    return ok(updated)


@router.post("/{draft_id}/mark-posted")
async def mark_posted(draft_id: str):
    try:
        draft = _get_draft(draft_id)
        if not draft:
            return fail("Draft not found", 404)

        final_content = draft.get("edited_content") or draft["content"]
        updated = _update_draft(draft_id, {"status": "posted", "posted_at": _now()})
        log_feedback(
            draft_id,
            draft["conversation_id"],
            "posted",
            original_content=draft["content"],
            final_content=final_content,
        )
        return ok(updated)
    except Exception:
        return fail("Failed to mark draft as posted", 500)


@router.get("/feedback-summary")
async def get_feedback_summary():
    try:
        return ok(feedback_summary())
    except Exception:
        return fail("Failed to build feedback summary", 500)
