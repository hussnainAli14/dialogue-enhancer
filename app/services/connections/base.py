"""Abstract base class every platform connector implements, plus the
UniversalPost standard format returned to Module 4."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.connections import ConnectionResult, PlatformConnection


@dataclass
class UniversalPost:
    """One post normalised across every platform. engagement_score is a float
    in [0, 1] computed per-platform from that platform's own signals."""

    platform: str
    post_id: str
    post_url: str
    author_name: str
    author_id: str
    content: str
    posted_at: datetime
    title: str | None = None
    thread_content: str | None = None
    community_name: str | None = None
    community_id: str | None = None
    comment_count: int = 0
    engagement_score: float = 0.0
    raw_data: dict = field(default_factory=dict)


class BaseConnector(ABC):
    """Contract for all connectors. Each concrete connector reads its own
    credentials from `settings` and must degrade gracefully (raise a clear
    error, never crash the process) when libraries or credentials are absent."""

    platform: str = "base"

    @abstractmethod
    def get_auth_url(self, state: str) -> str | None:
        """OAuth authorisation URL to redirect to, or None for platforms with
        no redirect flow (Bluesky, Telegram). `state` guards against CSRF."""

    @abstractmethod
    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        """Exchange an authorisation code for tokens."""

    @abstractmethod
    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        """Refresh an expired access token using the refresh token."""

    @abstractmethod
    async def validate_connection(self, connection: PlatformConnection) -> bool:
        """Lightweight API call to confirm the stored tokens still work."""

    @abstractmethod
    async def fetch_posts(
        self,
        connection: PlatformConnection,
        keywords: list[str],
        communities: list[str],
        since: datetime,
        limit: int,
    ) -> list[UniversalPost]:
        """Core method Module 4 calls: posts matching keywords from the given
        communities since `since`, capped at `limit`, as UniversalPost list."""

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Publish a reply to a post on this platform. Overridden by connectors
        that support posting; others raise a clear error."""
        raise NotImplementedError(f"Posting is not yet supported for {self.platform}.")

    # Shared helper so connectors don't each reimplement it.
    @staticmethod
    def _matches_keywords(text: str, keywords: list[str]) -> bool:
        if not keywords:
            return True
        low = (text or "").lower()
        return any(k.lower() in low for k in keywords)
