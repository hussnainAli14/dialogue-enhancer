"""X (Twitter) connector — OAuth 2.0 (PKCE) via the X API v2.

Posting only. Reading/searching other users' posts (discovery) is not available
on X's Free API tier, so fetch_posts and community discovery return empty; they
would require a paid Basic/Pro plan and can be filled in later.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost

AUTHORIZE = "https://twitter.com/i/oauth2/authorize"
TOKEN = "https://api.twitter.com/2/oauth2/token"
API = "https://api.twitter.com/2"
SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]
CHAR_LIMIT = 280

# X's OAuth2 requires PKCE, and connect/callback are two separate stateless
# requests, so the code_verifier generated at connect time is stashed here keyed
# by the OAuth `state` and read back during the token exchange. Single-process
# on Render; entries are short-lived and cleaned opportunistically.
_VERIFIERS: dict[str, tuple[str, float]] = {}
_VERIFIER_TTL = 600  # seconds


def _basic_auth() -> str:
    raw = f"{settings.X_CLIENT_ID}:{settings.X_CLIENT_SECRET}".encode()
    return base64.b64encode(raw).decode()


def _store_verifier(state: str, verifier: str) -> None:
    now = time.time()
    for k, (_, ts) in list(_VERIFIERS.items()):
        if now - ts > _VERIFIER_TTL:
            _VERIFIERS.pop(k, None)
    _VERIFIERS[state] = (verifier, now)


class XConnector(BaseConnector):
    platform = "x"

    def get_auth_url(self, state: str) -> str:
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        _store_verifier(state, verifier)
        params = {
            "response_type": "code",
            "client_id": settings.X_CLIENT_ID,
            "redirect_uri": settings.X_REDIRECT_URI,
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZE}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        verifier = (_VERIFIERS.pop(state, (None, 0))[0])
        if not verifier:
            raise ValueError("X login expired or was retried — please connect again.")
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.post(
                TOKEN,
                headers={
                    "Authorization": f"Basic {_basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.X_REDIRECT_URI,
                    "code_verifier": verifier,
                    "client_id": settings.X_CLIENT_ID,
                },
            )
            res.raise_for_status()
            tok = res.json()
            access_token = tok["access_token"]
            refresh_token = tok.get("refresh_token")
            expires_in = tok.get("expires_in", 7200)

            me = await http.get(
                f"{API}/users/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            me.raise_for_status()
            user = me.json().get("data", {})

        username = user.get("username", "")
        return ConnectionResult(
            account_name=f"@{username}" if username else user.get("name", "X account"),
            account_id=str(user.get("id", "")),
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            scope=" ".join(SCOPES),
            metadata={"username": username},
        )

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        if not connection.refresh_token:
            raise ValueError("No refresh token — reconnect X.")
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.post(
                TOKEN,
                headers={
                    "Authorization": f"Basic {_basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": connection.refresh_token,
                    "client_id": settings.X_CLIENT_ID,
                },
            )
            res.raise_for_status()
            tok = res.json()
        return ConnectionResult(
            account_name=connection.account_name,
            account_id=connection.account_id,
            access_token=tok["access_token"],
            refresh_token=tok.get("refresh_token") or connection.refresh_token,
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=tok.get("expires_in", 7200)),
            scope=connection.scope,
            metadata=connection.metadata,
        )

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{API}/users/me",
                    headers={"Authorization": f"Bearer {connection.access_token}"},
                )
                return res.status_code == 200
        except Exception:
            return False

    # ── Posting ─────────────────────────────────────────
    async def _post_tweet(self, connection: PlatformConnection, text: str, reply_to: str | None = None) -> dict:
        body: dict = {"text": text}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        async with httpx.AsyncClient(timeout=30) as http:
            res = await http.post(
                f"{API}/tweets",
                headers={
                    "Authorization": f"Bearer {connection.access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            _raise_x(res)
            data = res.json().get("data", {})
        tweet_id = str(data.get("id", ""))
        username = (connection.metadata or {}).get("username", "")
        url = f"https://x.com/{username}/status/{tweet_id}" if tweet_id else None
        return {"id": tweet_id, "url": url}

    async def create_post(self, connection: PlatformConnection, text: str, media=None) -> dict:
        """Publish a standalone tweet. Text only (image upload needs the v1.1
        media endpoint, which is out of scope for now)."""
        if media:
            raise ValueError(
                "X image posting isn't supported yet — post text only for now."
            )
        return await self._post_tweet(connection, text)

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Reply to a tweet. `target` needs the tweet id (as `id` or `post_id`)."""
        reply_to = target.get("id") or target.get("post_id")
        if not reply_to:
            raise ValueError("Missing X post id to reply to.")
        return await self._post_tweet(connection, text, reply_to=reply_to)

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the tweet is still retrievable."""
        tweet_id = target.get("id") or target.get("post_id")
        if not tweet_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(
                    f"{API}/tweets/{tweet_id}",
                    headers={"Authorization": f"Bearer {connection.access_token}"},
                )
                if res.status_code != 200:
                    return False
                return bool(res.json().get("data"))
        except Exception:
            return False

    # ── Discovery (needs a paid API tier — not available on Free) ──
    async def fetch_posts(
        self,
        connection: PlatformConnection,
        keywords: list[str],
        communities: list[str],
        since: datetime,
        limit: int,
    ) -> list[UniversalPost]:
        # Searching other users' posts requires X API Basic/Pro. On Free this is
        # unavailable, so return nothing rather than error out a discovery run.
        return []


def _raise_x(res: httpx.Response) -> None:
    """Raise with X's error message instead of httpx's generic text."""
    if res.is_success:
        return
    try:
        body = res.json()
        msg = body.get("detail") or body.get("title") or (
            body.get("errors", [{}])[0].get("message") if body.get("errors") else None
        ) or res.text
    except Exception:
        msg = res.text
    raise ValueError(f"X API {res.status_code}: {msg}")
