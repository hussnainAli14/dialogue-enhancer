"""AI relevance scorer — rates discovered posts for the author to respond to."""

from __future__ import annotations

import asyncio

from app.config import get_llm
from app.database import log_task
from app.models.discovery import DiscoverySettings, ScoredPost
from app.services.connections.base import UniversalPost
from app.services.retrieval import call_llm_with_retry, extract_json

SCORING_PROMPT = """You are helping the following author decide which online conversations \
are worth their time.

AUTHOR PROFILE:
{profile}

The author only wants to join conversations where they can make a GENUINELY VALUABLE \
contribution — not just any conversation that mentions their topics.

Score each post from 0.0 to 1.0 on four criteria, then return the weighted average as \
final_score:

- topic_relevance (weight 0.35): how closely the post relates to the author's areas of \
focus described in the profile above. 0 = off-topic, 1 = directly on topic.
- contribution_opportunity (weight 0.35): how much genuine value the author could add. \
0 = saturated / needs no input, 1 = a clear gap the author could fill.
- discussion_quality (weight 0.20): how thoughtful and substantive it is. 0 = superficial, \
promotional, or toxic, 1 = a genuine deep discussion.
- audience_fit (weight 0.10): how well the audience matches the author's readership. \
0 = clearly wrong audience, 1 = perfect fit.

final_score = topic_relevance*0.35 + contribution_opportunity*0.35 + discussion_quality*0.20 + audience_fit*0.10

POSTS:
{posts}

Return ONLY valid JSON, no other text:
{{
  "scores": [
    {{
      "post_id": "platform:post_id",
      "final_score": 0.0,
      "topic_relevance": 0.0,
      "contribution_opportunity": 0.0,
      "discussion_quality": 0.0,
      "audience_fit": 0.0,
      "reasoning": "one sentence"
    }}
  ]
}}"""

RETRY_SUFFIX = "\n\nReturn ONLY the JSON object. No prose, no markdown fences."

# Weight of knowledge-base overlap when blended into the final relevance score.
KB_OVERLAP_WEIGHT = 0.25

# Hard ceiling per batch so a slow/hung local LLM can never stall the worker.
BATCH_TIMEOUT_SECONDS = 120


def _key(post: UniversalPost) -> str:
    return f"{post.platform}:{post.post_id}"


def _format_post(post: UniversalPost) -> str:
    return (
        f"- post_id: {_key(post)}\n"
        f"  platform: {post.platform}\n"
        f"  community: {post.community_name or '-'}\n"
        f"  author: {post.author_name}\n"
        f"  title: {post.title or '-'}\n"
        f"  content: {(post.content or '')[:300]}"
    )


class Scorer:
    def __init__(self):
        self.llm = get_llm(temperature=0)

    async def score_batch(
        self, posts: list[UniversalPost], settings: DiscoverySettings
    ) -> list[ScoredPost]:
        results: list[ScoredPost] = []
        size = max(1, settings.scoring_batch_size)
        weight = getattr(settings, "kb_overlap_weight", KB_OVERLAP_WEIGHT)
        for i in range(0, len(posts), size):
            batch = posts[i : i + size]
            results.extend(await self.score_single_batch(batch, kb_weight=weight))
        return results

    async def score_single_batch(
        self, posts: list[UniversalPost], kb_weight: float = KB_OVERLAP_WEIGHT
    ) -> list[ScoredPost]:
        if not posts:
            return []
        from app.services.author_profile import get_author_profile

        profile = await get_author_profile()
        prompt = SCORING_PROMPT.format(
            profile=profile, posts="\n".join(_format_post(p) for p in posts)
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
            log_task("analysis", None, "failed", f"Scoring batch failed: {exc}")
            # Fallback: score everything 0 so the run continues.
            return [ScoredPost(post=p, reasoning="Scoring failed — defaulted to 0.") for p in posts]

        by_key = {}
        for s in (data or {}).get("scores", []):
            by_key[str(s.get("post_id"))] = s

        scored: list[ScoredPost] = []
        for p in posts:
            s = by_key.get(_key(p)) or {}
            scored.append(
                ScoredPost(
                    post=p,
                    final_score=_clamp(s.get("final_score")),
                    topic_relevance=_clamp(s.get("topic_relevance")),
                    contribution_opportunity=_clamp(s.get("contribution_opportunity")),
                    discussion_quality=_clamp(s.get("discussion_quality")),
                    audience_fit=_clamp(s.get("audience_fit")),
                    reasoning=str(s.get("reasoning", ""))[:1000],
                )
            )

        # Blend in how well each post overlaps the knowledge base — a boost for
        # topics the author has actually written about. Skipped entirely when the
        # knowledge base is empty, so it never penalises.
        overlaps = await self._kb_overlap(posts) if kb_weight > 0 else {}
        if overlaps:
            for sp in scored:
                ov = overlaps.get(_key(sp.post))
                if ov is None:
                    continue
                blended = sp.final_score * (1 - kb_weight) + ov * kb_weight
                sp.final_score = round(blended, 4)

        return scored

    async def _kb_overlap(self, posts: list[UniversalPost]) -> dict[str, float]:
        """Max cosine similarity of each post against the knowledge base, keyed by
        post. Returns {} when the knowledge base is empty (so no blending happens)."""
        from app.config import get_embeddings
        from app.database import get_supabase

        supabase = get_supabase()
        try:
            docs = supabase.table("documents").select("id", count="exact").limit(1).execute()
            if not (docs.count or 0):
                return {}
        except Exception:
            return {}

        out: dict[str, float] = {}
        try:
            embeddings = get_embeddings()
            texts = [f"{p.title or ''} {p.content or ''}".strip()[:1000] for p in posts]
            vectors = await embeddings.aembed_documents(texts)
        except Exception:
            return {}

        for p, vec in zip(posts, vectors):
            try:
                res = supabase.rpc(
                    "match_documents",
                    {"query_embedding": vec, "match_threshold": 0.0, "match_count": 1},
                ).execute()
                rows = res.data or []
                out[_key(p)] = float(rows[0]["similarity"]) if rows else 0.0
            except Exception:
                out[_key(p)] = 0.0
        return out

    async def score_single(self, post: UniversalPost) -> ScoredPost:
        results = await self.score_single_batch([post])
        return results[0]


def _clamp(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
