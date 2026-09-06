"""Module 2 — platform connection OAuth + management endpoints."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.config import settings
from app.envelope import fail, ok
from app.schemas.connections import (
    DIRECT_PLATFORMS,
    OAUTH_PLATFORMS,
    PLATFORMS,
    BlueskyConnectBody,
)
from app.services import token_store
from app.services.connections.factory import get_connector

router = APIRouter(prefix="/connections", tags=["connections"])

# Short-lived in-memory CSRF state store: state -> platform.
# Fine for a single-user, single-process deployment.
_STATE: dict[str, str] = {}


def _valid_platform(platform: str) -> bool:
    return platform in PLATFORMS


def _frontend_redirect(platform: str, ok_flag: bool, message: str = "") -> RedirectResponse:
    params = {"platform": platform}
    params["connected" if ok_flag else "error"] = "1" if ok_flag else message or "failed"
    url = f"{settings.FRONTEND_URL}/settings?{urlencode(params)}#connections"
    return RedirectResponse(url)


@router.get("/status")
async def status():
    try:
        stored = {c.platform: c for c in token_store.get_all_connections()}
        out = []
        for platform in PLATFORMS:
            c = stored.get(platform)
            out.append(
                {
                    "platform": platform,
                    "status": c.status if c else "disconnected",
                    "account_name": c.account_name if c else None,
                    "connected_at": c.connected_at if c else None,
                    "last_used_at": c.last_used_at if c else None,
                    "last_error": c.last_error if c else None,
                    "method": "oauth" if platform in OAUTH_PLATFORMS else "direct",
                }
            )
        return ok({"connections": out})
    except Exception as exc:
        return fail(f"Failed to load connection status: {exc}", 500)


@router.get("/logs")
async def logs(platform: str | None = None):
    try:
        return ok({"logs": token_store.get_logs(platform, limit=50)})
    except Exception as exc:
        return fail(f"Failed to load logs: {exc}", 500)


@router.get("/{platform}/auth-url")
async def auth_url(platform: str):
    if not _valid_platform(platform):
        return fail("Unknown platform", 404)

    if platform in DIRECT_PLATFORMS:
        if platform == "bluesky":
            return ok(
                {
                    "platform": platform,
                    "method": "credentials",
                    "auth_url": None,
                    "instructions": "Enter your Bluesky handle and an app password "
                    "(bsky.app/settings/app-passwords).",
                }
            )
        return ok(
            {
                "platform": platform,
                "method": "bot_token",
                "auth_url": None,
                "instructions": "Telegram connects using the bot token in the server "
                "environment. Click Connect to validate it.",
                "metadata": {"bot_username": settings.TELEGRAM_BOT_USERNAME},
            }
        )

    try:
        state = secrets.token_urlsafe(24)
        _STATE[state] = platform
        connector = get_connector(platform)
        url = connector.get_auth_url(state)
        token_store.log_event(platform, "connect_initiated", "Auth URL generated.")
        metadata = {}
        if platform == "discord":
            metadata["bot_invite_url"] = connector.bot_invite_url()  # type: ignore[attr-defined]
        return ok(
            {"platform": platform, "method": "oauth", "auth_url": url, "metadata": metadata}
        )
    except Exception as exc:
        return fail(f"Failed to generate auth URL: {exc}", 500)


@router.get("/{platform}/callback")
async def callback(platform: str, code: str | None = None, state: str | None = None, error: str | None = None):
    if not _valid_platform(platform):
        return _frontend_redirect(platform, False, "unknown_platform")
    if error:
        token_store.log_event(platform, "connect_failed", f"Provider error: {error}")
        return _frontend_redirect(platform, False, error)
    if not code or not state or _STATE.get(state) != platform:
        token_store.log_event(platform, "connect_failed", "Invalid state or missing code.")
        return _frontend_redirect(platform, False, "invalid_state")

    _STATE.pop(state, None)
    try:
        connector = get_connector(platform)
        result = await connector.exchange_code(code, state)
        token_store.save_connection(platform, result)
        token_store.log_event(platform, "connect_success", f"Connected as {result.account_name}")
        return _frontend_redirect(platform, True)
    except Exception as exc:
        token_store.mark_error(platform, str(exc))
        token_store.log_event(platform, "connect_failed", str(exc))
        return _frontend_redirect(platform, False, "exchange_failed")


@router.post("/bluesky/connect")
async def bluesky_connect(body: BlueskyConnectBody):
    try:
        connector = get_connector("bluesky")
        result = await connector.connect(body.handle, body.app_password)  # type: ignore[attr-defined]
        token_store.save_connection("bluesky", result)
        token_store.log_event("bluesky", "connect_success", f"Connected as {result.account_name}")
        return ok({"platform": "bluesky", "status": "connected", "account_name": result.account_name})
    except Exception as exc:
        token_store.mark_error("bluesky", str(exc))
        token_store.log_event("bluesky", "connect_failed", str(exc))
        return fail(f"Bluesky connection failed: {exc}", 400)


@router.post("/telegram/connect")
async def telegram_connect():
    try:
        connector = get_connector("telegram")
        result = await connector.connect()  # type: ignore[attr-defined]
        token_store.save_connection("telegram", result)
        token_store.log_event("telegram", "connect_success", f"Bot {result.account_name}")
        return ok(
            {"platform": "telegram", "status": "connected", "account_name": result.account_name}
        )
    except Exception as exc:
        token_store.mark_error("telegram", str(exc))
        token_store.log_event("telegram", "connect_failed", str(exc))
        return fail(f"Telegram connection failed: {exc}", 400)


@router.post("/{platform}/validate")
async def validate(platform: str):
    if not _valid_platform(platform):
        return fail("Unknown platform", 404)
    connection = token_store.get_connection(platform)
    if not connection or connection.status == "disconnected":
        return ok({"platform": platform, "valid": False, "reason": "not_connected"})
    try:
        connector = get_connector(platform)
        valid = await connector.validate_connection(connection)
        if not valid:
            token_store.mark_error(platform, "Validation failed")
        return ok(
            {"platform": platform, "valid": valid, "account_name": connection.account_name if valid else None}
        )
    except Exception as exc:
        return fail(f"Validation error: {exc}", 500)


@router.post("/{platform}/refresh")
async def refresh(platform: str):
    if not _valid_platform(platform):
        return fail("Unknown platform", 404)
    connection = token_store.get_connection(platform)
    if not connection or not connection.refresh_token:
        return fail("No refresh token available for this platform", 400)
    try:
        connector = get_connector(platform)
        new_tokens = await connector.refresh_token(connection)
        token_store.update_tokens(platform, new_tokens)
        token_store.log_event(platform, "token_refreshed", "Manual refresh.")
        return ok({"platform": platform, "status": "connected"})
    except Exception as exc:
        token_store.mark_error(platform, str(exc))
        return fail(f"Refresh failed: {exc}", 500)


@router.delete("/{platform}")
async def disconnect(platform: str):
    if not _valid_platform(platform):
        return fail("Unknown platform", 404)
    try:
        token_store.mark_disconnected(platform)
        token_store.log_event(platform, "disconnected", "User disconnected.")
        return ok({"platform": platform, "status": "disconnected"})
    except Exception as exc:
        return fail(f"Disconnect failed: {exc}", 500)
