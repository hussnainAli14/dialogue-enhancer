"""Module 7 — conversation endpoints."""

import traceback

from fastapi import APIRouter, BackgroundTasks, Query

from app.database import detach_feedback_log, get_supabase, log_task
from app.envelope import fail, ok
from app.models.conversations import ConversationSubmit
from app.services.analysis import run_pipeline

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/submit")
async def submit_conversation(body: ConversationSubmit, background_tasks: BackgroundTasks):
    try:
        allowed_sources = {"manual", "linkedin_clipper", "reddit_clipper"}
        source = body.source if body.source in allowed_sources else "manual"

        supabase = get_supabase()
        record = (
            supabase.table("conversations")
            .insert(
                {
                    "platform": body.platform,
                    "post_url": body.post_url,
                    "post_author": body.post_author,
                    "original_post": body.original_post,
                    "full_thread": body.full_thread,
                    "analysis_status": "pending",
                    "source": source,
                }
            )
            .execute()
        ).data[0]

        log_task("analysis", record["id"], "started", f"Submitted from {body.platform}")
        background_tasks.add_task(run_pipeline, record["id"])
        return ok({"conversation_id": record["id"], "status": "pending"}, 202)
    except Exception:
        return fail("Failed to submit conversation", 500)


@router.get("")
async def list_conversations(
    status: str | None = Query(None),
    platform: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        supabase = get_supabase()
        query = supabase.table("conversations").select("*", count="exact")
        if status:
            query = query.eq("analysis_status", status)
        if platform:
            query = query.eq("platform", platform)

        start = (page - 1) * page_size
        response = (
            query.order("submitted_at", desc=True).range(start, start + page_size - 1).execute()
        )
        convs = response.data or []
        conv_ids = [c["id"] for c in convs]

        analyses = {}
        draft_counts: dict[str, int] = {}
        posted_ids: set[str] = set()
        if conv_ids:
            for a in (
                supabase.table("conversation_analysis")
                .select("conversation_id, relevance_score, central_topic")
                .in_("conversation_id", conv_ids)
                .execute()
            ).data or []:
                analyses[a["conversation_id"]] = a
            for d in (
                supabase.table("response_drafts")
                .select("conversation_id, status")
                .in_("conversation_id", conv_ids)
                .execute()
            ).data or []:
                cid = d["conversation_id"]
                draft_counts[cid] = draft_counts.get(cid, 0) + 1
                if d.get("status") == "posted":
                    posted_ids.add(cid)

        return ok(
            {
                "page": page,
                "page_size": page_size,
                "total": response.count or len(convs),
                "conversations": [
                    {
                        "id": c["id"],
                        "platform": c["platform"],
                        "post_author": c.get("post_author"),
                        "original_post": c.get("original_post") or "",
                        "central_topic": (analyses.get(c["id"]) or {}).get("central_topic"),
                        "analysis_status": c["analysis_status"],
                        "relevance_score": (analyses.get(c["id"]) or {}).get("relevance_score"),
                        "submitted_at": c["submitted_at"],
                        "draft_count": draft_counts.get(c["id"], 0),
                        "has_posted_reply": c["id"] in posted_ids,
                        "source": c.get("source") or "manual",
                        "is_reply_to_me": c.get("is_reply_to_me") or False,
                        "parent_post_url": c.get("parent_post_url"),
                    }
                    for c in convs
                ],
            }
        )
    except Exception:
        return fail("Failed to list conversations", 500)


@router.post("/{conversation_id}/generate-drafts")
async def generate_drafts(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    force: bool = Query(False),
):
    """Run the analysis + drafting pipeline on demand — used for replies-to-you,
    which are surfaced without auto-drafting. Idempotent-ish: re-runs analysis.
    force=true still writes drafts when analysis says DO_NOT_COMMENT."""
    try:
        supabase = get_supabase()
        conv = (
            supabase.table("conversations").select("id, analysis_status")
            .eq("id", conversation_id).limit(1).execute()
        ).data
        if not conv:
            return fail("Conversation not found", 404)
        supabase.table("conversations").update({"analysis_status": "pending"}).eq(
            "id", conversation_id
        ).execute()
        log_task(
            "analysis",
            conversation_id,
            "started",
            "On-demand draft generation" + (" (forced)." if force else "."),
        )
        background_tasks.add_task(run_pipeline, conversation_id, force)
        return ok({"conversation_id": conversation_id, "status": "pending"}, 202)
    except Exception:
        return fail("Failed to start draft generation", 500)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    try:
        supabase = get_supabase()
        convs = (
            supabase.table("conversations").select("*").eq("id", conversation_id).execute()
        ).data
        if not convs:
            return fail("Conversation not found", 404)

        analysis = (
            supabase.table("conversation_analysis")
            .select("*")
            .eq("conversation_id", conversation_id)
            .execute()
        ).data
        drafts = (
            supabase.table("response_drafts")
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .execute()
        ).data or []

        for d in drafts:
            d.pop("source_chunk_ids", None)  # internal linkage, not needed by dashboard

        conv = convs[0]
        conv["analysis"] = analysis[0] if analysis else None
        conv["drafts"] = drafts
        return ok(conv)
    except Exception:
        return fail("Failed to fetch conversation", 500)


@router.post("/cleanup-deleted")
async def cleanup_deleted():
    """Start a background scan for conversations whose source post was deleted.

    One live platform call per conversation means this runs for a minute or
    more, so it returns a scan_id immediately and the client polls for progress
    rather than holding the request open.
    """
    try:
        from app.services.posting import start_scan

        return ok({"scan_id": start_scan(), "status": "running"}, 202)
    except Exception as exc:
        return fail(f"Failed to start cleanup scan: {exc}", 500)


@router.get("/cleanup-scans/{scan_id}")
async def cleanup_scan_status(scan_id: str):
    """Progress and results for a running or finished cleanup scan."""
    from app.services.posting import get_scan

    state = get_scan(scan_id)
    if not state:
        return fail("Scan not found or expired. Run the scan again.", 404)
    return ok(state)


@router.post("/cleanup-scans/{scan_id}/apply")
async def cleanup_scan_apply(scan_id: str):
    """Delete the conversations the given completed scan flagged."""
    from app.services.posting import apply_scan

    try:
        return ok(apply_scan(scan_id))
    except ValueError as exc:
        return fail(str(exc), 400)
    except Exception as exc:
        # A bare "Cleanup failed" hides why; print the trace so the server log
        # carries the real cause.
        traceback.print_exc()
        return fail(f"Cleanup failed: {type(exc).__name__}: {exc}", 500)


@router.get("/{conversation_id}/source-status")
async def source_status(conversation_id: str):
    """Fetch fresh data from the platform to see if the original post still
    exists (so the author knows if it was deleted before replying)."""
    try:
        from app.services.posting import check_source_alive

        return ok(await check_source_alive(conversation_id))
    except ValueError as exc:
        return fail(str(exc), 404)
    except Exception as exc:
        return fail(f"Failed to check source: {exc}", 500)


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Remove a conversation from the portal (e.g. its source post was deleted).
    Cascades to its analysis and drafts; also clears the discovered_posts row."""
    try:
        supabase = get_supabase()
        exists = (
            supabase.table("conversations").select("id").eq("id", conversation_id).execute()
        ).data
        if not exists:
            return fail("Conversation not found", 404)
        # Remove the discovered_posts row too (FK is ON DELETE SET NULL, so it
        # would otherwise linger with a null conversation_id).
        detach_feedback_log([conversation_id])
        supabase.table("discovered_posts").delete().eq("conversation_id", conversation_id).execute()
        supabase.table("conversations").delete().eq("id", conversation_id).execute()
        return ok({"deleted": True, "conversation_id": conversation_id})
    except Exception as exc:
        return fail(f"Failed to delete conversation: {exc}", 500)
