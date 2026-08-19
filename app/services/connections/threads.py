"""Threads connector — OAuth 2.0 via Meta Graph API (long-lived tokens)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost

AUTH = "https://threads.net/oauth/authorize"
GRAPH = "https://graph.threads.net"
SCOPES = ["threads_basic", "threads_read_replies"]


class ThreadsConnector(BaseConnector):
    platform = "threads"

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": settings.THREADS_APP_ID,
            "redirect_uri": settings.THREADS_REDIRECT_URI,
            "scope": ",".join(SCOPES),
            "response_type": "code",
            "state": state,
        }
        return f"{AUTH}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        async with httpx.AsyncClient(timeout=30) as http:
            short = await http.post(
                f"{GRAPH}/oauth/access_token",
                data={
                    "client_id": settings.THREADS_APP_ID,
                    "client_secret": settings.THREADS_APP_SECRET,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.THREADS_REDIRECT_URI,
                    "code": code,
                },
            )
            short.raise_for_status()
            short_token = short.json()["access_token"]

            long = await http.get(
                f"{GRAPH}/access_token",
                params={
                    "grant_type": "th_exchange_token",
                    "client_secret": settings.THREADS_APP_SECRET,
                    "access_token": short_token,
                },
            )
            long.raise_for_status()
            long_data = long.json()
            access_token = long_data["access_token"]
            expires_in = long_data.get("expires_in", 60 * 24 * 3600)

            me = await http.get(
                f"{GRAPH}/v1.0/me",
                params={"fields": "id,username", "access_token": access_token},
            )
            me.raise_for_status()
            user = me.json()

        return ConnectionResult(
            account_name=f"@{user.get('username', '')}",
            account_id=str(user.get("id", "")),
            access_token=access_token,
            refresh_token=None,
            token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            scope=",".join(SCOPES),
            metadata={"username": user.get("username")},
        )

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.get(
                f"{GRAPH}/refresh_access_token",
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": connection.access_token,
                },
            )
            res.raise_for_status()
            data = res.json()
        return ConnectionResult(
            account_name=connection.account_name,
            account_id=connection.account_id,
            access_token=data["access_token"],
            refresh_token=None,
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=data.get("expires_in", 60 * 24 * 3600)),
            scope=connection.scope,
            metadata=connection.metadata,
        )

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{GRAPH}/v1.0/me",
                    params={"fields": "id", "access_token": connection.access_token},
                )
                return res.status_code == 200
        except Exception:
            return False

    async def fetch_posts(
        self,
        connection: PlatformConnection,
        keywords: list[str],
        communities: list[str],
        since: datetime,
        limit: int,
    ) -> list[UniversalPost]:
        posts: list[UniversalPost] = []
        async with httpx.AsyncClient(timeout=30) as http:
            for keyword in keywords or communities:
                res = await http.get(
                    f"{GRAPH}/v1.0/keyword_search",
                    params={
                        "q": keyword,
                        "search_type": "TOP",
                        "fields": "id,text,username,permalink,timestamp,replies_count,likes_count",
                        "access_token": connection.access_token,
                    },
                )
                if res.status_code != 200:
                    continue
                for p in res.json().get("data", []):
                    created = _parse_dt(p.get("timestamp"))
                    if created < since:
                        continue
                    replies = p.get("replies_count", 0) or 0
                    likes = p.get("likes_count", 0) or 0
                    engagement = min(replies / 30, 1) * 0.5 + min(likes / 100, 1) * 0.5
                    posts.append(
                        UniversalPost(
                            platform="threads",
                            post_id=str(p.get("id")),
                            post_url=p.get("permalink", ""),
                            author_name=f"@{p.get('username', '')}",
                            author_id=str(p.get("username", "")),
                            content=p.get("text", ""),
                            thread_content=None,
                            community_name=None,
                            community_id=None,
                            posted_at=created,
                            comment_count=replies,
                            engagement_score=round(engagement, 4),
                            raw_data={"id": p.get("id")},
                        )
                    )
                    if len(posts) >= limit:
                        return posts
        return posts


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
