"""Mastodon connector — OAuth 2.0 via Mastodon.py on a configured instance."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost

SCOPES = ["read", "write"]


def _as_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


class MastodonConnector(BaseConnector):
    platform = "mastodon"

    def get_auth_url(self, state: str) -> str:
        from mastodon import Mastodon

        mastodon = Mastodon(
            client_id=settings.MASTODON_CLIENT_ID,
            client_secret=settings.MASTODON_CLIENT_SECRET,
            api_base_url=settings.MASTODON_INSTANCE_URL,
        )
        return mastodon.auth_request_url(
            redirect_uris=settings.MASTODON_REDIRECT_URI,
            scopes=SCOPES,
            state=state,
        )

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        def _work() -> ConnectionResult:
            from mastodon import Mastodon

            mastodon = Mastodon(
                client_id=settings.MASTODON_CLIENT_ID,
                client_secret=settings.MASTODON_CLIENT_SECRET,
                api_base_url=settings.MASTODON_INSTANCE_URL,
            )
            access_token = mastodon.log_in(
                code=code,
                redirect_uri=settings.MASTODON_REDIRECT_URI,
                scopes=SCOPES,
            )
            account = mastodon.account_verify_credentials()
            return ConnectionResult(
                account_name=f"@{account['username']}",
                account_id=str(account["id"]),
                access_token=access_token,
                refresh_token=None,
                token_expires_at=None,
                scope=" ".join(SCOPES),
                metadata={
                    "display_name": account.get("display_name"),
                    "instance": settings.MASTODON_INSTANCE_URL,
                },
            )

        return await asyncio.to_thread(_work)

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        return ConnectionResult(
            account_name=connection.account_name,
            account_id=connection.account_id,
            access_token=connection.access_token,
            refresh_token=None,
            token_expires_at=None,
            scope=connection.scope,
            metadata=connection.metadata,
        )

    def _client(self, connection: PlatformConnection):
        from mastodon import Mastodon

        instance = (connection.metadata or {}).get("instance") or settings.MASTODON_INSTANCE_URL
        return Mastodon(access_token=connection.access_token, api_base_url=instance)

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        def _work() -> bool:
            return self._client(connection).account_verify_credentials() is not None

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return False

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the status is still live, False if deleted/removed."""

        def _work() -> bool:
            mastodon = self._client(connection)
            status_id = target.get("id") or target.get("post_id")
            if not status_id:
                raise ValueError("No Mastodon status id to check.")
            try:
                mastodon.status(status_id)
                return True
            except Exception:
                return False

        return await asyncio.to_thread(_work)

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Publish a reply to a Mastodon status. `target` needs the status id
        (as `id` or `post_id`)."""

        def _work() -> dict:
            mastodon = self._client(connection)
            status_id = target.get("id") or target.get("post_id")
            if not status_id:
                raise ValueError("Missing Mastodon status id to reply to.")
            status = mastodon.status_post(
                text, in_reply_to_id=status_id, visibility="public"
            )
            return {"id": str(status["id"]), "url": status.get("url")}

        return await asyncio.to_thread(_work)

    async def fetch_posts(
        self,
        connection: PlatformConnection,
        keywords: list[str],
        communities: list[str],
        since: datetime,
        limit: int,
    ) -> list[UniversalPost]:
        def _work() -> list[UniversalPost]:
            mastodon = self._client(connection)
            posts: list[UniversalPost] = []
            seen: set[str] = set()
            for keyword in keywords or communities:
                tag = keyword.lstrip("#")
                try:
                    statuses = mastodon.timeline_hashtag(tag, limit=min(limit, 40))
                except Exception:
                    statuses = mastodon.search_v2(keyword).get("statuses", [])
                for s in statuses:
                    sid = str(s["id"])
                    if sid in seen:
                        continue
                    created = _as_dt(s.get("created_at"))
                    if created < since:
                        continue
                    seen.add(sid)
                    replies = s.get("replies_count", 0) or 0
                    favourites = s.get("favourites_count", 0) or 0
                    reblogs = s.get("reblogs_count", 0) or 0
                    engagement = (
                        min(replies / 30, 1) * 0.5
                        + min(favourites / 50, 1) * 0.3
                        + min(reblogs / 20, 1) * 0.2
                    )
                    account = s.get("account", {})
                    posts.append(
                        UniversalPost(
                            platform="mastodon",
                            post_id=sid,
                            post_url=s.get("url", ""),
                            author_name=f"@{account.get('username', '')}",
                            author_id=str(account.get("id", "")),
                            content=_strip_html(s.get("content", "")),
                            thread_content=None,
                            community_name=f"#{tag}",
                            community_id=tag,
                            posted_at=created,
                            comment_count=replies,
                            engagement_score=round(engagement, 4),
                            raw_data={"id": sid},
                        )
                    )
                    if len(posts) >= limit:
                        return posts
            return posts

        return await asyncio.to_thread(_work)


def _strip_html(html: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html or "", "html.parser").get_text(" ").strip()
