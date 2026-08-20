"""Module 4 — the discovery worker orchestrator."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app.database import get_supabase, log_task
from app.models.discovery import DiscoveryRunResult
from app.services import token_store
from app.services.connections.base import UniversalPost
from app.services.connections.factory import PlatformFetchService
from app.services.discovery import store
from app.services.discovery.deduplicator import Deduplicator
from app.services.discovery.scorer import Scorer
from app.services.discovery.submitter import Submitter


def _now():
    return datetime.now(timezone.utc)


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _post_row(post: UniversalPost, run_id: str) -> dict:
    return {
        "platform": post.platform,
        "post_id": post.post_id,
        "post_url": post.post_url,
        "author_name": post.author_name,
        "author_id": post.author_id,
        "title": post.title,
        "content": post.content,
        "thread_content": post.thread_content,
        "community_name": post.community_name,
        "community_id": post.community_id,
        "posted_at": _iso(post.posted_at),
        "engagement_score": post.engagement_score,
        "status": "fetched",
        "worker_run_id": run_id,
    }


class DiscoveryWorker:
    def __init__(self):
        self.supabase = get_supabase()
        self.fetcher = PlatformFetchService()
        self.dedup = Deduplicator()
        self.scorer = Scorer()
        self.submitter = Submitter()

    async def run(self, trigger_type: str = "scheduled", run_id: str | None = None) -> DiscoveryRunResult:
        run_id = run_id or self._create_run(trigger_type)
        started = time.monotonic()
        result = DiscoveryRunResult(run_id=run_id, status="running")
        try:
            settings = store.get_settings()

            # STEP 1 — enabled / daily-limit guards
            if not settings.is_enabled:
                return self._finish(run_id, result, "completed", started, "Discovery paused.")
            daily = store.daily_conversation_count()
            if daily >= settings.max_conversations_per_day:
                return self._finish(
                    run_id, result, "completed", started,
                    f"Daily limit reached ({daily}/{settings.max_conversations_per_day}).",
                )
            log_task("analysis", run_id, "started", f"Discovery run ({trigger_type})")

            # STEP 2 — communities
            communities = store.active_communities()
            if not communities:
                return self._finish(
                    run_id, result, "completed", started,
                    "No active communities configured. Add some to start discovering.",
                )
            grouped: dict[str, list[str]] = {}
            all_keywords: set[str] = set()
            since_candidates: list[datetime] = []
            for c in communities:
                grouped.setdefault(c["platform"], []).append(c["community_id"])
                all_keywords.update(c.get("keywords") or [])
                if c.get("last_fetched_at"):
                    since_candidates.append(_parse(c["last_fetched_at"]))

            # Only keep platforms that are actually connected.
            connected = {
                c.platform for c in token_store.get_all_connections() if c.status == "connected"
            }
            grouped = {p: ids for p, ids in grouped.items() if p in connected}
            result.platforms_checked = list(grouped.keys())
            if not grouped:
                return self._finish(
                    run_id, result, "completed", started,
                    "No connected platforms among configured communities.",
                )

            # STEP 3 — fetch
            since = min(since_candidates) if since_candidates else _now() - timedelta(hours=24)
            posts = await self.fetcher.fetch_from_all_platforms(
                keywords=list(all_keywords),
                communities=grouped,
                since=since,
                limit_per_platform=settings.max_posts_per_run,
            )
            result.posts_fetched = len(posts)
            self._touch_communities(communities, grouped, len(posts))

            # STEP 4 — deduplicate + store
            new_posts = await self.dedup.filter_new(posts)
            result.posts_duplicated = len(posts) - len(new_posts)
            if new_posts:
                try:
                    self.supabase.table("discovered_posts").insert(
                        [_post_row(p, run_id) for p in new_posts]
                    ).execute()
                except Exception as exc:
                    # Unique-constraint race: fall back to per-row inserts.
                    log_task("analysis", run_id, "failed", f"Batch insert fallback: {exc}")
                    new_posts = self._insert_individually(new_posts, run_id)
            self._update_run(run_id, {
                "posts_fetched": result.posts_fetched,
                "posts_duplicated": result.posts_duplicated,
            })

            # STEP 5 — score
            scored = await self.scorer.score_batch(new_posts, settings)
            for sp in scored:
                self._update_post(sp.post, {
                    "relevance_score": sp.final_score,
                    "relevance_reasoning": sp.reasoning,
                    "status": "scored",
                })
            result.posts_scored = len(scored)
            self._update_run(run_id, {"posts_scored": result.posts_scored})

            # STEP 6 — filter + rank
            passing = [s for s in scored if s.final_score >= settings.min_relevance_score]
            passing.sort(key=lambda s: s.final_score, reverse=True)
            remaining = max(0, settings.max_conversations_per_day - store.daily_conversation_count())
            to_submit = passing[:remaining]
            submit_keys = {(s.post.platform, s.post.post_id) for s in to_submit}
            # Everything scored but not chosen for submission = filtered_out.
            filtered_count = 0
            for s in scored:
                if (s.post.platform, s.post.post_id) not in submit_keys:
                    self._update_post(s.post, {"status": "filtered_out"})
                    filtered_count += 1
            result.posts_filtered = filtered_count

            # STEP 7 — submit to Module 7
            submitted = 0
            for s in to_submit:
                # Re-check the daily limit before EACH submit (DB-level, concurrency-safe).
                if store.daily_conversation_count() >= settings.max_conversations_per_day:
                    self._update_post(s.post, {"status": "filtered_out"})
                    continue
                try:
                    conversation_id = await self.submitter.submit(s.post)
                    self._update_post(s.post, {
                        "status": "submitted",
                        "conversation_id": conversation_id,
                    })
                    submitted += 1
                except Exception as exc:
                    self._update_post(s.post, {"status": "error"})
                    log_task("analysis", run_id, "failed", f"Submit failed: {exc}")
            result.posts_submitted = submitted

            # STEP 8 — complete
            return self._finish(
                run_id, result, "completed", started,
                f"Fetched {result.posts_fetched}, scored {result.posts_scored}, "
                f"submitted {submitted}, filtered {filtered_count}, "
                f"duplicates {result.posts_duplicated}.",
            )

        except Exception as exc:
            # STEP 9 — top-level failure never crashes the server.
            log_task("analysis", run_id, "failed", f"Discovery run failed: {exc}")
            return self._finish(run_id, result, "failed", started, str(exc), error=str(exc))

    # ── helpers ──────────────────────────────────────

    def _create_run(self, trigger_type: str) -> str:
        row = (
            self.supabase.table("discovery_runs")
            .insert({"trigger_type": trigger_type, "status": "running"})
            .execute()
        ).data[0]
        return row["id"]

    def _update_run(self, run_id: str, fields: dict) -> None:
        try:
            self.supabase.table("discovery_runs").update(fields).eq("id", run_id).execute()
        except Exception:
            pass

    def _finish(self, run_id, result, status, started, message, error=None) -> DiscoveryRunResult:
        duration = round(time.monotonic() - started, 2)
        result.status = status
        result.message = message
        self._update_run(run_id, {
            "status": status,
            "completed_at": _now().isoformat(),
            "duration_seconds": duration,
            "platforms_checked": result.platforms_checked,
            "posts_fetched": result.posts_fetched,
            "posts_scored": result.posts_scored,
            "posts_submitted": result.posts_submitted,
            "posts_filtered": result.posts_filtered,
            "posts_duplicated": result.posts_duplicated,
            # Persist a human-readable outcome for every run (e.g. "Daily limit
            # reached", "No connected platforms", or the success summary) so the
            # run history explains why a run did what it did.
            "error_message": error or message,
        })
        log_task("analysis", run_id, status if status != "completed" else "completed", message)
        return result

    def _update_post(self, post: UniversalPost, fields: dict) -> None:
        try:
            self.supabase.table("discovered_posts").update(fields).eq(
                "platform", post.platform
            ).eq("post_id", post.post_id).execute()
        except Exception:
            pass

    def _insert_individually(self, posts: list[UniversalPost], run_id: str) -> list[UniversalPost]:
        kept: list[UniversalPost] = []
        for p in posts:
            try:
                self.supabase.table("discovered_posts").insert(_post_row(p, run_id)).execute()
                kept.append(p)
            except Exception:
                # Treat as duplicate (unique constraint) — skip.
                pass
        return kept

    def _touch_communities(self, communities: list[dict], grouped: dict, total_posts: int) -> None:
        now_iso = _now().isoformat()
        for c in communities:
            if c["platform"] not in grouped:
                continue
            try:
                self.supabase.table("monitored_communities").update({
                    "last_fetched_at": now_iso,
                    "fetch_count": (c.get("fetch_count") or 0) + 1,
                }).eq("id", c["id"]).execute()
            except Exception:
                pass


def _parse(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return _now() - timedelta(hours=24)
