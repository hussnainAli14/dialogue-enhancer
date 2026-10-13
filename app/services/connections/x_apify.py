"""X (Twitter) discovery via Apify.

X's own API charges for search/read, so when `APIFY_TOKEN` is set we discover
tweets through an Apify actor instead — no X API needed. The actor keyword-
searches X and returns tweets with text, author, and engagement (likes,
retweets, replies), which feed the same scoring/ranking pipeline as every other
platform.

Posting replies to X still needs the paid X API — this module is read-only
(discovery) by design; X posting stays manual.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.config import settings
from app.services.connections.base import UniversalPost

_RUN_TIMEOUT_S = 150
_MAX_SEARCHES = 8  # keyword terms per run
_ITEMS_PER_RUN = 60


def _actor_endpoint() -> str:
    return f"https://api.apify.com/v2/acts/{settings.APIFY_X_ACTOR}/run-sync-get-dataset-items"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_created(value) -> datetime:
    """Tweets use the Twitter date format ('Tue Oct 13 14:08:50 +0000 2026');
    also accept ISO strings and unix epochs."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value)
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _first(item: dict, *keys, default=None):
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return default


def _engagement(likes: int, retweets: int, replies: int) -> float:
    """Normalise X signals into [0, 1]. Replies (active conversation) and likes
    (reach) weigh most; retweets add some. Scales tuned to typical tweet volume."""
    r = min(max(replies, 0) / 100, 1) * 0.4
    li = min(max(likes, 0) / 1000, 1) * 0.35
    rt = min(max(retweets, 0) / 200, 1) * 0.25
    return round(r + li + rt, 4)


def _to_post(item: dict, since: datetime) -> UniversalPost | None:
    created = _parse_created(_first(item, "createdAt", "created_at", "date"))
    if created < _aware(since):
        return None

    post_id = str(_first(item, "id", "id_str", "tweetId", default=""))
    url = _first(item, "url", "twitterUrl", default="")
    if not post_id and not url:
        return None
    if not post_id:
        post_id = url.rstrip("/").split("/")[-1]

    text = html.unescape(str(_first(item, "text", "fullText", "full_text", default="")))
    author = _first(item, "author", default={}) or {}
    if isinstance(author, dict):
        handle = str(_first(author, "userName", "screenName", "screen_name", "name", default=""))
        author_id = str(_first(author, "id", "id_str", default=""))
    else:
        handle = str(author)
        author_id = ""
    handle = handle.lstrip("@")

    likes = int(_first(item, "likeCount", "likes", "favoriteCount", default=0) or 0)
    retweets = int(_first(item, "retweetCount", "retweets", default=0) or 0)
    replies = int(_first(item, "replyCount", "replies", default=0) or 0)

    return UniversalPost(
        platform="x",
        post_id=post_id,
        post_url=url or f"https://x.com/i/status/{post_id}",
        author_name=handle or "[unknown]",
        author_id=author_id or handle,
        title=None,
        content=text,
        thread_content=None,
        community_name=None,
        community_id=None,
        posted_at=created,
        comment_count=replies,
        engagement_score=_engagement(likes, retweets, replies),
        raw_data={"id": post_id, "likes": likes, "retweets": retweets, "source": "apify"},
    )


async def _run_search(search_terms: list[str], max_items: int) -> list:
    """Run the X actor for a set of keyword search terms in a single run,
    sorted by Top so high-engagement tweets come first. [] on any failure."""
    terms = [t for t in search_terms if t]
    if not terms:
        return []
    payload = {
        "searchTerms": terms,
        "maxItems": max_items,
        "sort": "Top",  # highest-engagement tweets first
        "tweetLanguage": "en",
    }
    try:
        async with httpx.AsyncClient(timeout=_RUN_TIMEOUT_S + 20) as http:
            res = await http.post(
                _actor_endpoint(),
                params={"token": settings.APIFY_TOKEN, "timeout": _RUN_TIMEOUT_S},
                json=payload,
            )
            res.raise_for_status()
            items = res.json()
    except Exception:
        return []
    return items if isinstance(items, list) else []


async def fetch_x_via_apify(
    keywords: list[str],
    communities: list[str],
    since: datetime,
    limit: int,
) -> list[UniversalPost]:
    """Discover tweets for the given keywords via Apify (keyword search, Top
    sort). Returns normalised UniversalPosts with engagement. [] on failure or
    when no token is set."""
    if not settings.APIFY_TOKEN:
        return []
    import random

    pool = list(dict.fromkeys(k for k in keywords if k))
    if not pool:
        return []
    terms = random.sample(pool, min(_MAX_SEARCHES, len(pool)))
    items = await _run_search(terms, min(limit, _ITEMS_PER_RUN))

    posts: list[UniversalPost] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        # Skip retweets — we want original posts to engage with.
        if _first(item, "isRetweet", default=False):
            continue
        post = _to_post(item, since)
        if post is None or post.post_id in seen:
            continue
        seen.add(post.post_id)
        posts.append(post)
    posts.sort(key=lambda p: p.engagement_score, reverse=True)
    return posts[:limit]
