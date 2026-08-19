"""Connector factory and the unified fetch interface Module 4 consumes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.schemas.connections import PLATFORMS
from app.services import token_store
from app.services.connections.base import BaseConnector, UniversalPost

# Refresh a token if it expires within this window before a fetch.
REFRESH_MARGIN = timedelta(minutes=30)


def get_connector(platform: str) -> BaseConnector:
    """Return the connector instance for a platform name."""
    platform = platform.lower()
    if platform == "reddit":
        from app.services.connections.reddit import RedditConnector

        return RedditConnector()
    if platform == "bluesky":
        from app.services.connections.bluesky import BlueskyConnector

        return BlueskyConnector()
    if platform == "mastodon":
        from app.services.connections.mastodon import MastodonConnector

        return MastodonConnector()
    if platform == "discord":
        from app.services.connections.discord import DiscordConnector

        return DiscordConnector()
    if platform == "telegram":
        from app.services.connections.telegram import TelegramConnector

        return TelegramConnector()
    if platform == "threads":
        from app.services.connections.threads import ThreadsConnector

        return ThreadsConnector()
    if platform == "youtube":
        from app.services.connections.youtube import YouTubeConnector

        return YouTubeConnector()
    raise ValueError(f"Unknown platform: {platform}")


def _expires_soon(expires_at) -> bool:
    if not expires_at:
        return False
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            return False
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at - now <= REFRESH_MARGIN


class PlatformFetchService:
    """Entry point for Module 4. Fetches normalised posts across platforms."""

    async def fetch_from_platform(
        self,
        platform: str,
        keywords: list[str],
        communities: list[str],
        since: datetime,
        limit: int = 20,
    ) -> list[UniversalPost]:
        connection = token_store.get_connection(platform)
        if not connection or connection.status not in ("connected", "expired"):
            return []
        connector = get_connector(platform)

        # Refresh proactively if the token is close to expiry.
        if _expires_soon(connection.token_expires_at) and connection.refresh_token:
            try:
                new_tokens = await connector.refresh_token(connection)
                token_store.update_tokens(platform, new_tokens)
                token_store.log_event(platform, "token_refreshed", "Refreshed before fetch.")
                connection = token_store.get_connection(platform) or connection
            except Exception as exc:
                token_store.mark_expired(platform)
                token_store.log_event(platform, "token_expired", str(exc))
                return []

        try:
            posts = await connector.fetch_posts(connection, keywords, communities, since, limit)
            token_store.mark_used(platform)
            token_store.log_event(
                platform, "fetch_success", f"Fetched {len(posts)} posts.",
                {"count": len(posts)},
            )
            return posts
        except Exception as exc:
            token_store.log_event(platform, "fetch_failed", str(exc))
            return []

    async def fetch_from_all_platforms(
        self,
        keywords: list[str],
        communities: dict[str, list[str]],
        since: datetime,
        limit_per_platform: int = 20,
    ) -> list[UniversalPost]:
        connected = [
            c.platform for c in token_store.get_all_connections() if c.status == "connected"
        ]
        tasks = [
            self.fetch_from_platform(
                platform,
                keywords,
                communities.get(platform, []),
                since,
                limit_per_platform,
            )
            for platform in connected
            if platform in PLATFORMS
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined: list[UniversalPost] = []
        for res in results:
            if isinstance(res, Exception):
                continue
            combined.extend(res)

        combined.sort(key=lambda p: p.posted_at, reverse=True)
        return combined
