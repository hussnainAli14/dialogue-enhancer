"""Shared DB helpers for discovery (settings, daily count, communities)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.config import settings as env_settings
from app.database import get_supabase
from app.models.discovery import DiscoverySettings


def get_settings() -> DiscoverySettings:
    """Read the single discovery_settings row. Falls back to env defaults if
    the table is unreadable or empty."""
    try:
        rows = (
            get_supabase().table("discovery_settings").select("*").limit(1).execute()
        ).data
        if rows:
            r = rows[0]
            return DiscoverySettings(
                id=r.get("id"),
                is_enabled=r.get("is_enabled", True),
                schedule_interval_minutes=r.get("schedule_interval_minutes", 30),
                max_posts_per_run=r.get("max_posts_per_run", 50),
                max_conversations_per_day=r.get("max_conversations_per_day", 5),
                min_relevance_score=r.get("min_relevance_score", 0.65),
                scoring_batch_size=r.get("scoring_batch_size", 10),
            )
    except Exception:
        pass
    return DiscoverySettings(
        is_enabled=env_settings.DISCOVERY_ENABLED,
        schedule_interval_minutes=env_settings.DISCOVERY_SCHEDULE_MINUTES,
        max_posts_per_run=env_settings.MAX_POSTS_PER_RUN,
        max_conversations_per_day=env_settings.MAX_CONVERSATIONS_PER_DAY,
        min_relevance_score=env_settings.MIN_RELEVANCE_SCORE,
    )


def update_settings(fields: dict) -> DiscoverySettings:
    supabase = get_supabase()
    fields = {k: v for k, v in fields.items() if v is not None}
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    current = get_settings()
    if current.id:
        supabase.table("discovery_settings").update(fields).eq("id", current.id).execute()
    else:
        supabase.table("discovery_settings").insert(fields).execute()
    return get_settings()


def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def daily_conversation_count() -> int:
    """Conversations created since UTC midnight — the authoritative daily count."""
    try:
        res = (
            get_supabase()
            .table("conversations")
            .select("id", count="exact")
            .gte("submitted_at", _today_start_iso())
            .execute()
        )
        return res.count or 0
    except Exception:
        return 0


def active_communities() -> list[dict]:
    try:
        return (
            get_supabase()
            .table("monitored_communities")
            .select("*")
            .eq("is_active", True)
            .execute()
        ).data or []
    except Exception:
        return []
