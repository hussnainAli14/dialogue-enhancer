"""Turn the author's feedback into compact, bounded guidance the AI can act on.

The Feedback History only recorded actions; this closes the loop by distilling
them into small fixed-size blocks injected into the generation and scoring
prompts. The blocks are hard-capped by example count and characters, so the
injected context stays CONSTANT no matter how much feedback accumulates — the
database grows, the prompt does not. Results are cached and only recomputed when
feedback changes (same pattern as author_profile).

Phase 2 (not here): embed feedback in pgvector and retrieve the few most
relevant examples per draft, for learning from unlimited history.
"""

from __future__ import annotations

from collections import Counter

from app.database import get_supabase

# Hard caps — keep injected tokens flat regardless of history size.
_MAX_EMULATE = 3
_MAX_EDITS = 3
_MAX_REJECT_REASONS = 5
_SNIPPET_CHARS = 220
_DRAFT_BLOCK_CHARS = 1500
_MAX_DISMISS_TOPICS = 12
_DISCOVERY_BLOCK_CHARS = 600

_cache: dict = {"draft_sig": None, "draft_block": None, "disc_sig": None, "disc_block": None}


def _truncate(text: str, n: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _draft_signature() -> str:
    """Cheap change signal: feedback_log row count + latest timestamp."""
    try:
        rows = (
            get_supabase()
            .table("feedback_log")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        cnt = (
            get_supabase().table("feedback_log").select("id", count="exact").execute().count or 0
        )
        latest = rows[0]["created_at"] if rows else ""
        return f"{cnt}:{latest}"
    except Exception:
        return ""


def draft_preferences() -> str:
    """A bounded block describing the author's demonstrated draft preferences:
    approved voice to emulate, their edits to apply, and rejection patterns to
    avoid. Empty string when there is no usable feedback yet."""
    sig = _draft_signature()
    if sig and _cache["draft_sig"] == sig and _cache["draft_block"] is not None:
        return _cache["draft_block"]

    supabase = get_supabase()
    try:
        logs = (
            supabase.table("feedback_log")
            .select("action, original_content, final_content, edit_diff, rejection_reason, created_at")
            .order("created_at", desc=True)
            .limit(400)
            .execute()
        ).data or []
    except Exception:
        return ""

    emulate: list[str] = []
    edits: list[str] = []
    reject_reasons: list[str] = []
    for r in logs:
        action = r.get("action")
        if action in ("approved", "posted") and len(emulate) < _MAX_EMULATE:
            text = r.get("final_content") or r.get("original_content")
            if text:
                emulate.append(_truncate(text, _SNIPPET_CHARS))
        elif action == "edited" and len(edits) < _MAX_EDITS:
            if r.get("edit_diff"):
                edits.append(_truncate(r["edit_diff"], _SNIPPET_CHARS))
        elif action == "rejected" and r.get("rejection_reason"):
            reject_reasons.append(r["rejection_reason"].strip())

    top_rejects = [reason for reason, _ in Counter(reject_reasons).most_common(_MAX_REJECT_REASONS)]

    if not emulate and not edits and not top_rejects:
        _cache.update({"draft_sig": sig, "draft_block": ""})
        return ""

    parts = [
        "LEARNED FROM THE AUTHOR'S FEEDBACK (match these preferences):",
    ]
    if emulate:
        parts.append("Responses the author APPROVED (emulate this voice and shape):")
        parts += [f"- {e}" for e in emulate]
    if edits:
        parts.append("Edits the author made (apply these kinds of changes):")
        parts += [f"- {e}" for e in edits]
    if top_rejects:
        parts.append("Patterns the author REJECTS (avoid these):")
        parts += [f"- {r}" for r in top_rejects]

    block = "\n".join(parts)
    if len(block) > _DRAFT_BLOCK_CHARS:
        block = block[: _DRAFT_BLOCK_CHARS - 1].rstrip() + "…"
    _cache.update({"draft_sig": sig, "draft_block": block})
    return block


def _discovery_signature() -> str:
    try:
        cnt = (
            get_supabase()
            .table("conversations")
            .select("id", count="exact")
            .eq("analysis_status", "dismissed")
            .execute()
        ).count or 0
        return str(cnt)
    except Exception:
        return ""


def discovery_preferences() -> str:
    """A bounded note on the topics the author repeatedly dismisses, so the
    scorer can down-rank similar posts. Empty string when nothing dismissed."""
    sig = _discovery_signature()
    if sig and _cache["disc_sig"] == sig and _cache["disc_block"] is not None:
        return _cache["disc_block"]

    supabase = get_supabase()
    try:
        dismissed = (
            supabase.table("conversations")
            .select("id")
            .eq("analysis_status", "dismissed")
            .limit(200)
            .execute()
        ).data or []
        ids = [d["id"] for d in dismissed]
        topics: list[str] = []
        if ids:
            for a in (
                supabase.table("conversation_analysis")
                .select("conversation_id, central_topic")
                .in_("conversation_id", ids)
                .execute()
            ).data or []:
                t = (a.get("central_topic") or "").strip()
                if t:
                    topics.append(t)
    except Exception:
        return ""

    if not topics:
        _cache.update({"disc_sig": sig, "disc_block": ""})
        return ""

    top = [t for t, _ in Counter(topics).most_common(_MAX_DISMISS_TOPICS)]
    block = (
        "AUTHOR'S DISMISSAL PATTERNS — the author has repeatedly dismissed posts on "
        "these topics; score posts that closely resemble them LOWER on "
        "topic_relevance and contribution_opportunity:\n- " + "\n- ".join(top)
    )
    if len(block) > _DISCOVERY_BLOCK_CHARS:
        block = block[: _DISCOVERY_BLOCK_CHARS - 1].rstrip() + "…"
    _cache.update({"disc_sig": sig, "disc_block": block})
    return block
