"""Pydantic models and dataclasses for platform connections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel

PLATFORMS = ["reddit", "bluesky", "mastodon", "discord", "telegram", "threads", "youtube"]

# Platforms that use a redirect-based OAuth flow (get_auth_url -> callback).
OAUTH_PLATFORMS = {"reddit", "mastodon", "discord", "threads", "youtube"}
# Platforms connected directly without a redirect (credentials / bot token).
DIRECT_PLATFORMS = {"bluesky", "telegram"}


@dataclass
class ConnectionResult:
    """Outcome of a successful auth exchange, returned by every connector."""

    account_name: str | None = None
    account_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    scope: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PlatformConnection:
    """A stored connection with tokens already DECRYPTED. Never serialise this
    to an API response — use ConnectionStatusOut instead."""

    platform: str
    status: str
    account_name: str | None = None
    account_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    scope: str | None = None
    metadata: dict = field(default_factory=dict)
    last_used_at: datetime | None = None
    last_error: str | None = None
    connected_at: datetime | None = None
    id: str | None = None


# ── API response models (never contain tokens) ──────────────────

class ConnectionStatusOut(BaseModel):
    platform: str
    status: str
    account_name: str | None = None
    connected_at: datetime | None = None
    last_used_at: datetime | None = None
    last_error: str | None = None


class BlueskyConnectBody(BaseModel):
    handle: str | None = None
    app_password: str | None = None


class AuthUrlOut(BaseModel):
    platform: str
    method: str  # "oauth" | "credentials" | "bot_token"
    auth_url: str | None = None
    instructions: str | None = None
    metadata: dict | None = None
