"""Reddit connector — OAuth 2.0 via PRAW (scopes: read, identity)."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from app.config import settings
from app.schemas.connections import ConnectionResult, PlatformConnection
from app.services.connections.base import BaseConnector, UniversalPost

SCOPES = ["read", "identity", "submit"]


class _RateLimiter:
    """Reddit allows ~60 requests/min. Sleep if we approach the limit."""

    def __init__(self, max_per_min: int = 55):
        self.max = max_per_min
        self.window_start = time.monotonic()
        self.count = 0

    def tick(self):
        now = time.monotonic()
        if now - self.window_start >= 60:
            self.window_start = now
            self.count = 0
        self.count += 1
        if self.count >= self.max:
            time.sleep(max(0, 60 - (now - self.window_start)))
            self.window_start = time.monotonic()
            self.count = 0


class RedditConnector(BaseConnector):
    platform = "reddit"

    def __init__(self):
        self.rate = _RateLimiter()

    def _client(self, refresh_token: str | None = None):
        import praw

        return praw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            redirect_uri=settings.REDDIT_REDIRECT_URI,
            user_agent=settings.REDDIT_USER_AGENT,
            refresh_token=refresh_token,
        )

    def get_auth_url(self, state: str) -> str:
        return self._client().auth.url(scopes=SCOPES, state=state, duration="permanent")

    async def exchange_code(self, code: str, state: str) -> ConnectionResult:
        def _work() -> ConnectionResult:
            reddit = self._client()
            refresh_token = reddit.auth.authorize(code)
            me = reddit.user.me()
            return ConnectionResult(
                account_name=f"u/{me.name}",
                account_id=str(me.id),
                access_token=refresh_token,  # PRAW manages access token from refresh
                refresh_token=refresh_token,
                token_expires_at=None,  # refresh-token flow — no fixed expiry
                scope=" ".join(SCOPES),
                metadata={"username": me.name},
            )

        return await asyncio.to_thread(_work)

    async def refresh_token(self, connection: PlatformConnection) -> ConnectionResult:
        # PRAW refreshes access tokens automatically; nothing persistent to update.
        return ConnectionResult(
            account_name=connection.account_name,
            account_id=connection.account_id,
            access_token=connection.refresh_token,
            refresh_token=connection.refresh_token,
            token_expires_at=None,
            scope=connection.scope,
            metadata=connection.metadata,
        )

    async def validate_connection(self, connection: PlatformConnection) -> bool:
        def _work() -> bool:
            reddit = self._client(refresh_token=connection.refresh_token)
            return reddit.user.me() is not None

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return False

    @staticmethod
    def _submission_id(target: dict) -> str:
        sid = target.get("id") or target.get("post_id") or target.get("uri") or ""
        # Accept a full name like "t3_abc123" or a bare base36 id.
        return sid.split("_")[-1] if sid else ""

    async def post_reply(self, connection: PlatformConnection, target: dict, text: str) -> dict:
        """Add a top-level comment to a submission."""

        def _work() -> dict:
            reddit = self._client(refresh_token=connection.refresh_token)
            reddit.read_only = False
            sub_id = self._submission_id(target)
            if not sub_id:
                raise ValueError("Missing Reddit submission id to reply to.")
            comment = reddit.submission(id=sub_id).reply(text)
            return {"id": comment.id, "url": f"https://reddit.com{comment.permalink}"}

        return await asyncio.to_thread(_work)

    async def post_exists(self, connection: PlatformConnection, target: dict) -> bool:
        """True if the submission is still available (not removed/deleted)."""

        def _work() -> bool:
            reddit = self._client(refresh_token=connection.refresh_token)
            reddit.read_only = True
            sub_id = self._submission_id(target)
            if not sub_id:
                raise ValueError("Missing Reddit submission id.")
            submission = reddit.submission(id=sub_id)
            if getattr(submission, "removed_by_category", None):
                return False
            # A deleted post has no author and a placeholder body.
            if submission.author is None and (submission.selftext or "") in ("[deleted]", "[removed]"):
                return False
            return True

        try:
            return await asyncio.to_thread(_work)
        except Exception:
            return False

    # ── Module 3 — community discovery ──────────────────
    async def search_communities(self, keywords: list[str], limit: int = 20):
        from app.services.community import DiscoveredCommunity

        def _work():
            reddit = self._client()
            reddit.read_only = True
            out: list[DiscoveredCommunity] = []
            seen: set[str] = set()
            for kw in keywords:
                self.rate.tick()
                for sub in reddit.subreddits.search(kw, limit=limit):
                    name = sub.display_name
                    if name in seen:
                        continue
                    seen.add(name)
                    active = getattr(sub, "accounts_active", None) or 0
                    level = "high" if active > 500 else "medium" if active > 50 else "low"
                    out.append(
                        DiscoveredCommunity(
                            platform="reddit",
                            community_id=name,
                            community_name=f"r/{name}",
                            community_url=f"https://reddit.com/r/{name}",
                            description=getattr(sub, "public_description", None),
                            member_count=getattr(sub, "subscribers", None),
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
        from app.services.community import DiscoveredCommunity

        def _work():
            reddit = self._client()
            reddit.read_only = True
            username = handle.lstrip("u/").strip("/ ")
            counts: dict[str, int] = {}
            for c in reddit.redditor(username).comments.new(limit=100):
                counts[c.subreddit.display_name] = counts.get(c.subreddit.display_name, 0) + 1
            top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
            return [
                DiscoveredCommunity(
                    platform="reddit",
                    community_id=name,
                    community_name=f"r/{name}",
                    community_url=f"https://reddit.com/r/{name}",
                    activity_level="unknown",
                    discovery_method="people_based",
                )
                for name, _ in top
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
            reddit = self._client(refresh_token=connection.refresh_token)
            reddit.read_only = True
            since_ts = since.timestamp()
            posts: list[UniversalPost] = []
            for community in communities:
                sub_name = community.split("r/")[-1].strip("/ ")
                self.rate.tick()
                for submission in reddit.subreddit(sub_name).new(limit=limit):
                    if submission.created_utc < since_ts:
                        continue
                    text = f"{submission.title}\n{submission.selftext or ''}"
                    if not self._matches_keywords(text, keywords):
                        continue
                    self.rate.tick()
                    submission.comments.replace_more(limit=0)
                    top_comments = [c.body for c in submission.comments[:10]]
                    thread = "\n\n".join(top_comments) if top_comments else None
                    upvote_ratio = getattr(submission, "upvote_ratio", 0.0) or 0.0
                    num_comments = getattr(submission, "num_comments", 0) or 0
                    engagement = (upvote_ratio * 0.4) + (min(num_comments / 100, 1) * 0.6)
                    posts.append(
                        UniversalPost(
                            platform="reddit",
                            post_id=submission.id,
                            post_url=f"https://reddit.com{submission.permalink}",
                            author_name=str(submission.author) if submission.author else "[deleted]",
                            author_id=str(getattr(submission.author, "id", "")) if submission.author else "",
                            title=submission.title,
                            content=submission.selftext or submission.title,
                            thread_content=thread,
                            community_name=f"r/{sub_name}",
                            community_id=sub_name,
                            posted_at=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                            comment_count=num_comments,
                            engagement_score=round(engagement, 4),
                            raw_data={"id": submission.id, "score": submission.score},
                        )
                    )
                    if len(posts) >= limit:
                        break
            return posts

        return await asyncio.to_thread(_work)
