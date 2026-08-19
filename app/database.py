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
