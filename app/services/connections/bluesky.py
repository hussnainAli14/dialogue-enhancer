"""Bluesky connector — AT Protocol with handle + app password (no OAuth)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

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
                # App password is kept (encrypted at rest) so the session can be
                # re-established automatically when it expires or is revoked.
                refresh_token=app_password,
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

    @staticmethod
    def _is_expired_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "expiredtoken" in msg or "token has been revoked" in msg or "token has expired" in msg

    def _fresh_client(self, connection: PlatformConnection):
        """Re-login with the stored handle + app password (refresh_token) and
        persist the new session string, so a revoked/expired session self-heals.
        Returns a logged-in client. Raises a clear error if no app password."""
        from atproto import Client

        from app.services import token_store

        handle = (connection.metadata or {}).get("handle") or connection.account_name
        app_password = connection.refresh_token or settings.BLUESKY_APP_PASSWORD
        handle = handle or settings.BLUESKY_HANDLE
        if not handle or not app_password:
            raise ValueError(
                "Bluesky session expired and no stored app password to reconnect. "
                "Reconnect Bluesky in Connections."
            )
        client = Client()
        profile = client.login(handle, app_password)
        new_session = client.export_session_string()
        token_store.update_tokens(
            "bluesky", ConnectionResult(access_token=new_session, account_name=handle)
        )
        token_store.log_event("bluesky", "token_refreshed", "Session auto-refreshed after expiry.")
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

        def _reply(client) -> dict:
            from atproto import models

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

        def _work() -> dict:
            try:
                return _reply(self._client(connection))
            except Exception as exc:
                if self._is_expired_error(exc):
                    return _reply(self._fresh_client(connection))
                raise

        return await asyncio.to_thread(_work)

    async def create_post(self, connection: PlatformConnection, text: str, media=None) -> dict:
        """Publish a new standalone Bluesky post, optionally with up to 4 images.
        Auto-reconnects once if the stored session has expired/been revoked."""

        def _send(client) -> dict:
            images = list(media or [])[:4]
            if images:
                resp = client.send_images(
                    text=text,
                    images=[m.data for m in images],
                    image_alts=[m.alt or "" for m in images],
                )
            else:
                resp = client.send_post(text=text)
            handle = (connection.metadata or {}).get("handle") or connection.account_name
            rkey = resp.uri.split("/")[-1]
            return {
                "uri": resp.uri,
                "cid": resp.cid,
                "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
            }

        def _work() -> dict:
            try:
                return _send(self._client(connection))
            except Exception as exc:
                if self._is_expired_error(exc):
                    return _send(self._fresh_client(connection))
                raise

        return await asyncio.to_thread(_work)

    async def fetch_replies(self, connection, post_id, exclude_author_id=None):
        """Direct replies to a Bluesky post (post_id = at-uri)."""

        def _work() -> list[dict]:
            client = self._client(connection)
            thread = client.get_post_thread(post_id)
            node = getattr(thread, "thread", None)
            out: list[dict] = []
            for r in getattr(node, "replies", []) or []:
                post = getattr(r, "post", None)
                if not post:
                    continue
                author = getattr(post, "author", None)
                did = getattr(author, "did", "") if author else ""
                if exclude_author_id and did == exclude_author_id:
                    continue
                handle = getattr(author, "handle", "") if author else ""
                rkey = post.uri.split("/")[-1]
                out.append(
                    {
                        "reply_id": post.uri,
                        "post_url": f"https://bsky.app/profile/{handle}/post/{rkey}",
                        "author_name": handle,
                        "author_id": did,
                        "content": getattr(getattr(post, "record", None), "text", "") or "",
                        "created_at": getattr(getattr(post, "record", None), "created_at", None),
                    }
                )
            return out

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return []

    # ── Module 3 — community discovery ──────────────────
    async def search_communities(self, keywords: list[str], limit: int = 20):
        from app.services import token_store
        from app.services.community import DiscoveredCommunity

        conn = token_store.get_connection("bluesky")
        if not conn or conn.status != "connected":
            return []

        def _work():
            client = self._client(conn)
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            out: list[DiscoveredCommunity] = []
            for kw in keywords:
                tag = kw.replace(" ", "")
                res = client.app.bsky.feed.search_posts({"q": kw, "limit": 25})
                posts = getattr(res, "posts", []) or []
                recent = sum(
                    1
                    for p in posts
                    if _parse_dt(getattr(p.record, "created_at", None)) >= cutoff
                )
                level = "high" if recent > 50 else "medium" if recent > 10 else "low"
                out.append(
                    DiscoveredCommunity(
                        platform="bluesky",
                        community_id=tag,
                        community_name=f"#{tag}",
                        community_url=f"https://bsky.app/hashtag/{tag}",
                        description=f"Bluesky posts about {kw}",
                        activity_level=level,
                        discovered_via_keywords=[kw],
                    )
                )
            return out

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return []

    async def get_person_communities(self, handle: str, limit: int = 10):
        from app.services import token_store
        from app.services.community import DiscoveredCommunity

        conn = token_store.get_connection("bluesky")
        if not conn or conn.status != "connected":
            return []

        def _work():
            client = self._client(conn)
            feed = client.get_author_feed(handle, limit=100)
            counts: dict[str, int] = {}
            for item in getattr(feed, "feed", []) or []:
                text = getattr(item.post.record, "text", "") or ""
                for tag in re.findall(r"#(\w+)", text):
                    counts[tag] = counts.get(tag, 0) + 1
            top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
            return [
                DiscoveredCommunity(
                    platform="bluesky",
                    community_id=t,
                    community_name=f"#{t}",
                    community_url=f"https://bsky.app/hashtag/{t}",
                    discovery_method="people_based",
                )
                for t, _ in top
            ]

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return []

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
