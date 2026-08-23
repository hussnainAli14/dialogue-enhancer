"""Discord connector — OAuth for user identity, bot token for reading."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost

API = "https://discord.com/api/v10"
# read messages + identify user; bot needs message content intent enabled in the portal.
OAUTH_SCOPES = ["identify", "guilds"]
# permissions: View Channels (1024) + Send Messages (2048) + Read Message History (65536) = 68608
BOT_PERMISSIONS = 68608


class DiscordConnector(BaseConnector):
    platform = "discord"

    def get_auth_url(self, state: str) -> str:
        params = {
            "client_id": settings.DISCORD_CLIENT_ID,
            "redirect_uri": settings.DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(OAUTH_SCOPES),
            "state": state,
        }
        return f"https://discord.com/oauth2/authorize?{urlencode(params)}"

    def bot_invite_url(self) -> str:
        params = {
            "client_id": settings.DISCORD_CLIENT_ID,
            "scope": "bot",
            "permissions": str(BOT_PERMISSIONS),
        }
        return f"https://discord.com/oauth2/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        async with httpx.AsyncClient(timeout=30) as http:
            token_res = await http.post(
                f"{API}/oauth2/token",
                data={
                    "client_id": settings.DISCORD_CLIENT_ID,
                    "client_secret": settings.DISCORD_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.DISCORD_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            token_res.raise_for_status()
            tokens = token_res.json()
            me_res = await http.get(
                f"{API}/users/@me",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            me_res.raise_for_status()
            user = me_res.json()
        expires_at = None
        if tokens.get("expires_in"):
            expires_at = datetime.now(timezone.utc).timestamp() + tokens["expires_in"]
            expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        return ConnectionResult(
            account_name=user.get("username"),
            account_id=user.get("id"),
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_expires_at=expires_at,
            scope=tokens.get("scope"),
            metadata={"bot_invite_url": self.bot_invite_url()},
        )

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.post(
                f"{API}/oauth2/token",
                data={
                    "client_id": settings.DISCORD_CLIENT_ID,
                    "client_secret": settings.DISCORD_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": connection.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            res.raise_for_status()
            tokens = res.json()
        expires_at = None
        if tokens.get("expires_in"):
            expires_at = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + tokens["expires_in"], tz=timezone.utc
            )
        return ConnectionResult(
            account_name=connection.account_name,
            account_id=connection.account_id,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token") or connection.refresh_token,
            token_expires_at=expires_at,
            scope=tokens.get("scope"),
            metadata=connection.metadata,
        )

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        # Validate the BOT token — that is what reads messages.
        if not settings.DISCORD_BOT_TOKEN:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{API}/users/@me",
                    headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
                )
                return res.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _channel_message(target: dict) -> tuple[str, str]:
        """Return (channel_id, message_id) from the target, resolving from the
        post URL if needed (…/channels/{guild}/{channel}/{message})."""
        channel_id = target.get("community_id") or ""
        message_id = target.get("id") or target.get("post_id") or ""
        if (not channel_id or not message_id) and target.get("post_url"):
            parts = str(target["post_url"]).rstrip("/").split("/")
            if len(parts) >= 2:
                message_id = message_id or parts[-1]
                channel_id = channel_id or parts[-2]
        return str(channel_id), str(message_id)

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Post a reply message in the channel, referencing the original message."""
        channel_id, message_id = self._channel_message(target)
        if not channel_id:
            raise ValueError("Missing Discord channel id to post to.")
        payload: dict = {"content": text}
        if message_id:
            payload["message_reference"] = {"message_id": message_id, "fail_if_not_exists": False}
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.post(
                f"{API}/channels/{channel_id}/messages",
                json=payload,
                headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            )
            res.raise_for_status()
            m = res.json()
        return {
            "id": m["id"],
            "url": f"https://discord.com/channels/@me/{channel_id}/{m['id']}",
        }

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        channel_id, message_id = self._channel_message(target)
        if not channel_id or not message_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{API}/channels/{channel_id}/messages/{message_id}",
                    headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
                )
                return res.status_code == 200
        except Exception:
            return False

    # ── Module 3 — community discovery ──────────────────
    async def search_communities(self, keywords: list[str], limit: int = 20):
        """Discord has no reliable public server-search API. Attempt the
        discovery endpoint; return an empty list (not an error) if unavailable."""
        from app.services.community import DiscoveredCommunity

        out: list[DiscoveredCommunity] = []
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                for kw in keywords:
                    res = await http.get(
                        "https://discord.com/api/v9/discovery/search",
                        params={"query": kw, "limit": min(limit, 10)},
                    )
                    if res.status_code != 200:
                        continue
                    for hit in (res.json().get("hits") or []):
                        gid = str(hit.get("id") or hit.get("guild_id") or "")
                        if not gid:
                            continue
                        out.append(
                            DiscoveredCommunity(
                                platform="discord",
                                community_id=gid,
                                community_name=hit.get("name", "Discord server"),
                                description=hit.get("description"),
                                member_count=hit.get("approximate_member_count"),
                                activity_level="unknown",
                                discovered_via_keywords=[kw],
                            )
                        )
        except Exception:
            return []
        return out

    async def get_person_communities(self, handle: str, limit: int = 10):
        # Not feasible without being inside the servers the user is in.
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
        headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
        async with httpx.AsyncClient(timeout=30, headers=headers) as http:
            for channel_id in communities:
                res = await http.get(
                    f"{API}/channels/{channel_id}/messages",
                    params={"limit": min(limit, 100)},
                )
                if res.status_code != 200:
                    continue
                for m in res.json():
                    created = _parse_dt(m.get("timestamp"))
                    if created < since:
                        continue
                    if not self._matches_keywords(m.get("content", ""), keywords):
                        continue
                    reactions = sum(r.get("count", 0) for r in m.get("reactions", []) or [])
                    engagement = min(reactions / 20, 1) * 0.5  # replies not directly available
                    author = m.get("author", {})
                    posts.append(
                        UniversalPost(
                            platform="discord",
                            post_id=m["id"],
                            post_url=f"https://discord.com/channels/@me/{channel_id}/{m['id']}",
                            author_name=author.get("username", ""),
                            author_id=author.get("id", ""),
                            content=m.get("content", ""),
                            thread_content=None,
                            community_name=None,
                            community_id=str(channel_id),
                            posted_at=created,
                            comment_count=0,
                            engagement_score=round(engagement, 4),
                            raw_data={"id": m["id"], "channel_id": channel_id},
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
