"""Module 4 — discovery management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Query

from app.database import get_supabase
from app.envelope import fail, ok
from app.models.discovery import (
    CommunityCreate,
    CommunityUpdate,
    DiscoverySettingsUpdate,
)
from app.schemas.connections import PLATFORMS
from app.services import token_store
from app.services.connections.base import UniversalPost
from app.services.discovery import scheduler, store
from app.services.discovery.submitter import Submitter

router = APIRouter(prefix="/discovery", tags=["discovery"])


def _supabase():
    return get_supabase()


# ── Status ────────────────────────────────────────────

@router.get("/status")
async def status():
    try:
        sched = scheduler.get_status()
        settings = store.get_settings()
        last_run = (
            _supabase()
            .table("discovery_runs")
            .select("*")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        ).data
        connected = [
            c.platform for c in token_store.get_all_connections() if c.status == "connected"
        ]
        communities = (
            _supabase()
            .table("monitored_communities")
            .select("id", count="exact")
            .eq("is_active", True)
            .execute()
        )
        return ok(
            {
                "scheduler_running": sched.scheduler_running,
                "is_enabled": settings.is_enabled,
                "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
                "schedule_interval_minutes": sched.schedule_interval_minutes,
                "last_run": last_run[0] if last_run else None,
                "today_submitted": store.daily_conversation_count(),
                "today_limit": settings.max_conversations_per_day,
                "connected_platforms": connected,
                "monitored_communities": communities.count or 0,
            }
        )
    except Exception as exc:
        return fail(f"Failed to load discovery status: {exc}", 500)


@router.post("/trigger")
async def trigger(background_tasks: BackgroundTasks):
    try:
        run_id = scheduler.trigger_now("manual")
        return ok({"run_id": run_id, "status": "running"}, 202)
    except Exception as exc:
        return fail(f"Failed to trigger discovery: {exc}", 500)


# ── Runs ──────────────────────────────────────────────

@router.get("/runs")
async def list_runs(
    status: str | None = Query(None),
    trigger_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        query = _supabase().table("discovery_runs").select("*", count="exact")
        if status:
            query = query.eq("status", status)
        if trigger_type:
            query = query.eq("trigger_type", trigger_type)
        start = (page - 1) * page_size
        res = query.order("started_at", desc=True).range(start, start + page_size - 1).execute()
        return ok({"page": page, "page_size": page_size, "total": res.count or 0, "runs": res.data or []})
    except Exception as exc:
        return fail(f"Failed to list runs: {exc}", 500)


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    try:
        rows = _supabase().table("discovery_runs").select("*").eq("id", run_id).limit(1).execute().data
        if not rows:
            return fail("Run not found", 404)
        posts = (
            _supabase()
            .table("discovered_posts")
            .select("id, platform, community_name, relevance_score, status, conversation_id")
            .eq("worker_run_id", run_id)
            .order("relevance_score", desc=True)
            .execute()
        ).data or []
        return ok({"run": rows[0], "posts": posts})
    except Exception as exc:
        return fail(f"Failed to load run: {exc}", 500)


# ── Posts ─────────────────────────────────────────────

@router.get("/posts")
async def list_posts(
    platform: str | None = Query(None),
    status: str | None = Query(None),
    min_relevance_score: float | None = Query(None, ge=0, le=1),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        # DB-level filters that don't depend on the joined analysis score.
        query = _supabase().table("discovered_posts").select("*")
        if platform:
            query = query.eq("platform", platform)
        if status:
            query = query.eq("status", status)
        if date_from:
            query = query.gte("fetched_at", date_from)
        if date_to:
            query = query.lte("fetched_at", date_to + "T23:59:59")
        rows = query.limit(2000).execute().data or []

        # Attach the authoritative Module 7 analysis relevance for submitted posts.
        conv_ids = [p["conversation_id"] for p in rows if p.get("conversation_id")]
        if conv_ids:
            arows = (
                _supabase()
                .table("conversation_analysis")
                .select("conversation_id, relevance_score")
                .in_("conversation_id", conv_ids)
                .execute()
            ).data or []
            by_conv = {r["conversation_id"]: r["relevance_score"] for r in arows}
            for p in rows:
                p["analysis_score"] = by_conv.get(p.get("conversation_id"))

        # Effective score = analysis score once available, else the pre-screen score.
        def effective(p):
            s = p.get("analysis_score")
            return s if s is not None else p.get("relevance_score")

        # Filter and sort by the effective score (matches what the card shows).
        if min_relevance_score is not None:
            rows = [p for p in rows if (effective(p) or 0) >= min_relevance_score]
        rows.sort(key=lambda p: (effective(p) is not None, effective(p) or 0), reverse=True)

        total = len(rows)
        start = (page - 1) * page_size
        posts = rows[start : start + page_size]
        return ok({"page": page, "page_size": page_size, "total": total, "posts": posts})
    except Exception as exc:
        return fail(f"Failed to list posts: {exc}", 500)


@router.get("/posts/{post_id}")
async def get_post(post_id: str):
    try:
        rows = _supabase().table("discovered_posts").select("*").eq("id", post_id).limit(1).execute().data
        if not rows:
            return fail("Post not found", 404)
        return ok({"post": rows[0]})
    except Exception as exc:
        return fail(f"Failed to load post: {exc}", 500)


@router.post("/posts/{post_id}/submit")
async def submit_post(post_id: str):
    try:
        rows = _supabase().table("discovered_posts").select("*").eq("id", post_id).limit(1).execute().data
        if not rows:
            return fail("Post not found", 404)
        row = rows[0]
        if row.get("conversation_id"):
            return ok({"conversation_id": row["conversation_id"], "status": "already_submitted"})
        post = UniversalPost(
            platform=row["platform"],
            post_id=row["post_id"],
            post_url=row.get("post_url") or "",
            author_name=row.get("author_name") or "",
            author_id=row.get("author_id") or "",
            content=row["content"],
            posted_at=datetime.now(timezone.utc),
            title=row.get("title"),
            thread_content=row.get("thread_content"),
            community_name=row.get("community_name"),
            community_id=row.get("community_id"),
        )
        conversation_id = await Submitter().submit(post)
        _supabase().table("discovered_posts").update(
            {"status": "submitted", "conversation_id": conversation_id}
        ).eq("id", post_id).execute()
        return ok({"conversation_id": conversation_id, "status": "submitted"}, 202)
    except Exception as exc:
        return fail(f"Failed to submit post: {exc}", 500)


# ── Communities ───────────────────────────────────────

@router.get("/communities")
async def list_communities():
    try:
        rows = (
            _supabase().table("monitored_communities").select("*").order("platform").execute()
        ).data or []
        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r["platform"], []).append(r)
        return ok({"communities": grouped, "total": len(rows)})
    except Exception as exc:
        return fail(f"Failed to list communities: {exc}", 500)


@router.post("/communities")
async def add_community(body: CommunityCreate):
    if body.platform not in PLATFORMS:
        return fail(f"Unsupported platform. Allowed: {', '.join(PLATFORMS)}", 422)
    connection = token_store.get_connection(body.platform)
    if not connection or connection.status != "connected":
        return fail(f"No connected account for {body.platform}. Connect it first.", 400)
    try:
        row = (
            _supabase()
            .table("monitored_communities")
            .insert(
                {
                    "platform": body.platform,
                    "community_id": body.community_id,
                    "community_name": body.community_name,
                    "keywords": body.keywords,
                    "priority": body.priority,
                }
            )
            .execute()
        ).data[0]
        return ok({"community": row}, 201)
    except Exception as exc:
        return fail(f"Failed to add community (already exists?): {exc}", 400)


@router.patch("/communities/{community_id}")
async def update_community(community_id: str, body: CommunityUpdate):
    try:
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if not fields:
            return fail("No fields to update", 400)
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        res = (
            _supabase()
            .table("monitored_communities")
            .update(fields)
            .eq("id", community_id)
            .execute()
        ).data
        if not res:
            return fail("Community not found", 404)
        return ok({"community": res[0]})
    except Exception as exc:
        return fail(f"Failed to update community: {exc}", 500)


@router.delete("/communities/{community_id}")
async def delete_community(community_id: str):
    try:
        _supabase().table("monitored_communities").delete().eq("id", community_id).execute()
        return ok({"deleted": True})
    except Exception as exc:
        return fail(f"Failed to delete community: {exc}", 500)


# ── Settings ──────────────────────────────────────────

@router.get("/settings")
async def get_settings():
    try:
        s = store.get_settings()
        return ok(
            {
                "is_enabled": s.is_enabled,
                "schedule_interval_minutes": s.schedule_interval_minutes,
                "max_posts_per_run": s.max_posts_per_run,
                "max_conversations_per_day": s.max_conversations_per_day,
                "min_relevance_score": s.min_relevance_score,
                "scoring_batch_size": s.scoring_batch_size,
            }
        )
    except Exception as exc:
        return fail(f"Failed to load settings: {exc}", 500)


@router.post("/settings")
async def update_settings(body: DiscoverySettingsUpdate):
    try:
        before = store.get_settings()
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = store.update_settings(fields)
        # Reschedule if the interval changed.
        if (
            body.schedule_interval_minutes is not None
            and body.schedule_interval_minutes != before.schedule_interval_minutes
        ):
            scheduler.reschedule(updated.schedule_interval_minutes)
        return ok(
            {
                "is_enabled": updated.is_enabled,
                "schedule_interval_minutes": updated.schedule_interval_minutes,
                "max_posts_per_run": updated.max_posts_per_run,
                "max_conversations_per_day": updated.max_conversations_per_day,
                "min_relevance_score": updated.min_relevance_score,
                "scoring_batch_size": updated.scoring_batch_size,
            }
        )
    except Exception as exc:
        return fail(f"Failed to update settings: {exc}", 500)
