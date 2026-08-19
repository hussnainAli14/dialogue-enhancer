"""Bluesky connector — AT Protocol with handle + app password (no OAuth)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


class BlueskyConnector(BaseConnector):
    platform = "bluesky"

    def get_auth_url(self, state: str) -> None:
        # No redirect OAuth flow for Bluesky.
        return None

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        raise NotImplementedError("Bluesky connects via connect(handle, app_password), not OAuth.")

    async def connect(self, handle: str | None = None, app_password: str | None = None) -> ConnectionResult:
        handle = handle or settings.BLUESKY_HANDLE
        app_password = app_password or settings.BLUESKY_APP_PASSWORD
        if not handle or not app_password:
            raise ValueError("Bluesky handle and app password are required.")

        def _work() -> ConnectionResult:
            from atproto import Client

            client = Client()
            profile = client.login(handle, app_password)
            session_string = client.export_session_string()
            return ConnectionResult(
                account_name=getattr(profile, "handle", handle),
                account_id=getattr(profile, "did", handle),
                access_token=session_string,
                refresh_token=None,
                token_expires_at=None,
                scope=None,
                metadata={"handle": handle, "did": getattr(profile, "did", None)},
            )

        return await asyncio.to_thread(_work)

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        # Re-login with stored session; app-password sessions self-refresh in client.
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
        from atproto import Client

        client = Client()
        if connection.access_token:
            client.login(session_string=connection.access_token)
        return client

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        def _work() -> bool:
            client = self._client(connection)
            handle = (connection.metadata or {}).get("handle") or connection.account_name
            client.get_profile(handle)
            return True

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return False

    def _resolve_uri(self, client, target: dict) -> str:
        """Return the parent post's at-uri. Uses a stored at:// uri if present,
        otherwise resolves it from the post URL (handle + rkey -> did -> uri)."""
        uri = target.get("uri") or target.get("post_id")
        if uri and str(uri).startswith("at://"):
            return uri
        url = target.get("post_url") or ""
        m = re.search(r"/profile/([^/]+)/post/([^/?#]+)", url)
        if not m:
            raise ValueError("Cannot resolve a Bluesky post from the stored URL.")
        handle, rkey = m.group(1), m.group(2)
        did = handle
        if not handle.startswith("did:"):
            res = client.com.atproto.identity.resolve_handle({"handle": handle})
            did = res.did
        return f"at://{did}/app.bsky.feed.post/{rkey}"

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the post is still live, False if deleted/removed/blocked."""

        def _work() -> bool:
            client = self._client(connection)
            uri = self._resolve_uri(client, target)
            try:
                thread = client.get_post_thread(uri)
            except Exception:
                return False  # NotFound / deleted
            node = getattr(thread, "thread", None)
            return node is not None and getattr(node, "post", None) is not None

        return await asyncio.to_thread(_work)

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Publish a reply to a Bluesky post. `target` needs the parent's at-uri
        (as `uri` or `post_id`); the cid is resolved live from the thread."""

        def _work() -> dict:
            from atproto import models

            client = self._client(connection)
            uri = self._resolve_uri(client, target)

            thread = client.get_post_thread(uri)
            post = thread.thread.post  # has .uri and .cid
            parent_ref = models.ComAtprotoRepoStrongRef.Main(cid=post.cid, uri=post.uri)

            # Thread root: reuse the original post's root if it is itself a reply.
            root_ref = parent_ref
            record = getattr(post, "record", None)
            reply = getattr(record, "reply", None) if record else None
            if reply and getattr(reply, "root", None):
                root_ref = models.ComAtprotoRepoStrongRef.Main(
                    cid=reply.root.cid, uri=reply.root.uri
                )

            reply_ref = models.AppBskyFeedPost.ReplyRef(parent=parent_ref, root=root_ref)
            resp = client.send_post(text=text, reply_to=reply_ref)
            handle = (connection.metadata or {}).get("handle") or connection.account_name
            rkey = resp.uri.split("/")[-1]
            return {
                "uri": resp.uri,
                "cid": resp.cid,
                "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
            }

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
            client = self._client(connection)
            posts: list[UniversalPost] = []
            for keyword in keywords or communities:
                res = client.app.bsky.feed.search_posts({"q": keyword, "limit": min(limit, 25)})
                for p in getattr(res, "posts", []):
                    created = _parse_dt(getattr(p.record, "created_at", None))
                    if created < since:
                        continue
                    reply_count = getattr(p, "reply_count", 0) or 0
                    like_count = getattr(p, "like_count", 0) or 0
                    repost_count = getattr(p, "repost_count", 0) or 0
                    engagement = (
                        min(reply_count / 50, 1) * 0.5
                        + min(like_count / 100, 1) * 0.3
                        + min(repost_count / 50, 1) * 0.2
                    )
                    author = getattr(p, "author", None)
                    handle = getattr(author, "handle", "") if author else ""
                    rkey = p.uri.split("/")[-1]
                    posts.append(
                        UniversalPost(
                            platform="bluesky",
                            post_id=p.uri,
                            post_url=f"https://bsky.app/profile/{handle}/post/{rkey}",
                            author_name=handle,
                            author_id=getattr(author, "did", "") if author else "",
                            content=getattr(p.record, "text", ""),
                            thread_content=None,
                            community_name=None,
                            community_id=None,
                            posted_at=created,
                            comment_count=reply_count,
                            engagement_score=round(engagement, 4),
                            raw_data={"uri": p.uri, "cid": getattr(p, "cid", None)},
                        )
                    )
                    if len(posts) >= limit:
                        return posts
            return posts

        return await asyncio.to_thread(_work)
