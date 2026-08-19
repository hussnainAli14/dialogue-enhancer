"""Module 10 — feedback logging and summary aggregation."""

from collections import Counter, defaultdict

from app.database import get_supabase


def log_feedback(
    draft_id: str,
    conversation_id: str | None,
    action: str,
    original_content: str | None = None,
    final_content: str | None = None,
    rejection_reason: str | None = None,
    edit_diff: str | None = None,
) -> None:
    get_supabase().table("feedback_log").insert(
        {
            "draft_id": draft_id,
            "conversation_id": conversation_id,
            "action": action,
            "original_content": original_content,
            "final_content": final_content,
            "rejection_reason": rejection_reason,
            "edit_diff": edit_diff,
        }
    ).execute()


def build_edit_diff(original: str, edited: str) -> str:
    """Simple diff summary: character count delta plus first changed sentence."""
    delta = len(edited) - len(original)
    first_changed = ""
    orig_sentences = original.split(". ")
    edit_sentences = edited.split(". ")
    for o, e in zip(orig_sentences, edit_sentences):
        if o != e:
            first_changed = e[:200]
            break
    else:
        if len(edit_sentences) != len(orig_sentences):
            first_changed = (edit_sentences[-1] if edit_sentences else "")[:200]
    return f"Character delta: {delta:+d}. First changed sentence: {first_changed or '(none)'}"


def feedback_summary() -> dict:
    supabase = get_supabase()
    drafts = (
        supabase.table("response_drafts")
        .select("id, style, status, content, edited_content, rejection_reason")
        .execute()
    ).data or []

    total = len(drafts)
    if total == 0:
        return {
            "total_drafts_generated": 0,
            "approval_rate": 0.0,
            "edit_rate": 0.0,
            "rejection_rate": 0.0,
            "most_common_rejection_reasons": [],
            "best_performing_styles": [],
            "average_edit_length_vs_original": 0.0,
        }

    approved = sum(1 for d in drafts if d["status"] in ("approved", "posted"))
    edited = sum(1 for d in drafts if d["status"] == "edited")
    rejected = sum(1 for d in drafts if d["status"] == "rejected")

    reasons = Counter(
        d["rejection_reason"] for d in drafts if d.get("rejection_reason")
    )

    style_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "approved": 0})
    for d in drafts:
        style_stats[d["style"]]["total"] += 1
        if d["status"] in ("approved", "edited", "posted"):
            style_stats[d["style"]]["approved"] += 1
    styles_ranked = sorted(
        (
            {
                "style": style,
                "total": s["total"],
                "approval_rate": round(s["approved"] / s["total"], 3),
            }
            for style, s in style_stats.items()
        ),
        key=lambda x: x["approval_rate"],
        reverse=True,
    )

    ratios = [
        len(d["edited_content"]) / len(d["content"])
        for d in drafts
        if d.get("edited_content") and d.get("content")
    ]
    avg_ratio = round(sum(ratios) / len(ratios), 3) if ratios else 0.0

    return {
        "total_drafts_generated": total,
        "approval_rate": round((approved + edited) / total, 3),
        "edit_rate": round(edited / total, 3),
        "rejection_rate": round(rejected / total, 3),
        "most_common_rejection_reasons": [
            {"reason": r, "count": c} for r, c in reasons.most_common(5)
        ],
        "best_performing_styles": styles_ranked,
        "average_edit_length_vs_original": avg_ratio,
    }
