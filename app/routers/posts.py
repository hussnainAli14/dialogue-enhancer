"""Standalone posting — publish the author's own post (text + optional images)
directly to a connected platform. Distinct from Module 9 reply posting."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

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
        except Exception as exc:
            results.append({"platform": platform, "success": False, "error": str(exc)})

    posted = sum(1 for r in results if r["success"])
    return ok({"results": results, "posted": posted, "total": len(targets)})
