"""Publishes an approved reply to the originating platform (Module 9 write side)."""

from __future__ import annotations

import asyncio
import uuid

from app.database import detach_feedback_log, get_supabase, log_task
from app.services import token_store
from app.services.connections.factory import get_connector

# Platforms with a working post_reply / post_exists implementation.
SUPPORTED_POSTING = {"bluesky", "mastodon", "reddit", "discord", "threads", "youtube"}

# Platforms with a working create_post (standalone post) implementation.
SUPPORTED_STANDALONE = {"bluesky", "mastodon", "threads"}

# Hard per-post character limits.
PLATFORM_CHAR_LIMITS = {
    "bluesky": 300,
    "mastodon": 500,
    "reddit": 10000,
    "discord": 2000,
    "threads": 500,
    "youtube": 10000,
}


def _resolve_target(supabase, conversation_id: str, conv: dict) -> dict:
    """Resolve the platform post reference for a conversation — prefer the
    discovered_posts row (exact platform post id), fall back to post_url."""
    dp = (
        supabase.table("discovered_posts")
        .select("post_id, post_url, community_id")
        .eq("conversation_id", conversation_id)
        .limit(1)
        .execute()
    ).data
    if dp:
        return {
            "uri": dp[0]["post_id"],
            "id": dp[0]["post_id"],
            "community_id": dp[0].get("community_id"),
            "post_url": dp[0].get("post_url"),
        }
    if conv.get("post_url"):
        return {"post_url": conv["post_url"]}
    return {}


async def check_source_alive(conversation_id: str) -> dict:
    """Fetch fresh data from the platform to see if the original post still
    exists. Returns {supported, connected, exists, ...}. `exists` is None when
    it could not be determined."""
    supabase = get_supabase()
    conv_rows = (
        supabase.table("conversations").select("*").eq("id", conversation_id).limit(1).execute()
    ).data
    if not conv_rows:
        raise ValueError("Conversation not found.")
    conv = conv_rows[0]
    platform = conv["platform"]

    if platform not in SUPPORTED_POSTING:
        return {"supported": False, "platform": platform, "exists": None}

    connection = token_store.get_connection(platform)
    if not connection or connection.status != "connected":
        return {"supported": True, "connected": False, "platform": platform, "exists": None}

    target = _resolve_target(supabase, conversation_id, conv)
    if not target:
        return {"supported": True, "connected": True, "exists": None, "reason": "no_reference"}

    connector = get_connector(platform)
    try:
        exists = await connector.post_exists(connection, target=target)
    except Exception as exc:
        return {"supported": True, "connected": True, "exists": None, "error": str(exc)}
    return {
        "supported": True,
        "connected": True,
        "exists": exists,
        "platform": platform,
        "post_url": conv.get("post_url"),
    }


# ── Background scan registry ──────────────────────────
# A scan makes one live API call per conversation, so it runs for a minute or
# more. It is kicked off as a background task and polled by scan_id instead of
# blocking the request. In-memory on purpose: a scan result is throwaway state
# and does not need to survive a restart.
_SCANS: dict[str, dict] = {}
_SCAN_RETENTION = 20  # keep only the most recent scans


def start_scan() -> str:
    """Kick off a dry-run scan in the background and return its scan_id."""
    scan_id = str(uuid.uuid4())
    _SCANS[scan_id] = {
        "scan_id": scan_id,
        "status": "running",
        "checked": 0,
        "total": 0,
        "deleted": [],
        "deleted_count": 0,
        "error": None,
    }
    # Drop the oldest entries so a long-lived process cannot grow unbounded.
    for stale in list(_SCANS)[:-_SCAN_RETENTION]:
        _SCANS.pop(stale, None)

    asyncio.create_task(_run_scan(scan_id))
    return scan_id


def get_scan(scan_id: str) -> dict | None:
    return _SCANS.get(scan_id)


async def _run_scan(scan_id: str) -> None:
    state = _SCANS[scan_id]
    try:
        result = await scan_deleted(dry_run=True, state=state)
        state.update(result)
        state["status"] = "completed"
    except Exception as exc:  # never leave a scan stuck on "running"
        state["status"] = "failed"
        state["error"] = str(exc)


def apply_scan(scan_id: str) -> dict:
    """Delete exactly the conversations a completed scan flagged.

    Re-scanning here would repeat every platform call for a second time, so the
    confirm step reuses the ids the scan already found.
    """
    state = _SCANS.get(scan_id)
    if not state:
        raise ValueError("Scan not found or expired. Run the scan again.")
    if state["status"] != "completed":
        raise ValueError(f"Scan is not finished (status: {state['status']}).")

    ids = [d["id"] for d in state["deleted"]]
    if not ids:
        return {"removed": False, "deleted_count": 0}

    supabase = get_supabase()
    detach_feedback_log(ids)
    supabase.table("discovered_posts").delete().in_("conversation_id", ids).execute()
    supabase.table("conversations").delete().in_("id", ids).execute()
    log_task("analysis", None, "completed", f"Bulk cleanup removed {len(ids)} deleted posts.")

    state["applied"] = True
    return {"removed": True, "deleted_count": len(ids)}


async def scan_deleted(dry_run: bool = True, state: dict | None = None) -> dict:
    """Check every connected-platform conversation to see if its source post is
    still live. With dry_run=True, only report the deleted ones. With
    dry_run=False, also remove them (conversation + discovered_posts row).

    `state`, when given, is updated with live progress for polling.

    Only platforms that are currently connected are scanned; conversations whose
    source could not be determined are left alone (never deleted on uncertainty).
    """
    supabase = get_supabase()

    connected = {
        c.platform
        for c in token_store.get_all_connections()
        if c.status == "connected" and c.platform in SUPPORTED_POSTING
    }
    if not connected:
        return {"checked": 0, "deleted": [], "deleted_count": 0, "dry_run": dry_run,
                "skipped": "no supported platforms connected"}

    convs = (
        supabase.table("conversations")
        .select("id, platform, post_url")
        .in_("platform", list(connected))
        .execute()
    ).data or []

    if state is not None:
        state["total"] = len(convs)

    # Still well inside platform rate limits (Mastodon allows 300 req / 5 min),
    # but ~2x faster than the old limit of 5 on a few hundred conversations.
    sem = asyncio.Semaphore(10)
    PER_CHECK_TIMEOUT = 10  # a hung platform must not stall the whole scan

    async def _check(conv: dict):
        async with sem:
            try:
                connector = get_connector(conv["platform"])
                connection = token_store.get_connection(conv["platform"])
                target = _resolve_target(supabase, conv["id"], conv)
                if not target:
                    return (conv, None)  # unknown — leave alone
                exists = await asyncio.wait_for(
                    connector.post_exists(connection, target=target),
                    timeout=PER_CHECK_TIMEOUT,
                )
                return (conv, exists)
            except Exception:
                return (conv, None)  # error/timeout — unknown, never delete
            finally:
                if state is not None:
                    state["checked"] += 1

    results = await asyncio.gather(*[_check(c) for c in convs])

    deleted: list[dict] = []
    for conv, exists in results:
        if exists is False:
            deleted.append(
                {"id": conv["id"], "platform": conv["platform"], "post_url": conv.get("post_url")}
            )

    if not dry_run and deleted:
        ids = [d["id"] for d in deleted]
        supabase.table("discovered_posts").delete().in_("conversation_id", ids).execute()
        supabase.table("conversations").delete().in_("id", ids).execute()
        log_task("analysis", None, "completed", f"Bulk cleanup removed {len(ids)} deleted posts.")

    return {
        "checked": len(convs),
        "deleted": deleted,
        "deleted_count": len(deleted),
        "removed": (not dry_run) and bool(deleted),
        "dry_run": dry_run,
    }


async def publish_post(platform: str, text: str, media: list | None = None) -> dict:
    """Publish a new standalone post (author's own thought + optional images) to
    `platform`. Raises ValueError with a clear message on any problem."""
    if platform not in SUPPORTED_STANDALONE:
        raise ValueError(
            f"Standalone posting is not supported for {platform}. "
            f"Currently supported: {', '.join(sorted(SUPPORTED_STANDALONE))}."
        )

    text = (text or "").strip()
    if not text and not media:
        raise ValueError("A post needs text or at least one image.")

    connection = token_store.get_connection(platform)
    if not connection or connection.status != "connected":
        raise ValueError(f"{platform} is not connected. Connect it in Settings first.")

    limit = PLATFORM_CHAR_LIMITS.get(platform)
    if limit and len(text) > limit:
        raise ValueError(
            f"This post is {len(text)} characters but {platform}'s limit is {limit}. "
            f"Shorten it and try again."
        )

    connector = get_connector(platform)
    try:
        result = await connector.create_post(connection, text=text, media=media or [])
        token_store.mark_used(platform)
        from app.services import replies
        replies.record_authored_post(platform, result, text, is_reply=False)
        token_store.log_event(platform, "fetch_success", "Standalone post published.")
        log_task("generation", None, "completed", f"Published standalone post to {platform}.")
        return result
    except Exception as exc:
        token_store.log_event(platform, "fetch_failed", f"Standalone post failed: {exc}")
        log_task("generation", None, "failed", f"Standalone post to {platform} failed: {exc}")
        raise ValueError(str(exc)) from exc


async def publish_reply(conversation_id: str, text: str) -> dict:
    """Post `text` as a reply to the conversation's original post. Returns the
    platform result (url/id). Raises ValueError with a clear message on any
    problem so the caller can surface it to the user."""
    supabase = get_supabase()

    conv_rows = (
        supabase.table("conversations").select("*").eq("id", conversation_id).limit(1).execute()
    ).data
    if not conv_rows:
        raise ValueError("Conversation not found.")
    conv = conv_rows[0]
    platform = conv["platform"]

    if platform not in SUPPORTED_POSTING:
        raise ValueError(
            f"Posting is not supported for {platform} yet. "
            f"Currently supported: {', '.join(sorted(SUPPORTED_POSTING))}."
        )

    connection = token_store.get_connection(platform)
    if not connection or connection.status != "connected":
        raise ValueError(f"{platform} is not connected. Connect it in Settings first.")

    # Enforce the platform's character limit with a clear message (rather than a
    # raw API rejection) so the author can shorten via Edit & Approve.
    limit = PLATFORM_CHAR_LIMITS.get(platform)
    if limit and len(text) > limit:
        raise ValueError(
            f"This reply is {len(text)} characters but {platform}'s limit is {limit}. "
            f"Use 'Edit & Approve' to shorten it, then post."
        )

    target = _resolve_target(supabase, conversation_id, conv)
    if not target:
        raise ValueError("No original post reference is available to reply to.")

    connector = get_connector(platform)
    try:
        result = await connector.post_reply(connection, text=text, target=target)
        token_store.mark_used(platform)
        if platform in {"bluesky", "mastodon"}:
            from app.services import replies
            replies.record_authored_post(platform, result, text, is_reply=True)
        token_store.log_event(platform, "fetch_success", "Reply posted.", {"conversation_id": conversation_id})
        log_task("generation", conversation_id, "completed", f"Posted reply to {platform}.")
        return result
    except Exception as exc:
        token_store.log_event(platform, "fetch_failed", f"Post failed: {exc}")
        log_task("generation", conversation_id, "failed", f"Post to {platform} failed: {exc}")
        raise ValueError(str(exc)) from exc
