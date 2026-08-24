"""Supabase client initialisation."""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache
def get_supabase() -> Client:
    """Service-role client — backend has full access; RLS is enforced
    at the dashboard layer later."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def log_task(task_type: str, reference_id: str | None, status: str, message: str = "") -> None:
    """Insert a processing_logs row. Never raises — logging must not
    break the pipeline it is logging."""
    try:
        get_supabase().table("processing_logs").insert(
            {
                "task_type": task_type,
                "reference_id": reference_id,
                "status": status,
                "message": message[:2000],
            }
        ).execute()
    except Exception:
        pass


def detach_feedback_log(conversation_ids: list[str]) -> None:
    """Clear feedback_log references to the given conversations and their drafts.

    feedback_log.conversation_id / draft_id are the only FKs to those tables
    without an ON DELETE rule, so any conversation with decision history cannot
    be deleted while they point at it. Both columns are nullable, so the
    references are nulled rather than the rows deleted — the audit history of
    what was approved/rejected is worth keeping after the conversation is gone.
    """
    if not conversation_ids:
        return
    supabase = get_supabase()
    draft_ids = [
        d["id"]
        for d in (
            supabase.table("response_drafts")
            .select("id")
            .in_("conversation_id", conversation_ids)
            .execute()
        ).data
        or []
    ]
    supabase.table("feedback_log").update({"conversation_id": None}).in_(
        "conversation_id", conversation_ids
    ).execute()
    if draft_ids:
        supabase.table("feedback_log").update({"draft_id": None}).in_(
            "draft_id", draft_ids
        ).execute()
