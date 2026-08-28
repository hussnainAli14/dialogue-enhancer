"""Module 3 — community discovery orchestrator."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import settings as env_settings
from app.database import get_supabase, log_task
from app.schemas.connections import PLATFORMS
from app.services import token_store
from app.services.community import DiscoveredCommunity
from app.services.community.community_scorer import CommunityScorer
from app.services.community.keyword_searcher import KeywordSearcher
from app.services.community.people_tracker import PeopleTracker


@dataclass
class CommunityDiscoveryResult:
    run_id: str
    status: str
    communities_found: int = 0
    communities_new: int = 0
    communities_already_known: int = 0
    message: str = ""
    platforms_searched: list[str] = field(default_factory=list)


def _now():
    return datetime.now(timezone.utc)


def _community_settings() -> dict:
    """Read community-discovery settings from discovery_settings, env fallback."""
    defaults = {
        "max_communities_per_platform": env_settings.MAX_COMMUNITIES_PER_PLATFORM,
        "min_community_relevance_score": env_settings.MIN_COMMUNITY_RELEVANCE_SCORE,
        "max_community_suggestions": env_settings.MAX_SUGGESTIONS_PER_RUN,
        "community_discovery_enabled": env_settings.COMMUNITY_DISCOVERY_ENABLED,
    }
    try:
        rows = get_supabase().table("discovery_settings").select("*").limit(1).execute().data
        if rows:
            r = rows[0]
            for k in list(defaults):
                if r.get(k) is not None:
                    defaults[k] = r[k]
    except Exception:
        pass
    return defaults


class CommunityDiscoveryWorker:
    def __init__(self):
        self.supabase = get_supabase()
        self.searcher = KeywordSearcher()
        self.tracker = PeopleTracker()
        self.scorer = CommunityScorer()

    async def run(
        self,
        trigger_type: str = "scheduled",
        modes: list[str] | None = None,
        platforms: list[str] | None = None,
        run_id: str | None = None,
    ) -> CommunityDiscoveryResult:
        modes = modes or ["keyword", "people_based"]
        started = time.monotonic()
        run_id = run_id or self._create_run(trigger_type, modes)
        result = CommunityDiscoveryResult(run_id=run_id, status="running")
        try:
            cfg = _community_settings()

            # STEP 1 — load topics + people
            topics = (
                self.supabase.table("discovery_topics").select("*").eq("is_active", True).execute()
            ).data or []
            people = (
                self.supabase.table("monitored_people").select("*").eq("is_active", True).execute()
            ).data or []
            if not topics and not people:
                return self._finish(run_id, result, started, "completed",
                                    "No topics or people configured. Add some to discover communities.")

            connected = {
                c.platform for c in token_store.get_all_connections() if c.status == "connected"
            }
            if platforms:
                connected &= set(platforms)
            connected = {p for p in connected if p in PLATFORMS}
            result.platforms_searched = sorted(connected)
            if not connected:
                return self._finish(run_id, result, started, "completed",
                                    "No connected platforms to search.")

            found: dict[tuple[str, str], DiscoveredCommunity] = {}

            # STEP 2 — keyword discovery
            if "keyword" in modes and topics:
                for platform in connected:
                    try:
                        items = await self.searcher.search_platform(
                            platform, topics, cfg["max_communities_per_platform"]
                        )
                    except Exception as exc:
                        log_task("analysis", run_id, "failed", f"Keyword search {platform}: {exc}")
                        items = []
                    for c in items:
                        self._merge(found, c)

            # STEP 3 — people-based discovery
            if "people_based" in modes and people:
                try:
                    items = await self.tracker.discover(people, connected)
                except Exception as exc:
                    log_task("analysis", run_id, "failed", f"People discovery: {exc}")
                    items = []
                for c in items:
                    self._merge(found, c)

            result.communities_found = len(found)

            # STEP 4 — remove already-known / already-processed
            known = self._known_keys()
            new_items = [c for k, c in found.items() if k not in known]
            result.communities_already_known = len(found) - len(new_items)

            # STEP 5 — score, filter, rank, cap
            scored = await self.scorer.score_batch(
                new_items, [t["topic"] for t in topics]
            ) if new_items else []
            passing = [s for s in scored if s.final_score >= cfg["min_community_relevance_score"]]
            passing.sort(key=lambda s: s.final_score, reverse=True)
            passing = passing[: cfg["max_community_suggestions"]]

            # STEP 6 — upsert suggestions
            self._save_suggestions(passing, run_id)
            result.communities_new = len(passing)

            # STEP 7 — complete
            return self._finish(
                run_id, result, started, "completed",
                f"Found {result.communities_found} communities, "
                f"{result.communities_new} new suggestions awaiting review "
                f"({result.communities_already_known} already known).",
            )
        except Exception as exc:
            log_task("analysis", run_id, "failed", f"Community discovery failed: {exc}")
            return self._finish(run_id, result, started, "failed", str(exc), error=str(exc))

    # ── helpers ──────────────────────────────────────

    @staticmethod
    def _merge(bucket: dict, c: DiscoveredCommunity) -> None:
        key = (c.platform, c.community_id)
        existing = bucket.get(key)
        if not existing:
            bucket[key] = c
            return
        existing.discovered_via_keywords = sorted(
            set(existing.discovered_via_keywords) | set(c.discovered_via_keywords)
        )
        existing.discovered_via_people = sorted(
            set(existing.discovered_via_people) | set(c.discovered_via_people)
        )
        methods = {existing.discovery_method, c.discovery_method}
        existing.discovery_method = "both" if methods >= {"keyword", "people_based"} else existing.discovery_method

    def _known_keys(self) -> set[tuple[str, str]]:
        known: set[tuple[str, str]] = set()
        try:
            for r in (self.supabase.table("monitored_communities").select("platform, community_id").execute().data or []):
                known.add((r["platform"], r["community_id"]))
            for r in (
                self.supabase.table("community_suggestions")
                .select("platform, community_id, status")
                .in_("status", ["approved", "rejected", "already_monitoring"])
                .execute()
            ).data or []:
                known.add((r["platform"], r["community_id"]))
        except Exception:
            pass
        return known

    def _save_suggestions(self, scored, run_id: str) -> None:
        rows = []
        for s in scored:
            c = s.community
            method = c.discovery_method
            if c.discovered_via_keywords and c.discovered_via_people:
                method = "both"
            rows.append(
                {
                    "platform": c.platform,
                    "community_id": c.community_id,
                    "community_name": c.community_name,
                    "community_url": c.community_url,
                    "description": c.description,
                    "member_count": c.member_count,
                    "activity_level": c.activity_level,
                    "discovery_method": method,
                    "discovered_via_keywords": c.discovered_via_keywords,
                    "discovered_via_people": c.discovered_via_people,
                    "relevance_score": s.final_score,
                    "relevance_reasoning": s.reasoning,
                    "suggested_keywords": s.suggested_keywords,
                    "status": "pending",
                    "discovery_run_id": run_id,
                }
            )
        if rows:
            try:
                self.supabase.table("community_suggestions").upsert(
                    rows, on_conflict="platform,community_id"
                ).execute()
            except Exception as exc:
                log_task("analysis", run_id, "failed", f"Save suggestions: {exc}")

    def _create_run(self, trigger_type: str, modes: list[str]) -> str:
        row = (
            self.supabase.table("community_discovery_runs")
            .insert({"trigger_type": trigger_type, "discovery_modes": modes, "status": "running"})
            .execute()
        ).data[0]
        return row["id"]

    def _finish(self, run_id, result, started, status, message, error=None) -> CommunityDiscoveryResult:
        result.status = status
        result.message = message
        try:
            self.supabase.table("community_discovery_runs").update(
                {
                    "status": status,
                    "platforms_searched": result.platforms_searched,
                    "communities_found": result.communities_found,
                    "communities_new": result.communities_new,
                    "communities_already_known": result.communities_already_known,
                    "completed_at": _now().isoformat(),
                    "duration_seconds": round(time.monotonic() - started, 2),
                    "error_message": error or message,
                }
            ).eq("id", run_id).execute()
        except Exception:
            pass
        log_task("analysis", run_id, status if status != "completed" else "completed", message)
        return result
