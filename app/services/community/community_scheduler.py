"""Adds the community-discovery job to the existing Module 4 scheduler."""

from __future__ import annotations

import asyncio

from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings as env_settings
from app.database import get_supabase, log_task
from app.services.discovery.scheduler import current_scheduler

JOB_ID = "community_discovery_worker"


def _schedule_hours() -> int:
    try:
        rows = get_supabase().table("discovery_settings").select("community_schedule_hours").limit(1).execute().data
        if rows and rows[0].get("community_schedule_hours"):
            return int(rows[0]["community_schedule_hours"])
    except Exception:
        pass
    return env_settings.COMMUNITY_DISCOVERY_SCHEDULE_HOURS


async def _run_community_job() -> None:
    from app.services.community.discovery_worker import CommunityDiscoveryWorker

    try:
        # Respect the enable flag.
        rows = get_supabase().table("discovery_settings").select("community_discovery_enabled").limit(1).execute().data
        if rows and rows[0].get("community_discovery_enabled") is False:
            return
        await CommunityDiscoveryWorker().run("scheduled")
    except Exception as exc:
        log_task("analysis", None, "failed", f"Scheduled community discovery error: {exc}")


def add_community_discovery_job() -> None:
    scheduler = current_scheduler()
    if not scheduler:
        return
    scheduler.add_job(
        _run_community_job,
        trigger=IntervalTrigger(hours=_schedule_hours()),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    log_task("analysis", None, "started", f"Community discovery scheduled (every {_schedule_hours()}h).")


def reschedule_community_discovery(hours: int) -> None:
    scheduler = current_scheduler()
    if scheduler and scheduler.get_job(JOB_ID):
        scheduler.reschedule_job(JOB_ID, trigger=IntervalTrigger(hours=hours))
        log_task("analysis", None, "completed", f"Community discovery rescheduled to {hours}h.")


def community_trigger_now(trigger_type: str = "manual", modes=None, platforms=None) -> str:
    """Create a run row, launch the worker in the background, return the run_id."""
    row = (
        get_supabase()
        .table("community_discovery_runs")
        .insert({"trigger_type": trigger_type, "discovery_modes": modes or ["keyword", "people_based"], "status": "running"})
        .execute()
    ).data[0]
    run_id = row["id"]

    from app.services.community.discovery_worker import CommunityDiscoveryWorker

    asyncio.create_task(
        CommunityDiscoveryWorker().run(trigger_type, modes=modes, platforms=platforms, run_id=run_id)
    )
    return run_id
