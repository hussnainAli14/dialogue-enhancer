"""Standalone posting — publish the author's own post (text + optional images)
directly to a connected platform. Distinct from Module 9 reply posting."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.database import get_supabase
from app.envelope import fail, ok
from app.services import token_store
from app.services.connections.base import PostMedia
from app.services.posting import (
    PLATFORM_CHAR_LIMITS,
    SUPPORTED_STANDALONE,
    publish_post,
)

router = APIRouter(prefix="/posts", tags=["posts"])

# Max images accepted per post (Bluesky/Mastodon both allow 4).
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB per image


@router.get("/history")
async def posted_history(page: int = 1, page_size: int = 50):
    """Everything you've published, newest first: standalone Compose posts and
    posted replies, each with platform, text, and a link to the live post."""
    try:
        supabase = get_supabase()
        items: list[dict] = []

        # Standalone Compose posts.
        try:
            for p in (
                supabase.table("published_posts")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            ).data or []:
                items.append(
                    {
                        "type": "post",
                        "platform": p.get("platform"),
                        "content": p.get("content") or "",
                        "url": p.get("post_url"),
                        "posted_at": p.get("created_at"),
                    }
                )
        except Exception:
            pass

        # Posted replies — join drafts to their conversation for the platform.
        posted_drafts = (
            supabase.table("response_drafts")
            .select("*")
            .eq("status", "posted")
            .order("posted_at", desc=True)
            .execute()
        ).data or []
        conv_ids = list({d["conversation_id"] for d in posted_drafts if d.get("conversation_id")})
        convs: dict[str, dict] = {}
        if conv_ids:
            for c in (
                supabase.table("conversations")
                .select("id, platform, post_url, post_author")
                .in_("id", conv_ids)
                .execute()
            ).data or []:
                convs[c["id"]] = c
        for d in posted_drafts:
            conv = convs.get(d.get("conversation_id"), {})
            items.append(
                {
                    "type": "reply",
                    "platform": conv.get("platform"),
                    "content": d.get("edited_content") or d.get("content") or "",
                    # the reply's own link if captured, else the post it replied to
                    "url": d.get("posted_url") or conv.get("post_url"),
                    "posted_at": d.get("posted_at"),
                    "in_reply_to": conv.get("post_author"),
                }
            )

        items.sort(key=lambda x: x.get("posted_at") or "", reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return ok(
            {
                "page": page,
                "page_size": page_size,
                "total": total,
                "items": items[start : start + page_size],
            }
        )
    except Exception as exc:
        return fail(f"Failed to load posted history: {exc}", 500)


@router.get("/targets")
async def targets():
    """Platforms that support standalone posting and whether each is connected,
    so the composer can offer only usable options."""
    try:
        connected = {
            c.platform for c in token_store.get_all_connections() if c.status == "connected"
        }
        out = [
            {
                "platform": p,
                "connected": p in connected,
                "char_limit": PLATFORM_CHAR_LIMITS.get(p),
            }
            for p in sorted(SUPPORTED_STANDALONE)
        ]
        return ok({"targets": out})
    except Exception as exc:
        return fail(f"Failed to load posting targets: {exc}", 500)


@router.post("/compose-suggest")
async def compose_suggest(body: dict):
    """Generate four original-post candidates (Wholistic / Challenging / Insightful
    / Facilitative) from the author's seed thoughts, grounded in the knowledge
    base. Returns candidates for the composer — nothing is posted or stored."""
    body = body or {}
    seed = {
        "thinking": (body.get("thinking") or "").strip(),
        "example": (body.get("example") or "").strip(),
        "tension": (body.get("tension") or "").strip(),
        "invite": (body.get("invite") or "").strip(),
    }
    if not any(seed.values()):
        return fail("Fill in at least one box so there's something to work from.", 400)
    char_limit = body.get("char_limit")
    try:
        char_limit = int(char_limit) if char_limit else None
    except (TypeError, ValueError):
        char_limit = None
    try:
        from app.services.generation import generate_compose_candidates

        candidates = await generate_compose_candidates(seed, char_limit=char_limit)
        return ok({"candidates": candidates})
    except Exception as exc:
        return fail(f"Failed to generate suggestions: {exc}", 500)


@router.post("/poll-replies")
async def poll_replies_now():
    """Manually check connected platforms for new replies to your posts."""
    try:
        from app.services.replies import poll_replies

        return ok(await poll_replies())
    except Exception as exc:
        return fail(f"Failed to poll replies: {exc}", 500)


@router.post("")
async def create_post(
    platforms: list[str] = Form(...),
    text: str = Form(""),
    alts: list[str] = Form(default=[]),
    images: list[UploadFile] = File(default=[]),
):
    """Publish one standalone post to one or more platforms at once. Multipart:
    platforms[] (one or many), text, optional images[] plus matching alts[].
    Each platform is posted independently — one failing never blocks the others.
    """
    # `platforms` may arrive as a single comma-joined field; normalise either way.
    targets: list[str] = []
    for p in platforms:
        targets.extend(x.strip() for x in p.split(",") if x.strip())
    targets = list(dict.fromkeys(targets))  # de-dupe, keep order
    if not targets:
        return fail("Select at least one platform.", 400)

    media: list[PostMedia] = []
    files = [f for f in (images or []) if f and f.filename]
    if len(files) > MAX_IMAGES:
        return fail(f"At most {MAX_IMAGES} images per post.", 400)

    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > MAX_IMAGE_BYTES:
            return fail(f"Image '{f.filename}' exceeds the 8 MB limit.", 400)
        content_type = f.content_type or "application/octet-stream"
        if not content_type.startswith("image/"):
            return fail(f"'{f.filename}' is not an image.", 400)
        media.append(
            PostMedia(
                data=data,
                content_type=content_type,
                filename=f.filename,
                alt=(alts[i] if i < len(alts) else "") or "",
            )
        )

    results = []
    for platform in targets:
        try:
            result = await publish_post(platform, text, media=media)
            results.append({"platform": platform, "success": True, "result": result})
            # Record the published post so it shows in Posted history. Best-effort:
            # never let a logging failure affect the actual publish result.
            try:
                get_supabase().table("published_posts").insert(
                    {
                        "platform": platform,
                        "content": text,
                        "post_url": (result or {}).get("url") or (result or {}).get("post_url"),
                    }
                ).execute()
            except Exception:
                pass
        except Exception as exc:
            results.append({"platform": platform, "success": False, "error": str(exc)})

    posted = sum(1 for r in results if r["success"])
    return ok({"results": results, "posted": posted, "total": len(targets)})
