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
                keyword_search_cap=r.get("keyword_search_cap") or 30,
                kb_overlap_weight=(
                    r.get("kb_overlap_weight")
                    if r.get("kb_overlap_weight") is not None
                    else 0.25
                ),
                min_engagement_score=(
                    r.get("min_engagement_score")
                    if r.get("min_engagement_score") is not None
                    else 0.0
                ),
                engagement_weight=(
                    r.get("engagement_weight")
                    if r.get("engagement_weight") is not None
                    else 0.3
                ),
                discovery_lookback_hours=r.get("discovery_lookback_hours") or 72,
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


# Default max active keywords searched per run when unset — caps API/quota cost.
# The live value comes from discovery_settings.keyword_search_cap.
KEYWORD_SEARCH_CAP = 30


def active_keywords(limit: int | None = None) -> list[str]:
    """Active discovery keywords (KB-derived + manual), oldest first, capped."""
    if limit is None:
        limit = get_settings().keyword_search_cap
    try:
        rows = (
            get_supabase()
            .table("discovery_keywords")
            .select("keyword")
            .eq("is_active", True)
            .order("created_at")
            .limit(limit)
            .execute()
        ).data or []
        return [r["keyword"] for r in rows if r.get("keyword")]
    except Exception:
        return []


def seed_reddit_subreddits(found: list[dict], min_matches: int = 2) -> int:
    """Insert newly discovered subreddits into monitored_communities. Only adds
    rows that don't exist yet — never touches ones the user has already chosen
    (so a user-deactivated subreddit stays off). A subreddit is inserted ACTIVE
    (scraped) only if it matched at least `min_matches` distinct keywords (the
    `weekly_active` field = that count); one-off matches are inserted inactive but
    visible in Community Manager. Returns the number newly inserted."""
    if not found:
        return 0
    supabase = get_supabase()
    try:
        existing = {
            r["community_id"]
            for r in (
                supabase.table("monitored_communities")
                .select("community_id")
                .eq("platform", "reddit")
                .execute()
            ).data
            or []
        }
        new_rows = []
        for c in found:
            cid = c.get("community_id")
            if not cid or cid in existing:
                continue
            new_rows.append(
                {
                    "platform": "reddit",
                    "community_id": cid,
                    "community_name": c.get("community_name") or f"r/{cid}",
                    "keywords": [],
                    "is_active": (c.get("weekly_active") or 0) >= min_matches,
                    "priority": 1,
                }
            )
        if new_rows:
            supabase.table("monitored_communities").insert(new_rows).execute()
        return len(new_rows)
    except Exception:
        return 0


def reddit_subreddits_last_refresh() -> datetime | None:
    """When the monitored reddit subreddits were last discovered/refreshed —
    the latest updated_at across reddit rows. None if there are no reddit rows."""
    try:
        rows = (
            get_supabase()
            .table("monitored_communities")
            .select("updated_at")
            .eq("platform", "reddit")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if not rows or not rows[0].get("updated_at"):
            return None
        ts = datetime.fromisoformat(rows[0]["updated_at"].replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def keywords_changed_since(ts: datetime) -> bool:
    """True if any active keyword was added after `ts` — so the subreddit list
    should be re-discovered to reflect the new keyword."""
    try:
        rows = (
            get_supabase()
            .table("discovery_keywords")
            .select("created_at")
            .eq("is_active", True)
            .gt("created_at", ts.isoformat())
            .limit(1)
            .execute()
        ).data or []
        return bool(rows)
    except Exception:
        return False


def touch_reddit_refresh() -> None:
    """Mark the reddit subreddits as freshly refreshed (bumps updated_at) so a
    refresh that found no *new* subreddits still resets the staleness clock —
    stops repeated manual runs from re-paying for discovery."""
    try:
        get_supabase().table("monitored_communities").update(
            {"updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("platform", "reddit").execute()
    except Exception:
        pass


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
