"""Reply tracking — records the author's own posts, polls each connected
platform for replies to them, and surfaces new replies in the dashboard feed
as starred `reply_to_me` conversations (drafted on demand, not automatically)."""

from __future__ import annotations

from app.database import get_supabase, log_task
from app.services import token_store
from app.services.connections.factory import get_connector

# Platforms whose connectors implement fetch_replies + record post ids.
REPLY_PLATFORMS = {"bluesky", "mastodon"}


def _post_ref(platform: str, result: dict) -> tuple[str | None, str | None]:
    """Extract (post_id, post_url) from a connector post result."""
    if not isinstance(result, dict):
        return None, None
    if platform == "bluesky":
        return result.get("uri"), result.get("url")
    # mastodon and others: {id, url}
    return (str(result["id"]) if result.get("id") else None), result.get("url")


def record_authored_post(platform: str, result: dict, content: str, is_reply: bool) -> None:
    """Remember a post we just published so replies to it can be tracked. Never
    raises — recording is best-effort and must not break the posting flow."""
    if platform not in REPLY_PLATFORMS:
        return
    try:
        post_id, post_url = _post_ref(platform, result)
        if not post_id:
            return
        get_supabase().table("authored_posts").upsert(
            {
                "platform": platform,
                "post_id": post_id,
                "post_url": post_url,
                "content": (content or "")[:2000],
                "is_reply": is_reply,
            },
            on_conflict="platform,post_id",
        ).execute()
    except Exception as exc:
        log_task("analysis", None, "failed", f"Could not record authored post: {exc}")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def poll_replies() -> dict:
    """Check every connected reply-capable platform for new replies to the
    author's posts. New replies become starred `reply_to_me` conversations
    (analysis_status 'reply_pending' — no drafts until the author asks).
    Returns {checked, new_replies}."""
    supabase = get_supabase()

    connected = {
        c.platform
        for c in token_store.get_all_connections()
        if c.status == "connected" and c.platform in REPLY_PLATFORMS
    }
    if not connected:
        return {"checked": 0, "new_replies": 0, "skipped": "no reply-capable platform connected"}

    posts = (
        supabase.table("authored_posts")
        .select("*")
        .in_("platform", list(connected))
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    ).data or []

    checked = 0
    new_count = 0

    for ap in posts:
        platform = ap["platform"]
        connection = token_store.get_connection(platform)
        if not connection:
            continue
        connector = get_connector(platform)
        checked += 1
        try:
            replies = await connector.fetch_replies(
                connection, ap["post_id"], exclude_author_id=connection.account_id
            )
        except Exception:
            replies = []

        for r in replies:
            reply_id = r.get("reply_id")
            if not reply_id:
                continue
            # Skip replies we have already ingested.
            exists = (
                supabase.table("seen_replies")
                .select("id")
                .eq("platform", platform)
                .eq("reply_id", reply_id)
                .limit(1)
                .execute()
            ).data
            if exists:
                continue

            conv = (
                supabase.table("conversations")
                .insert(
                    {
                        "platform": platform,
                        "post_url": r.get("post_url"),
                        "post_author": r.get("author_name"),
                        "original_post": r.get("content") or "(no text)",
                        "parent_post_url": ap.get("post_url"),
                        "source": "reply_to_me",
                        "is_reply_to_me": True,
                        "analysis_status": "reply_pending",
                    }
                )
                .execute()
            ).data[0]
            conversation_id = conv["id"]

            # Store the reply's platform id so a response threads back to it via
            # the existing publish_reply target resolution.
            try:
                supabase.table("discovered_posts").insert(
                    {
                        "platform": platform,
                        "post_id": reply_id,
                        "post_url": r.get("post_url"),
                        "author_name": r.get("author_name"),
                        "author_id": r.get("author_id"),
                        "content": r.get("content") or "(no text)",
                        "status": "submitted",
                        "conversation_id": conversation_id,
                    }
                ).execute()
            except Exception:
                pass

            supabase.table("seen_replies").insert(
                {"platform": platform, "reply_id": reply_id, "conversation_id": conversation_id}
            ).execute()
            new_count += 1

        supabase.table("authored_posts").update({"last_checked_at": _now_iso()}).eq(
            "id", ap["id"]
        ).execute()

    if new_count:
        log_task("analysis", None, "completed", f"Reply tracking found {new_count} new repl(y/ies).")
    return {"checked": checked, "new_replies": new_count}
