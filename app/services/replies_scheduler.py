"""Adds the reply-tracking poll to the shared discovery scheduler."""

from __future__ import annotations

from apscheduler.triggers.interval import IntervalTrigger

from app.database import log_task

JOB_ID = "reply_tracker"
INTERVAL_MINUTES = 15


async def _run_job() -> None:
    from app.services.replies import poll_replies

    try:
        await poll_replies()
    except Exception as exc:
        log_task("analysis", None, "failed", f"Reply-tracking job error: {exc}")


def add_reply_tracking_job() -> None:
    """Attach the reply poll to the running discovery scheduler. Safe no-op if
    the scheduler is not running."""
    from app.services.discovery.scheduler import current_scheduler

    scheduler = current_scheduler()
    if not scheduler:
        return
    scheduler.add_job(
        _run_job,
        trigger=IntervalTrigger(minutes=INTERVAL_MINUTES),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    log_task("analysis", None, "started", f"Reply tracker started (every {INTERVAL_MINUTES} min).")
