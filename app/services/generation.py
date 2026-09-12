"""Module 7, Stage 4 — draft generation.

Generates 4 style drafts in parallel with LangChain RunnableParallel,
parses content + metadata, and stores them in response_drafts.
"""

import json

from langchain_core.runnables import RunnableLambda, RunnableParallel

from app.config import get_llm, settings
from app.database import get_supabase
from app.models.conversations import AnalysisResult
from app.prompts.generation import COMPOSE_PROMPT, GENERATION_PROMPT, STYLE_INSTRUCTIONS
from app.services.retrieval import (
    RetrievalResult,
    RetrievalService,
    call_llm_with_retry,
    extract_json,
)

METADATA_DELIMITER = "---METADATA---"

# Hard character limits per platform for a single post/reply. Drafts are asked to
# stay safely under these so posting doesn't get rejected.
PLATFORM_CHAR_LIMITS = {"bluesky": 300, "mastodon": 500}


def _length_instruction(platform: str) -> str:
    limit = PLATFORM_CHAR_LIMITS.get(platform)
    if limit:
        # Aim ~20 chars under the hard limit for safety.
        return (
            f"CRITICAL: Keep the entire response under {limit - 20} characters "
            f"({platform} has a hard {limit}-character limit). Be concise and complete — "
            f"do not exceed this."
        )
    return f"Length: between {settings.MIN_DRAFT_WORDS} and {settings.MAX_DRAFT_WORDS} words."


def _parse_draft(raw: str) -> tuple[str, dict]:
    """Split a draft response into content and its trailing metadata JSON."""
    if METADATA_DELIMITER in raw:
        content, meta_raw = raw.split(METADATA_DELIMITER, 1)
        try:
            meta = extract_json(meta_raw)
        except Exception:
            meta = {}
    else:
        content, meta = raw, {}
    return content.strip(), meta if isinstance(meta, dict) else {}


async def _generate_one(
    style: str, conversation_text: str, analysis_json: str, context_block: str, platform: str
) -> dict:
    llm = get_llm(temperature=0.7)
    prompt = GENERATION_PROMPT.format(
        conversation=conversation_text,
        analysis=analysis_json,
        context_block=context_block,
        style_instruction=STYLE_INSTRUCTIONS[style],
        length_instruction=_length_instruction(platform),
    )
    raw = await call_llm_with_retry(llm, prompt)
    content, meta = _parse_draft(raw)
    # Safety net: hard-trim to the platform limit at a word boundary if the model
    # still overshoots, so an approved draft can always be posted.
    limit = PLATFORM_CHAR_LIMITS.get(platform)
    if limit and len(content) > limit:
        content = _trim_to(content, limit)
    return {"style": style, "content": content, "meta": meta}


def _trim_to(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"


def _compose_length_instruction(char_limit: int | None) -> str:
    if char_limit:
        return (
            f"CRITICAL: Keep the entire post under {char_limit - 20} characters "
            f"(the target platform has a hard {char_limit}-character limit). Be concise "
            f"and complete — do not exceed this."
        )
    return f"Length: between {settings.MIN_DRAFT_WORDS} and {settings.MAX_DRAFT_WORDS} words."


async def _generate_one_compose(
    style: str, seed: dict, context_block: str, char_limit: int | None
) -> dict:
    llm = get_llm(temperature=0.7)
    prompt = COMPOSE_PROMPT.format(
        thinking=seed.get("thinking", "") or "(not specified)",
        example=seed.get("example", "") or "(not specified)",
        tension=seed.get("tension", "") or "(not specified)",
        invite=seed.get("invite", "") or "(not specified)",
        context_block=context_block,
        style_instruction=STYLE_INSTRUCTIONS[style],
        length_instruction=_compose_length_instruction(char_limit),
    )
    raw = await call_llm_with_retry(llm, prompt)
    content, meta = _parse_draft(raw)
    if char_limit and len(content) > char_limit:
        content = _trim_to(content, char_limit)
    return {"style": style, "content": content, "meta": meta}


async def generate_compose_candidates(seed: dict, char_limit: int | None = None) -> list[dict]:
    """Generate four original-post candidates (one per style lens) from the
    author's seed thoughts, grounded in the knowledge base. When char_limit is
    given (the strictest selected platform), candidates are written to fit it.
    Ephemeral — returned to the composer to pick, edit, and post; not stored."""
    seed_text = "\n".join(
        v for v in [
            seed.get("thinking"), seed.get("example"),
            seed.get("tension"), seed.get("invite"),
        ] if v
    ).strip()

    context_block = "(No relevant source material found.)"
    if seed_text:
        try:
            retrieval = await RetrievalService().retrieve(seed_text)
            context_block = retrieval.context_block
        except Exception:
            pass

    def make_branch(style: str):
        async def branch(_):
            return await _generate_one_compose(style, seed, context_block, char_limit)

        return RunnableLambda(branch)

    parallel = RunnableParallel({style: make_branch(style) for style in STYLE_INSTRUCTIONS})
    results = await parallel.ainvoke({})

    return [
        {
            "style": style,
            "content": result["content"],
            "value_explanation": (result["meta"] or {}).get("value_explanation"),
        }
        for style, result in results.items()
    ]


async def generate_drafts(
    conversation_id: str,
    conversation_text: str,
    analysis: AnalysisResult,
    retrieval: RetrievalResult,
    platform: str = "",
) -> None:
    analysis_json = json.dumps(analysis.model_dump(), indent=2)

    def make_branch(style: str):
        async def branch(_):
            return await _generate_one(
                style, conversation_text, analysis_json, retrieval.context_block, platform
            )

        return RunnableLambda(branch)

    parallel = RunnableParallel(
        {style: make_branch(style) for style in STYLE_INSTRUCTIONS}
    )
    results = await parallel.ainvoke({})

    source_chunk_ids = [c.chunk_id for c in retrieval.source_chunks]
    source_titles = list({c.document_title for c in retrieval.source_chunks})

    rows = []
    for style, result in results.items():
        meta = result["meta"]
        rows.append(
            {
                "conversation_id": conversation_id,
                "style": style,
                "content": result["content"],
                "value_explanation": meta.get("value_explanation"),
                "source_chunk_ids": source_chunk_ids,
                "source_document_titles": meta.get("source_documents_used") or source_titles,
                "include_link": bool(meta.get("include_link", False)),
                "suggested_link": meta.get("suggested_link"),
                "status": "pending",
            }
        )

    supabase = get_supabase()
    # Regenerating replaces the previous suggestions rather than stacking on top:
    # clear only the still-pending drafts, preserving any already approved/posted/saved.
    supabase.table("response_drafts").delete().eq(
        "conversation_id", conversation_id
    ).eq("status", "pending").execute()
    supabase.table("response_drafts").insert(rows).execute()
