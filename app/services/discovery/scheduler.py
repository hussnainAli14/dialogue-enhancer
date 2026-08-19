"""APScheduler setup for the discovery worker (runs in FastAPI's event loop)."""

from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import get_supabase, log_task
from app.models.discovery import SchedulerStatus
from app.services.discovery import store

JOB_ID = "discovery_worker"

_scheduler: AsyncIOScheduler | None = None


async def _run_job() -> None:
    """Scheduled entry point. The worker itself checks is_enabled and the daily
    limit, so we always call it and let it decide whether to act."""
    from app.services.discovery.worker import DiscoveryWorker

    try:
        await DiscoveryWorker().run("scheduled")
    except Exception as exc:  # APScheduler would swallow this; log it too.
        log_task("analysis", None, "failed", f"Scheduled discovery job error: {exc}")


def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return
    interval = store.get_settings().schedule_interval_minutes
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_job,
        trigger=IntervalTrigger(minutes=interval),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    log_task("analysis", None, "started", f"Discovery scheduler started (every {interval} min).")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log_task("analysis", None, "completed", "Discovery scheduler stopped.")
    _scheduler = None


def reschedule(interval_minutes: int) -> None:
    """Change the job interval without restarting the scheduler."""
    if _scheduler and _scheduler.get_job(JOB_ID):
        _scheduler.reschedule_job(JOB_ID, trigger=IntervalTrigger(minutes=interval_minutes))
        log_task("analysis", None, "completed", f"Discovery rescheduled to {interval_minutes} min.")


def get_status() -> SchedulerStatus:
    running = bool(_scheduler and _scheduler.running)
    next_run = None
    if running:
        job = _scheduler.get_job(JOB_ID)
        next_run = getattr(job, "next_run_time", None)
    return SchedulerStatus(
        scheduler_running=running,
        next_run_at=next_run,
        schedule_interval_minutes=store.get_settings().schedule_interval_minutes,
    )


def trigger_now(trigger_type: str = "manual") -> str:
    """Create a run row immediately, launch the worker in the background, and
    return the run_id for tracking."""
    row = (
        get_supabase()
        .table("discovery_runs")
        .insert({"trigger_type": trigger_type, "status": "running"})
        .execute()
    ).data[0]
    run_id = row["id"]

    from app.services.discovery.worker import DiscoveryWorker

    asyncio.create_task(DiscoveryWorker().run(trigger_type, run_id=run_id))
    return run_id
