"""Module 7 — conversation endpoints."""

from fastapi import APIRouter, BackgroundTasks, Query

from app.database import get_supabase, log_task
from app.envelope import fail, ok
from app.models.conversations import ConversationSubmit
from app.services.analysis import run_pipeline

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/submit")
async def submit_conversation(body: ConversationSubmit, background_tasks: BackgroundTasks):
    try:
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
                    }
                    for c in convs
                ],
            }
        )
    except Exception:
        return fail("Failed to list conversations", 500)


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
async def cleanup_deleted(dry_run: bool = Query(True)):
    """Scan all connected Bluesky/Mastodon conversations for deleted source
    posts. dry_run=true reports them; dry_run=false also removes them."""
    try:
        from app.services.posting import scan_deleted

        return ok(await scan_deleted(dry_run=dry_run))
    except Exception as exc:
        return fail(f"Cleanup failed: {exc}", 500)


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
        supabase.table("discovered_posts").delete().eq("conversation_id", conversation_id).execute()
        supabase.table("conversations").delete().eq("id", conversation_id).execute()
        return ok({"deleted": True, "conversation_id": conversation_id})
    except Exception as exc:
        return fail(f"Failed to delete conversation: {exc}", 500)
