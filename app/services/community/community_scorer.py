"""AI relevance scoring for discovered communities."""

from __future__ import annotations

import asyncio

from app.config import get_llm
from app.database import log_task
from app.services.community import DiscoveredCommunity, ScoredCommunity
from app.services.retrieval import call_llm_with_retry, extract_json

BATCH_SIZE = 15
BATCH_TIMEOUT_SECONDS = 120

SCORING_PROMPT = """You are helping the following author find online communities where they \
can make genuinely valuable contributions to discussions.

AUTHOR PROFILE:
{profile}

The author's topics of interest: {topics}

Score each community below from 0.00 to 1.00 on four criteria, then return the weighted average \
as final_score:
- topic_relevance (weight 0.40): how closely this community discusses the author's areas of \
focus described in the profile above.
- audience_fit (weight 0.30): how well its audience matches the author's readers and the people \
they want to reach.
- discussion_quality (weight 0.20): based on the description and activity level, whether it \
appears to have substantive, thoughtful discussions.
- contribution_opportunity (weight 0.10): whether an expert voice would be welcomed and valued.

final_score = topic_relevance*0.40 + audience_fit*0.30 + discussion_quality*0.20 + contribution_opportunity*0.10

Also suggest 2 to 5 specific keywords to monitor in this community based on its focus.

COMMUNITIES:
{communities}

Return ONLY valid JSON, no other text:
{{
  "scores": [
    {{
      "community_id": "platform:community_id",
      "final_score": 0.0,
      "topic_relevance": 0.0,
      "audience_fit": 0.0,
      "discussion_quality": 0.0,
      "contribution_opportunity": 0.0,
      "reasoning": "one sentence",
      "suggested_keywords": ["keyword1", "keyword2"]
    }}
  ]
}}"""

RETRY_SUFFIX = "\n\nReturn ONLY the JSON object. No prose, no markdown fences."


def _key(c: DiscoveredCommunity) -> str:
    return f"{c.platform}:{c.community_id}"


def _format(c: DiscoveredCommunity) -> str:
    return (
        f"- community_id: {_key(c)}\n"
        f"  platform: {c.platform}\n"
        f"  name: {c.community_name}\n"
        f"  description: {(c.description or '-')[:200]}\n"
        f"  member_count: {c.member_count if c.member_count is not None else '-'}\n"
        f"  activity_level: {c.activity_level}"
    )


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


class CommunityScorer:
    def __init__(self):
        self.llm = get_llm(temperature=0)

    async def score_batch(
        self, communities: list[DiscoveredCommunity], topics: list[str]
    ) -> list[ScoredCommunity]:
        results: list[ScoredCommunity] = []
        for i in range(0, len(communities), BATCH_SIZE):
            results.extend(await self._score_one(communities[i : i + BATCH_SIZE], topics))
        return results

    async def _score_one(
        self, batch: list[DiscoveredCommunity], topics: list[str]
    ) -> list[ScoredCommunity]:
        if not batch:
            return []
        from app.services.author_profile import get_author_profile

        profile = await get_author_profile()
        prompt = SCORING_PROMPT.format(
            profile=profile,
            topics=", ".join(topics) or "coaching, leadership, personal growth",
            communities="\n".join(_format(c) for c in batch),
        )
        data = None
        try:
            async with asyncio.timeout(BATCH_TIMEOUT_SECONDS):
                raw = await call_llm_with_retry(self.llm, prompt)
                try:
                    data = extract_json(raw)
                except Exception:
                    raw = await call_llm_with_retry(self.llm, prompt + RETRY_SUFFIX)
                    data = extract_json(raw)
        except Exception as exc:
            log_task("analysis", None, "failed", f"Community scoring failed: {exc}")
            return [ScoredCommunity(community=c, reasoning="Scoring failed — defaulted to 0.") for c in batch]

        by_key = {str(s.get("community_id")): s for s in (data or {}).get("scores", [])}
        out: list[ScoredCommunity] = []
        for c in batch:
            s = by_key.get(_key(c)) or {}
            kws = s.get("suggested_keywords") or []
            out.append(
                ScoredCommunity(
                    community=c,
                    final_score=_clamp(s.get("final_score")),
                    topic_relevance=_clamp(s.get("topic_relevance")),
                    audience_fit=_clamp(s.get("audience_fit")),
                    discussion_quality=_clamp(s.get("discussion_quality")),
                    contribution_opportunity=_clamp(s.get("contribution_opportunity")),
                    reasoning=str(s.get("reasoning", ""))[:1000],
                    suggested_keywords=[str(k) for k in kws][:5],
                )
            )
        return out
