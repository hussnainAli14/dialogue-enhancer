"""Derive a short author profile from the knowledge base.

Used by relevance scoring so that which conversations are judged "worth the
author's time" reflects the author's own saved writing, instead of a hardcoded
description. Falls back to DEFAULT_PROFILE when the knowledge base is empty.
"""

from __future__ import annotations

from app.config import get_llm
from app.database import get_supabase, log_task

# Used when the knowledge base has no usable documents yet.
DEFAULT_PROFILE = (
    "A coach and author with fifteen years of experience in coaching, leadership, "
    "personal growth, spirituality, and community building. They write for an "
    "audience seeking practical, reflective guidance on growth and leadership."
)

PROFILE_PROMPT = """From the author's own writing below, write a SHORT third-person profile \
(2-4 sentences, no name) describing their expertise, the main topics they cover, their \
perspective, and who their audience is. This profile is used to judge which online \
conversations are worth the author's time.

AUTHOR'S WRITING (samples):
{samples}

Return ONLY the profile sentences, no headings or extra text."""

# Cheap in-process cache — the knowledge base changes rarely, and regenerating
# the profile on every scoring batch would waste an LLM call per run.
_cache: dict = {"signature": None, "profile": None}


def _signature(docs: list[dict]) -> str:
    """A change signal: profile is regenerated only when the doc set changes."""
    ids = sorted(str(d.get("id")) for d in docs)
    return f"{len(ids)}:{'|'.join(ids)}"


async def get_author_profile() -> str:
    """Return a short profile summarising the author from their knowledge base,
    or DEFAULT_PROFILE when no usable documents exist. Never raises."""
    supabase = get_supabase()
    try:
        docs = (
            supabase.table("documents")
            .select("id, title, source_type, status")
            .execute()
        ).data or []
    except Exception:
        return DEFAULT_PROFILE

    # Only summarise documents that finished indexing (status values vary across
    # the pipeline; treat missing/ready/completed/indexed as usable).
    ready = [d for d in docs if d.get("status") in (None, "ready", "completed", "indexed")]
    if not ready:
        return DEFAULT_PROFILE

    signature = _signature(ready)
    if _cache["signature"] == signature and _cache["profile"]:
        return _cache["profile"]

    try:
        chunks = (
            supabase.table("document_chunks").select("content").limit(30).execute()
        ).data or []
    except Exception:
        chunks = []

    samples = "\n\n".join((c.get("content") or "")[:400] for c in chunks[:20]).strip()
    if not samples:
        # No chunk text available — summarise from titles as a weak fallback.
        samples = "\n".join(
            f"- {d.get('title') or 'Untitled'} ({d.get('source_type') or 'other'})"
            for d in ready
        ).strip()
    if not samples:
        return DEFAULT_PROFILE

    try:
        llm = get_llm(temperature=0.2)
        result = await llm.ainvoke(PROFILE_PROMPT.format(samples=samples[:6000]))
        profile = (result.content or "").strip()
    except Exception as exc:
        log_task("analysis", None, "failed", f"Author profile generation failed: {exc}")
        return DEFAULT_PROFILE

    if not profile:
        return DEFAULT_PROFILE

    _cache["signature"] = signature
    _cache["profile"] = profile
    return profile
