"""YouTube connector — OAuth 2.0 via Google, YouTube Data API v3."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost
from app.services.token_store import log_event

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
QUOTA_DAILY = 10000
QUOTA_STOP_THRESHOLD = 500  # stop fetching when fewer than this many units likely remain


def _flow():
    from google_auth_oauthlib.flow import Flow

    client_config = {
        "web": {
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "client_secret": settings.YOUTUBE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.YOUTUBE_REDIRECT_URI],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = settings.YOUTUBE_REDIRECT_URI
    return flow


class YouTubeConnector(BaseConnector):
    platform = "youtube"

    def __init__(self):
        self._quota_used = 0

    def get_auth_url(self, state: str) -> str:
        flow = _flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        def _work() -> ConnectionResult:
            flow = _flow()
            flow.fetch_token(code=code)
            creds = flow.credentials
            channel = self._youtube(creds.token).channels().list(part="snippet", mine=True).execute()
            item = (channel.get("items") or [{}])[0]
            snippet = item.get("snippet", {})
            return ConnectionResult(
                account_name=snippet.get("title", "YouTube channel"),
                account_id=item.get("id", ""),
                access_token=creds.token,
                refresh_token=creds.refresh_token,
                token_expires_at=creds.expiry.replace(tzinfo=timezone.utc)
                if creds.expiry
                else datetime.now(timezone.utc) + timedelta(hours=1),
                scope=" ".join(SCOPES),
                metadata={"channel_title": snippet.get("title")},
            )

        return await asyncio.to_thread(_work)

    def _credentials(self, connection: PlatformConnection):
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=connection.access_token,
            refresh_token=connection.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.YOUTUBE_CLIENT_ID,
            client_secret=settings.YOUTUBE_CLIENT_SECRET,
            scopes=SCOPES,
        )

    def _youtube(self, token_or_creds):
        from googleapiclient.discovery import build

        if isinstance(token_or_creds, str):
            from google.oauth2.credentials import Credentials

            creds = Credentials(token=token_or_creds, scopes=SCOPES)
        else:
            creds = token_or_creds
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        def _work() -> ConnectionResult:
            from google.auth.transport.requests import Request

            creds = self._credentials(connection)
            creds.refresh(Request())
            return ConnectionResult(
                account_name=connection.account_name,
                account_id=connection.account_id,
                access_token=creds.token,
                refresh_token=creds.refresh_token or connection.refresh_token,
                token_expires_at=creds.expiry.replace(tzinfo=timezone.utc)
                if creds.expiry
                else datetime.now(timezone.utc) + timedelta(hours=1),
                scope=connection.scope,
                metadata=connection.metadata,
            )

        return await asyncio.to_thread(_work)

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        def _work() -> bool:
            yt = self._youtube(self._credentials(connection))
            res = yt.channels().list(part="id", mine=True).execute()
            return bool(res.get("items"))

        try:
            return await asyncio.to_thread(_work)
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
        def _work() -> list[UniversalPost]:
            yt = self._youtube(self._credentials(connection))
            self._quota_used = 0
            posts: list[UniversalPost] = []
            published_after = since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            for keyword in keywords:
                if self._quota_low():
                    log_event("youtube", "fetch_failed", "Quota threshold reached — stopping.")
                    break
                search = (
                    yt.search()
                    .list(
                        part="snippet",
                        q=keyword,
                        type="video",
                        order="relevance",
                        publishedAfter=published_after,
                        maxResults=min(limit, 10),
                    )
                    .execute()
                )
                self._quota_used += 100  # search.list costs 100 units
                for item in search.get("items", []):
                    video_id = item["id"].get("videoId")
                    if not video_id:
                        continue
                    snippet = item["snippet"]
                    created = _parse_dt(snippet.get("publishedAt"))
                    stats, thread = self._video_details(yt, video_id)
                    comment_count = int(stats.get("commentCount", 0) or 0)
                    like_count = int(stats.get("likeCount", 0) or 0)
                    view_count = int(stats.get("viewCount", 0) or 0)
                    engagement = (
                        min(comment_count / 100, 1) * 0.4
                        + min(like_count / 1000, 1) * 0.3
                        + min(view_count / 10000, 1) * 0.3
                    )
                    posts.append(
                        UniversalPost(
                            platform="youtube",
                            post_id=video_id,
                            post_url=f"https://youtube.com/watch?v={video_id}",
                            author_name=snippet.get("channelTitle", ""),
                            author_id=snippet.get("channelId", ""),
                            title=snippet.get("title"),
                            content=snippet.get("description", ""),
                            thread_content=thread,
                            community_name=snippet.get("channelTitle"),
                            community_id=snippet.get("channelId"),
                            posted_at=created,
                            comment_count=comment_count,
                            engagement_score=round(engagement, 4),
                            raw_data={"video_id": video_id},
                        )
                    )
                    if len(posts) >= limit:
                        break
            log_event("youtube", "fetch_success", f"Quota used ~{self._quota_used} units.",
                      {"quota_used": self._quota_used})
            return posts

        return await asyncio.to_thread(_work)

    def _quota_low(self) -> bool:
        return (QUOTA_DAILY - self._quota_used) < QUOTA_STOP_THRESHOLD

    def _video_details(self, yt, video_id: str):
        stats = {}
        try:
            v = yt.videos().list(part="statistics", id=video_id).execute()
            self._quota_used += 1
            items = v.get("items", [])
            if items:
                stats = items[0].get("statistics", {})
        except Exception:
            pass
        thread = None
        try:
            ct = (
                yt.commentThreads()
                .list(part="snippet", videoId=video_id, order="relevance", maxResults=10)
                .execute()
            )
            self._quota_used += 1
            comments = [
                t["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
                for t in ct.get("items", [])
            ]
            thread = "\n\n".join(comments) if comments else None
        except Exception:
            pass
        return stats, thread


def _parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
