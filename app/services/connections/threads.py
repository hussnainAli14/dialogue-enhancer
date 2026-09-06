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
SCOPES = [
    "threads_basic",
    "threads_read_replies",
    "threads_content_publish",
    "threads_manage_replies",
]


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

    async def _publish(self, connection: PlatformConnection, text: str, reply_to_id: str | None = None) -> dict:
        """Threads' two-step publish: create a text container, then publish it.
        Returns {id, url}."""
        uid = connection.account_id
        token = connection.access_token
        if not uid:
            raise ValueError("Missing Threads user id — reconnect Threads.")
        async with httpx.AsyncClient(timeout=30) as http:
            create_params = {"media_type": "TEXT", "text": text, "access_token": token}
            if reply_to_id:
                create_params["reply_to_id"] = reply_to_id
            created = await http.post(f"{GRAPH}/v1.0/{uid}/threads", data=create_params)
            created.raise_for_status()
            creation_id = created.json()["id"]

            published = await http.post(
                f"{GRAPH}/v1.0/{uid}/threads_publish",
                data={"creation_id": creation_id, "access_token": token},
            )
            published.raise_for_status()
            media_id = str(published.json()["id"])

            url = None
            try:
                meta = await http.get(
                    f"{GRAPH}/v1.0/{media_id}",
                    params={"fields": "permalink", "access_token": token},
                )
                if meta.status_code == 200:
                    url = meta.json().get("permalink")
            except Exception:
                pass
        return {"id": media_id, "url": url}

    async def create_post(self, connection: PlatformConnection, text: str, media=None) -> dict:
        """Publish a new standalone Threads post. Text only for now — Threads
        image publishing needs a publicly hosted image URL, which the app does
        not provide yet."""
        if media:
            raise ValueError(
                "Threads image posting isn't supported yet (Threads requires a public "
                "image URL). Post text only for now."
            )
        return await self._publish(connection, text)

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Publish a reply to a Threads post. `target` needs the post id (as
        `id` or `post_id`)."""
        reply_to_id = target.get("id") or target.get("post_id")
        if not reply_to_id:
            raise ValueError("Missing Threads post id to reply to.")
        return await self._publish(connection, text, reply_to_id=reply_to_id)

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the Threads post is still retrievable."""
        post_id = target.get("id") or target.get("post_id")
        if not post_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{GRAPH}/v1.0/{post_id}",
                    params={"fields": "id", "access_token": connection.access_token},
                )
                return res.status_code == 200
        except Exception:
            return False

    # ── Module 3 — community discovery ──────────────────
    async def search_communities(self, keywords: list[str], limit: int = 20):
        from app.services import token_store
        from app.services.community import DiscoveredCommunity

        conn = token_store.get_connection("threads")
        if not conn or conn.status != "connected":
            return []

        out: list[DiscoveredCommunity] = []
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                for kw in keywords:
                    res = await http.get(
                        f"{GRAPH}/v1.0/keyword_search",
                        params={
                            "q": kw,
                            "search_type": "TOP",
                            "fields": "id",
                            "access_token": conn.access_token,
                        },
                    )
                    count = len(res.json().get("data", [])) if res.status_code == 200 else 0
                    level = "high" if count > 20 else "medium" if count > 5 else "low"
                    tag = kw.replace(" ", "")
                    out.append(
                        DiscoveredCommunity(
                            platform="threads",
                            community_id=tag,
                            community_name=f"#{tag}",
                            community_url=f"https://www.threads.net/search?q={kw}",
                            activity_level=level,
                            discovered_via_keywords=[kw],
                        )
                    )
        except Exception:
            return []
        return out

    async def get_person_communities(self, handle: str, limit: int = 10):
        # Threads person-level topic extraction needs the person's own token; skip.
        return []

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
