"""Module 3 — community discovery, topics, people, suggestions endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.database import get_supabase
from app.envelope import fail, ok
from app.models.community import (
    ApproveAllBody,
    ApproveBody,
    MonitoredCreate,
    MonitoredUpdate,
    PersonCreate,
    PersonUpdate,
    RejectAllBody,
    RejectBody,
    TopicCreate,
    TopicUpdate,
)
from app.schemas.connections import PLATFORMS
from app.services.community.community_scheduler import community_trigger_now

router = APIRouter(prefix="/community", tags=["community"])


def _sb():
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Topics ────────────────────────────────────────────
@router.get("/topics")
async def list_topics():
    try:
        rows = _sb().table("discovery_topics").select("*").order("created_at").execute().data or []
        return ok({"topics": rows})
    except Exception as exc:
        return fail(f"Failed to load topics: {exc}", 500)


@router.post("/topics")
async def add_topic(body: TopicCreate):
    try:
        row = (
            _sb().table("discovery_topics").insert(
                {"topic": body.topic, "keywords": body.keywords, "description": body.description}
            ).execute()
        ).data[0]
        return ok({"topic": row}, 201)
    except Exception as exc:
        return fail(f"Failed to add topic: {exc}", 400)


@router.patch("/topics/{topic_id}")
async def update_topic(topic_id: str, body: TopicUpdate):
    try:
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if not fields:
            return fail("No fields to update", 400)
        fields["updated_at"] = _now()
        rows = _sb().table("discovery_topics").update(fields).eq("id", topic_id).execute().data
        if not rows:
            return fail("Topic not found", 404)
        return ok({"topic": rows[0]})
    except Exception as exc:
        return fail(f"Failed to update topic: {exc}", 500)


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str):
    try:
        _sb().table("discovery_topics").delete().eq("id", topic_id).execute()
        return ok({"deleted": True})
    except Exception as exc:
        return fail(f"Failed to delete topic: {exc}", 500)


# ── People ────────────────────────────────────────────
@router.get("/people")
async def list_people():
    try:
        rows = _sb().table("monitored_people").select("*").order("created_at").execute().data or []
        return ok({"people": rows})
    except Exception as exc:
        return fail(f"Failed to load people: {exc}", 500)


@router.post("/people")
async def add_person(body: PersonCreate):
    handles = {k: v for k, v in (body.platform_handles or {}).items() if v}
    if not handles:
        return fail("Provide at least one platform handle.", 400)
    try:
        row = (
            _sb().table("monitored_people").insert(
                {"name": body.name, "description": body.description, "platform_handles": handles}
            ).execute()
        ).data[0]
        return ok({"person": row}, 201)
    except Exception as exc:
        return fail(f"Failed to add person: {exc}", 400)


@router.patch("/people/{person_id}")
async def update_person(person_id: str, body: PersonUpdate):
    try:
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if not fields:
            return fail("No fields to update", 400)
        fields["updated_at"] = _now()
        rows = _sb().table("monitored_people").update(fields).eq("id", person_id).execute().data
        if not rows:
            return fail("Person not found", 404)
        return ok({"person": rows[0]})
    except Exception as exc:
        return fail(f"Failed to update person: {exc}", 500)


@router.delete("/people/{person_id}")
async def delete_person(person_id: str):
    try:
        _sb().table("monitored_people").delete().eq("id", person_id).execute()
        return ok({"deleted": True})
    except Exception as exc:
        return fail(f"Failed to delete person: {exc}", 500)


# ── Discovery ─────────────────────────────────────────
@router.post("/discover")
async def discover(body: dict | None = None):
    try:
        body = body or {}
        run_id = community_trigger_now("manual", modes=body.get("modes"), platforms=body.get("platforms"))
        return ok({"run_id": run_id, "status": "running"}, 202)
    except Exception as exc:
        return fail(f"Failed to trigger community discovery: {exc}", 500)


@router.get("/discover/runs")
async def list_runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    try:
        start = (page - 1) * page_size
        res = (
            _sb().table("community_discovery_runs").select("*", count="exact")
            .order("started_at", desc=True).range(start, start + page_size - 1).execute()
        )
        return ok({"page": page, "page_size": page_size, "total": res.count or 0, "runs": res.data or []})
    except Exception as exc:
        return fail(f"Failed to load runs: {exc}", 500)


@router.get("/discover/runs/{run_id}")
async def get_run(run_id: str):
    try:
        rows = _sb().table("community_discovery_runs").select("*").eq("id", run_id).limit(1).execute().data
        if not rows:
            return fail("Run not found", 404)
        return ok({"run": rows[0]})
    except Exception as exc:
        return fail(f"Failed to load run: {exc}", 500)


# ── Suggestions (approval queue) ──────────────────────
@router.get("/suggestions")
async def list_suggestions(
    platform: str | None = Query(None),
    status: str | None = Query("pending"),
    min_score: float | None = Query(None, ge=0, le=1),
):
    try:
        query = _sb().table("community_suggestions").select("*")
        if platform:
            query = query.eq("platform", platform)
        if status:
            query = query.eq("status", status)
        if min_score is not None:
            query = query.gte("relevance_score", min_score)
        rows = query.order("relevance_score", desc=True, nullsfirst=False).execute().data or []

        def _count(s):
            return (
                _sb().table("community_suggestions").select("id", count="exact").eq("status", s).execute().count
                or 0
            )

        return ok({
            "suggestions": rows,
            "counts": {"pending": _count("pending"), "approved": _count("approved"), "rejected": _count("rejected")},
        })
    except Exception as exc:
        return fail(f"Failed to load suggestions: {exc}", 500)


@router.post("/suggestions/approve-all")
async def approve_all(body: ApproveAllBody):
    try:
        rows = (
            _sb().table("community_suggestions").select("*")
            .eq("status", "pending").gte("relevance_score", body.min_score).execute()
        ).data or []
        approved = 0
        for s in rows:
            if _approve_one(s):
                approved += 1
        return ok({"approved": approved})
    except Exception as exc:
        return fail(f"Bulk approve failed: {exc}", 500)


@router.post("/suggestions/reject-all")
async def reject_all(body: RejectAllBody):
    try:
        rows = (
            _sb().table("community_suggestions").select("id")
            .eq("status", "pending").lte("relevance_score", body.max_score).execute()
        ).data or []
        ids = [r["id"] for r in rows]
        if ids:
            _sb().table("community_suggestions").update(
                {"status": "rejected", "rejection_reason": body.rejection_reason, "rejected_at": _now()}
            ).in_("id", ids).execute()
        return ok({"rejected": len(ids)})
    except Exception as exc:
        return fail(f"Bulk reject failed: {exc}", 500)


@router.get("/suggestions/{suggestion_id}")
async def get_suggestion(suggestion_id: str):
    try:
        rows = _sb().table("community_suggestions").select("*").eq("id", suggestion_id).limit(1).execute().data
        if not rows:
            return fail("Suggestion not found", 404)
        return ok({"suggestion": rows[0]})
    except Exception as exc:
        return fail(f"Failed to load suggestion: {exc}", 500)


def _approve_one(s: dict, keywords: list[str] | None = None) -> dict | None:
    """Create a monitored_communities row from a suggestion and mark it approved."""
    kws = keywords if keywords is not None else (s.get("suggested_keywords") or [])
    try:
        _sb().table("monitored_communities").upsert(
            {
                "platform": s["platform"],
                "community_id": s["community_id"],
                "community_name": s["community_name"],
                "keywords": kws,
                "is_active": True,
                "priority": 1,
            },
            on_conflict="platform,community_id",
        ).execute()
        _sb().table("community_suggestions").update(
            {"status": "approved", "approved_at": _now()}
        ).eq("id", s["id"]).execute()
        return s
    except Exception:
        return None


@router.post("/suggestions/{suggestion_id}/approve")
async def approve_suggestion(suggestion_id: str, body: ApproveBody | None = None):
    try:
        rows = _sb().table("community_suggestions").select("*").eq("id", suggestion_id).limit(1).execute().data
        if not rows:
            return fail("Suggestion not found", 404)
        keywords = body.keywords if body else None
        if not _approve_one(rows[0], keywords):
            return fail("Failed to approve suggestion", 500)
        community = (
            _sb().table("monitored_communities").select("*")
            .eq("platform", rows[0]["platform"]).eq("community_id", rows[0]["community_id"]).limit(1).execute()
        ).data
        return ok({"community": community[0] if community else None})
    except Exception as exc:
        return fail(f"Failed to approve: {exc}", 500)


@router.post("/suggestions/{suggestion_id}/reject")
async def reject_suggestion(suggestion_id: str, body: RejectBody | None = None):
    try:
        rows = _sb().table("community_suggestions").update(
            {"status": "rejected", "rejection_reason": body.rejection_reason if body else None, "rejected_at": _now()}
        ).eq("id", suggestion_id).execute().data
        if not rows:
            return fail("Suggestion not found", 404)
        return ok({"suggestion": rows[0]})
    except Exception as exc:
        return fail(f"Failed to reject: {exc}", 500)


# ── Monitored communities (grouped) ───────────────────
@router.get("/monitored")
async def list_monitored():
    try:
        rows = _sb().table("monitored_communities").select("*").order("platform").execute().data or []
        grouped: dict[str, list] = {}
        for r in rows:
            grouped.setdefault(r["platform"], []).append(r)
        return ok({"communities": grouped, "total": len(rows)})
    except Exception as exc:
        return fail(f"Failed to load monitored communities: {exc}", 500)


@router.post("/monitored")
async def add_monitored(body: MonitoredCreate):
    if body.platform not in PLATFORMS:
        return fail(f"Unsupported platform. Allowed: {', '.join(PLATFORMS)}", 422)
    try:
        row = (
            _sb().table("monitored_communities").insert(
                {
                    "platform": body.platform,
                    "community_id": body.community_id,
                    "community_name": body.community_name,
                    "keywords": body.keywords,
                    "priority": body.priority,
                }
            ).execute()
        ).data[0]
        return ok({"community": row}, 201)
    except Exception as exc:
        return fail(f"Failed to add community (already exists?): {exc}", 400)


@router.patch("/monitored/{community_id}")
async def update_monitored(community_id: str, body: MonitoredUpdate):
    try:
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if not fields:
            return fail("No fields to update", 400)
        fields["updated_at"] = _now()
        rows = _sb().table("monitored_communities").update(fields).eq("id", community_id).execute().data
        if not rows:
            return fail("Community not found", 404)
        return ok({"community": rows[0]})
    except Exception as exc:
        return fail(f"Failed to update community: {exc}", 500)


@router.delete("/monitored/{community_id}")
async def delete_monitored(community_id: str):
    try:
        _sb().table("monitored_communities").delete().eq("id", community_id).execute()
        return ok({"deleted": True})
    except Exception as exc:
        return fail(f"Failed to delete community: {exc}", 500)
