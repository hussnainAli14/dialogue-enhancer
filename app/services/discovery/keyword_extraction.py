"""Extract discovery keywords/themes from knowledge base documents.

Runs after a document finishes ingesting. The extracted keywords feed the
discovery search (Stage 1). Existing keywords are never overwritten, so a user's
manual edits and deactivations survive a re-scan.
"""

from __future__ import annotations

from app.config import get_llm
from app.database import get_supabase, log_task
from app.services.retrieval import call_llm_with_retry, extract_json

MAX_KEYWORDS_PER_DOC = 8
MAX_KEYWORD_LEN = 60

EXTRACTION_PROMPT = """From the author's writing below, extract up to {n} short search \
keywords or topic phrases (1-3 words each) that best capture what this author writes about. \
These are used to search social media for conversations worth joining.

Rules:
- Specific, distinctive themes — not generic filler ("inner work" yes; "people", "things", \
"the" no).
- Lowercase. 1-3 words each. No hashtags, no punctuation, no duplicates.
- Prefer the author's actual subject matter over broad umbrella words.

AUTHOR'S WRITING:
{samples}

Return ONLY a JSON array of strings, e.g. ["shadow work", "servant leadership"]."""


def _normalize(kw: str) -> str:
    return " ".join(kw.lower().strip().split())


async def extract_keywords_for_document(document_id: str, text: str | None = None) -> list[str]:
    """Extract and store keywords for one document. Returns the normalized
    keywords newly stored. Never raises."""
    supabase = get_supabase()

    samples = (text or "")[:6000]
    if not samples.strip():
        try:
            chunks = (
                supabase.table("document_chunks")
                .select("content")
                .eq("document_id", document_id)
                .limit(15)
                .execute()
            ).data or []
            samples = "\n\n".join((c.get("content") or "")[:400] for c in chunks)[:6000]
        except Exception:
            samples = ""
    if not samples.strip():
        return []

    try:
        llm = get_llm(temperature=0.2)
        raw = await call_llm_with_retry(
            llm, EXTRACTION_PROMPT.format(n=MAX_KEYWORDS_PER_DOC, samples=samples)
        )
        data = extract_json(raw)
        candidates = [k for k in data if isinstance(k, str)] if isinstance(data, list) else []
    except Exception as exc:
        log_task("ingestion", document_id, "failed", f"Keyword extraction failed: {exc}")
        return []

    # Skip keywords that already exist (any source) so manual edits/removals and
    # prior activations are preserved.
    try:
        existing = {
            r["normalized"]
            for r in (supabase.table("discovery_keywords").select("normalized").execute().data or [])
        }
    except Exception:
        existing = set()

    saved: list[str] = []
    for kw in candidates:
        norm = _normalize(kw)
        if not norm or len(norm) > MAX_KEYWORD_LEN or norm in existing:
            continue
        try:
            supabase.table("discovery_keywords").insert(
                {
                    "keyword": kw.strip(),
                    "normalized": norm,
                    "source": "kb",
                    "document_id": document_id,
                    "is_active": True,
                }
            ).execute()
            existing.add(norm)
            saved.append(norm)
        except Exception:
            continue

    if saved:
        log_task("ingestion", document_id, "completed", f"Extracted {len(saved)} keywords.")
    return saved


CURATE_TARGET = 30
CURATION_PROMPT = """You are choosing the best social-media search keywords for an author \
from a large list of candidates extracted from their writing.

Pick the {n} MOST useful and distinctive keywords for finding relevant online conversations:
- Favour specific, substantive topics over generic words.
- Drop near-duplicates and vague filler.

CANDIDATES:
{keywords}

Return ONLY a JSON array of the chosen keywords, copied exactly from the list."""


async def curate_keywords(target: int | None = None) -> int:
    """Activate the best ~`target` keywords and deactivate the rest, so discovery
    searches a strong, capped set. Manual keywords are always kept active; an AI
    picks the best of the knowledge-base keywords to fill the remaining slots.
    `target` defaults to the configured keyword_search_cap. Never raises."""
    if target is None:
        from app.services.discovery import store

        target = store.get_settings().keyword_search_cap
    supabase = get_supabase()
    try:
        rows = (
            supabase.table("discovery_keywords")
            .select("id, keyword, normalized, source")
            .execute()
        ).data or []
    except Exception:
        return 0
    if not rows:
        return 0

    manual = [r for r in rows if r.get("source") == "manual"]
    kb = [r for r in rows if r.get("source") != "manual"]
    slots = max(0, target - len(manual))

    chosen_kb: set[str] = set()
    if len(kb) <= slots:
        chosen_kb = {r["id"] for r in kb}
    elif slots > 0:
        listing = "\n".join(f"- {r['keyword']}" for r in kb[:400])
        try:
            llm = get_llm(temperature=0)
            raw = await call_llm_with_retry(
                llm, CURATION_PROMPT.format(n=slots, keywords=listing)
            )
            picks = extract_json(raw)
            pick_norms = {_normalize(p) for p in picks if isinstance(p, str)}
            for r in kb:
                if r["normalized"] in pick_norms:
                    chosen_kb.add(r["id"])
        except Exception as exc:
            log_task("analysis", None, "failed", f"Keyword curation failed: {exc}")
        # Top up (or fully fall back) by order if the model under-picked.
        if len(chosen_kb) < slots:
            for r in kb:
                if r["id"] not in chosen_kb:
                    chosen_kb.add(r["id"])
                    if len(chosen_kb) >= slots:
                        break

    active_ids = {r["id"] for r in manual} | chosen_kb
    inactive_ids = [r["id"] for r in rows if r["id"] not in active_ids]

    try:
        if active_ids:
            supabase.table("discovery_keywords").update({"is_active": True}).in_(
                "id", list(active_ids)
            ).execute()
        if inactive_ids:
            supabase.table("discovery_keywords").update({"is_active": False}).in_(
                "id", inactive_ids
            ).execute()
    except Exception as exc:
        log_task("analysis", None, "failed", f"Keyword curation apply failed: {exc}")

    return len(active_ids)


async def rescan_all_documents() -> int:
    """Re-run extraction across every ready document. Returns the number of new
    keywords stored. Used by the manual 'Rescan knowledge base' action."""
    supabase = get_supabase()
    try:
        docs = (
            supabase.table("documents").select("id, status").eq("status", "ready").execute()
        ).data or []
    except Exception:
        return 0
    total = 0
    for d in docs:
        total += len(await extract_keywords_for_document(d["id"]))
    # Pick the best set to keep active once all keywords are in.
    await curate_keywords()
    return total
