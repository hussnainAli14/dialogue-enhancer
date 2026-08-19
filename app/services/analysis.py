"""Module 7, Stage 2 — conversation analysis, plus the full pipeline
orchestrator that runs as a background task."""

from app.config import get_llm
from app.database import get_supabase, log_task
from app.models.conversations import AnalysisResult
from app.prompts.analysis import ANALYSIS_PROMPT, ANALYSIS_RETRY_SUFFIX
from app.services.retrieval import RetrievalService, call_llm_with_retry, extract_json


async def analyse_conversation(conversation_text: str, context_block: str) -> AnalysisResult:
    """Run the analysis prompt and strictly parse the JSON result.
    One retry with an explicit JSON-only instruction if parsing fails."""
    llm = get_llm(temperature=0.3)
    prompt = ANALYSIS_PROMPT.format(conversation=conversation_text, context_block=context_block)

    raw = await call_llm_with_retry(llm, prompt)
    try:
        data = extract_json(raw)
    except Exception:
        raw = await call_llm_with_retry(llm, prompt + ANALYSIS_RETRY_SUFFIX)
        data = extract_json(raw)

    return AnalysisResult(**_coerce_analysis(data))


def _coerce_analysis(data: dict) -> dict:
    """Fill safe defaults for any fields a smaller local model omitted or
    mistyped, so a mostly-complete analysis still proceeds instead of failing
    validation. Errs conservative: unknown recommendation -> DO_NOT_COMMENT."""

    def as_list(v):
        if isinstance(v, list):
            return [str(x) for x in v]
        if v in (None, ""):
            return []
        return [str(v)]

    def as_str(v):
        return "" if v is None else str(v)

    rec = str(data.get("participation_recommendation", "")).upper()
    rec = "COMMENT" if rec == "COMMENT" else "DO_NOT_COMMENT"

    def as_score(v, default=None):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return default

    # Prefer a weighted average of the four sub-dimensions (more granular than
    # the single vibe number a small model tends to round to 0.8). Fall back to
    # the model's own relevance_score, then 0.0.
    topic = as_score(data.get("topic_relevance"))
    contrib = as_score(data.get("contribution_opportunity"))
    quality = as_score(data.get("discussion_quality"))
    audience = as_score(data.get("audience_fit"))
    subs = [topic, contrib, quality, audience]
    if all(s is not None for s in subs):
        score = round(topic * 0.35 + contrib * 0.35 + quality * 0.20 + audience * 0.10, 2)
    else:
        score = as_score(data.get("relevance_score"), 0.0)

    return {
        "central_topic": as_str(data.get("central_topic")) or "Unknown topic",
        "key_tensions": as_list(data.get("key_tensions")),
        "viewpoints_represented": as_list(data.get("viewpoints_represented")),
        "emotional_sensitivities": as_str(data.get("emotional_sensitivities")),
        "can_add_value": bool(data.get("can_add_value", rec == "COMMENT")),
        "value_reasoning": as_str(data.get("value_reasoning")),
        "participation_recommendation": rec,
        "recommendation_reason": as_str(data.get("recommendation_reason")),
        "relevance_score": score,
    }


async def run_pipeline(conversation_id: str) -> None:
    """Full pipeline: retrieval → analysis → skip check → draft generation.
    Triggered as a BackgroundTask from POST /conversations/submit."""
    from app.services.generation import generate_drafts

    supabase = get_supabase()
    try:
        conv = (
            supabase.table("conversations").select("*").eq("id", conversation_id).execute()
        ).data[0]
        conversation_text = conv.get("full_thread") or conv["original_post"]

        # STAGE 1 — retrieval
        retrieval = await RetrievalService().retrieve(conversation_text)

        # STAGE 2 — analysis
        analysis = await analyse_conversation(conversation_text, retrieval.context_block)
        supabase.table("conversation_analysis").insert(
            {
                "conversation_id": conversation_id,
                "central_topic": analysis.central_topic,
                "key_tensions": analysis.key_tensions,
                "viewpoints_represented": analysis.viewpoints_represented,
                "emotional_sensitivities": analysis.emotional_sensitivities,
                "can_add_value": analysis.can_add_value,
                "value_reasoning": analysis.value_reasoning,
                "participation_recommendation": analysis.participation_recommendation,
                "recommendation_reason": analysis.recommendation_reason,
                "relevance_score": analysis.relevance_score,
            }
        ).execute()
        supabase.table("conversations").update({"analysis_status": "analysed"}).eq(
            "id", conversation_id
        ).execute()

        # STAGE 3 — skip check
        if analysis.participation_recommendation == "DO_NOT_COMMENT":
            supabase.table("conversations").update({"analysis_status": "skipped"}).eq(
                "id", conversation_id
            ).execute()
            log_task(
                "analysis",
                conversation_id,
                "completed",
                f"Skipped — DO_NOT_COMMENT: {analysis.recommendation_reason}",
            )
            return

        # STAGE 4 — draft generation (platform-aware length)
        await generate_drafts(
            conversation_id, conversation_text, analysis, retrieval, platform=conv.get("platform", "")
        )
        log_task("generation", conversation_id, "completed", "4 drafts generated")

    except Exception as exc:
        supabase.table("conversations").update({"analysis_status": "error"}).eq(
            "id", conversation_id
        ).execute()
        log_task("analysis", conversation_id, "failed", str(exc))
