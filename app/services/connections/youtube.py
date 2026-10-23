"""YouTube connector — OAuth 2.0 via Google, YouTube Data API v3."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost
from app.services.token_store import log_event

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    # force-ssl is required to insert comments (post replies on videos).
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
QUOTA_DAILY = 10000
QUOTA_STOP_THRESHOLD = 500  # stop fetching when fewer than this many units likely remain
# YouTube search.list costs 100 units and the daily quota is only 10,000 — so at
# most ~100 searches/day across ALL runs. The per-run quota guard can't see what
# earlier runs spent, so cap how many keywords each run searches and rotate
# through them. ~5 keywords ≈ 500-700 units/run, leaving room for many runs/day.
MAX_SEARCH_KEYWORDS_PER_RUN = 5


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
    # PKCE is disabled: get_auth_url and exchange_code run as two independent,
    # stateless calls that each build a fresh Flow, so the code_verifier from the
    # auth step can't be carried to the token exchange. With PKCE on, Google would
    # reject the exchange ("execution failed").
    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, autogenerate_code_verifier=False
    )
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

    # ── Posting — comment on a video ────────────────────
    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Publish a top-level comment on a YouTube video. `target` needs the
        video id (as `id` or `post_id`). Returns {id, url}."""
        video_id = target.get("id") or target.get("post_id")
        if not video_id:
            raise ValueError("Missing YouTube video id to comment on.")

        def _work() -> dict:
            yt = self._youtube(self._credentials(connection))
            res = yt.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {"snippet": {"textOriginal": text}},
                    }
                },
            ).execute()
            comment_id = res.get("id", "")
            return {
                "id": comment_id,
                "url": f"https://youtube.com/watch?v={video_id}&lc={comment_id}",
            }

        return await asyncio.to_thread(_work)

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the YouTube video is still retrievable."""
        video_id = target.get("id") or target.get("post_id")
        if not video_id:
            return False

        def _work() -> bool:
            yt = self._youtube(self._credentials(connection))
            res = yt.videos().list(part="id", id=video_id).execute()
            return bool(res.get("items"))

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return False

    # ── Module 3 — community discovery ──────────────────
    async def search_communities(self, keywords: list[str], limit: int = 20):
        from app.services import token_store
        from app.services.community import DiscoveredCommunity

        conn = token_store.get_connection("youtube")
        if not conn or conn.status != "connected":
            return []

        def _work():
            yt = self._youtube(self._credentials(conn))
            out: list[DiscoveredCommunity] = []
            seen: set[str] = set()
            # Each channel search costs 100 of the 10,000 daily units — cap +
            # rotate so community discovery can't exhaust the shared quota.
            kws = list(dict.fromkeys(k for k in keywords if k))
            if len(kws) > MAX_SEARCH_KEYWORDS_PER_RUN:
                kws = random.sample(kws, MAX_SEARCH_KEYWORDS_PER_RUN)
            for kw in kws:
                res = yt.search().list(
                    part="snippet", q=kw, type="channel", maxResults=min(limit, 10)
                ).execute()
                for item in res.get("items", []):
                    cid = item["id"].get("channelId")
                    if not cid or cid in seen:
                        continue
                    seen.add(cid)
                    sn = item["snippet"]
                    out.append(
                        DiscoveredCommunity(
                            platform="youtube",
                            community_id=cid,
                            community_name=sn.get("channelTitle", "YouTube channel"),
                            community_url=f"https://youtube.com/channel/{cid}",
                            description=sn.get("description"),
                            activity_level="unknown",
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

        conn = token_store.get_connection("youtube")
        if not conn or conn.status != "connected":
            return []

        def _work():
            yt = self._youtube(self._credentials(conn))
            res = yt.search().list(
                part="snippet", q=handle, type="channel", maxResults=1
            ).execute()
            items = res.get("items", [])
            if not items:
                return []
            cid = items[0]["id"].get("channelId")
            sn = items[0]["snippet"]
            return [
                DiscoveredCommunity(
                    platform="youtube",
                    community_id=cid,
                    community_name=sn.get("channelTitle", handle),
                    community_url=f"https://youtube.com/channel/{cid}",
                    discovery_method="people_based",
                )
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
            yt = self._youtube(self._credentials(connection))
            self._quota_used = 0
            posts: list[UniversalPost] = []
            seen: set[str] = set()
            since_utc = since.astimezone(timezone.utc)
            published_after = since_utc.isoformat().replace("+00:00", "Z")

            # STEP 1 — recent uploads from approved channels first. Pulling a
            # channel's uploads costs ~1 unit each (vs 100 for a keyword search),
            # so this is both cheaper and exactly the content the user curated in
            # Community Manager. `communities` holds the approved channel IDs.
            channel_ids = list(dict.fromkeys(c for c in communities if c))
            if channel_ids:
                posts.extend(
                    self._videos_from_channels(yt, channel_ids, since_utc, limit, seen)
                )

            # STEP 2 — keyword search fills any remaining room. Cap + rotate the
            # keywords so a run can't exhaust the shared daily quota (each search
            # costs 100 units of only 10,000/day across all runs).
            search_keywords = list(dict.fromkeys(k for k in keywords if k))
            if len(search_keywords) > MAX_SEARCH_KEYWORDS_PER_RUN:
                search_keywords = random.sample(search_keywords, MAX_SEARCH_KEYWORDS_PER_RUN)
            for keyword in search_keywords:
                if len(posts) >= limit:
                    break
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
                    if not video_id or video_id in seen:
                        continue
                    seen.add(video_id)
                    snippet = item["snippet"]
                    posts.append(self._build_video_post(yt, video_id, snippet))
                    if len(posts) >= limit:
                        break

            log_event("youtube", "fetch_success", f"Quota used ~{self._quota_used} units.",
                      {"quota_used": self._quota_used})
            return posts

        return await asyncio.to_thread(_work)

    def _videos_from_channels(
        self, yt, channel_ids: list[str], since_utc: datetime, limit: int, seen: set[str]
    ) -> list[UniversalPost]:
        """Recent uploads from approved channels — ~1 quota unit per channel."""
        posts: list[UniversalPost] = []
        # Resolve each channel's uploads playlist (one call covers up to 50 IDs).
        uploads: dict[str, str] = {}
        try:
            for i in range(0, len(channel_ids), 50):
                chunk = channel_ids[i : i + 50]
                resp = (
                    yt.channels()
                    .list(part="contentDetails", id=",".join(chunk), maxResults=50)
                    .execute()
                )
                self._quota_used += 1
                for item in resp.get("items", []):
                    playlist = (
                        item.get("contentDetails", {})
                        .get("relatedPlaylists", {})
                        .get("uploads")
                    )
                    if playlist:
                        uploads[item["id"]] = playlist
        except Exception:
            return posts

        for playlist_id in uploads.values():
            if len(posts) >= limit or self._quota_low():
                break
            try:
                resp = (
                    yt.playlistItems()
                    .list(part="snippet", playlistId=playlist_id, maxResults=min(limit, 10))
                    .execute()
                )
                self._quota_used += 1
            except Exception:
                continue
            for item in resp.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId")
                if not video_id or video_id in seen:
                    continue
                if _parse_dt(snippet.get("publishedAt")) < since_utc:
                    continue  # older than the lookback window
                seen.add(video_id)
                # playlistItems name the uploader via videoOwnerChannel*.
                author_name = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle", "")
                author_id = snippet.get("videoOwnerChannelId") or snippet.get("channelId", "")
                posts.append(
                    self._build_video_post(yt, video_id, snippet, author_name, author_id)
                )
                if len(posts) >= limit:
                    break
        return posts

    def _build_video_post(
        self, yt, video_id: str, snippet: dict,
        author_name: str | None = None, author_id: str | None = None,
    ) -> UniversalPost:
        """Build a UniversalPost for a video, fetching stats + top comments."""
        stats, thread = self._video_details(yt, video_id)
        comment_count = int(stats.get("commentCount", 0) or 0)
        like_count = int(stats.get("likeCount", 0) or 0)
        view_count = int(stats.get("viewCount", 0) or 0)
        engagement = (
            min(comment_count / 100, 1) * 0.4
            + min(like_count / 1000, 1) * 0.3
            + min(view_count / 10000, 1) * 0.3
        )
        name = author_name if author_name is not None else snippet.get("channelTitle", "")
        cid = author_id if author_id is not None else snippet.get("channelId", "")
        return UniversalPost(
            platform="youtube",
            post_id=video_id,
            post_url=f"https://youtube.com/watch?v={video_id}",
            author_name=name,
            author_id=cid,
            title=snippet.get("title"),
            content=snippet.get("description", ""),
            thread_content=thread,
            community_name=name,
            community_id=cid,
            posted_at=_parse_dt(snippet.get("publishedAt")),
            comment_count=comment_count,
            engagement_score=round(engagement, 4),
            raw_data={"video_id": video_id},
        )

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
