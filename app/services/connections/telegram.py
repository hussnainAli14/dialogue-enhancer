"""Telegram connector — bot token, no OAuth."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


class TelegramConnector(BaseConnector):
    platform = "telegram"

    def get_auth_url(self, state: str) -> None:
        return None  # no OAuth for Telegram

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        raise NotImplementedError("Telegram connects via connect() using the bot token.")

    async def connect(self) -> ConnectionResult:
        """Validate the bot token via getMe and store bot identity."""
        if not settings.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set.")
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(_api("getMe"))
                res.raise_for_status()
                data = res.json()
        except httpx.TimeoutException as exc:
            raise ValueError(
                "Could not reach api.telegram.org (request timed out). Telegram's "
                "Bot API appears blocked on this network — try a VPN."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Telegram rejected the token (HTTP {exc.response.status_code}). "
                "Check TELEGRAM_BOT_TOKEN."
            ) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Network error reaching Telegram: {type(exc).__name__}") from exc
        if not data.get("ok"):
            raise ValueError("Telegram getMe failed — invalid bot token.")
        bot = data["result"]
        return ConnectionResult(
            account_name=f"@{bot.get('username', settings.TELEGRAM_BOT_USERNAME)}",
            account_id=str(bot.get("id", "")),
            access_token=settings.TELEGRAM_BOT_TOKEN,
            refresh_token=None,
            token_expires_at=None,
            scope=None,
            metadata={"username": bot.get("username"), "is_bot": bot.get("is_bot")},
        )

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

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(_api("getMe"))
                return res.status_code == 200 and res.json().get("ok", False)
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
        """Read via getUpdates. A bot only receives messages from chats it is a
        member of; channel post visibility requires the bot to be an admin."""
        posts: list[UniversalPost] = []
        wanted = {str(c).lstrip("@") for c in communities} if communities else None
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.get(_api("getUpdates"), params={"limit": 100, "allowed_updates": '["channel_post","message"]'})
            if res.status_code != 200:
                return posts
            for upd in res.json().get("result", []):
                msg = upd.get("channel_post") or upd.get("message")
                if not msg:
                    continue
                created = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc)
                if created < since:
                    continue
                chat = msg.get("chat", {})
                chat_key = str(chat.get("username") or chat.get("id"))
                if wanted and chat_key.lstrip("@") not in wanted:
                    continue
                text = msg.get("text") or msg.get("caption") or ""
                if not self._matches_keywords(text, keywords):
                    continue
                forwards = msg.get("forward_from_message_id") and 1 or 0
                views = msg.get("views", 0) or 0
                engagement = min(forwards / 50, 1) * 0.5 + min(views / 500, 1) * 0.5
                posts.append(
                    UniversalPost(
                        platform="telegram",
                        post_id=str(msg.get("message_id")),
                        post_url=(
                            f"https://t.me/{chat.get('username')}/{msg.get('message_id')}"
                            if chat.get("username")
                            else ""
                        ),
                        author_name=chat.get("title") or chat.get("username") or "",
                        author_id=str(chat.get("id", "")),
                        content=text,
                        thread_content=None,
                        community_name=chat.get("title"),
                        community_id=chat_key,
                        posted_at=created,
                        comment_count=0,
                        engagement_score=round(engagement, 4),
                        raw_data={"message_id": msg.get("message_id"), "chat_id": chat.get("id")},
                    )
                )
                if len(posts) >= limit:
                    break
        return posts
