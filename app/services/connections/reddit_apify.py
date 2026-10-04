"""Reddit-via-Apify fetch backend.

Reddit's own Data API is approval-gated (and often never granted), so when an
`APIFY_TOKEN` is configured we scrape Reddit through an Apify actor instead.
This needs no Reddit OAuth connection: it runs the actor synchronously with the
active discovery keywords and maps the returned posts into UniversalPost.

Posting replies to Reddit still needs the official API — this module is
read-only (discovery) by design.
"""

from __future__ import annotations

import asyncio
import html
import random
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services.connections.base import UniversalPost

# Each actor run scrapes ONE search term / subreddit — fast (~60-90s). On a paid
# Apify plan (Starter allows 32 concurrent runs) we fan these out in parallel and
# merge, so one discovery run can cover many subreddits/keywords quickly. Runs
# are bounded by a semaphore to stay within the plan's concurrency limit.
_RUN_TIMEOUT_S = 150  # per single-term run-sync wait
_CONCURRENCY = 6  # parallel actor runs — higher (e.g. 12) overruns the actor's
# effective concurrent capacity and every run times out; 6 is reliable.
_SCRAPE_CONCURRENCY = 1  # subreddit scraping runs sequentially — ANY parallelism
# degrades the proxy into returning title-only posts (no body/selftext). Each
# isolated call reliably returns full post bodies. Slower, but complete.
_MAX_SUBREDDITS = 10  # subreddits scraped per discovery run (covers the full
# active list; scraped sequentially so a run takes ~10-12 min)
_SUBREDDIT_ITEMS = 30  # posts per subreddit
_MAX_SEARCHES = 8  # keyword terms in the general-Reddit fallback path
_MAX_ITEMS = 15  # posts per keyword (fallback)
_SEED_KEYWORDS = 25  # keywords used to discover subreddits during seeding
_MIN_SUBREDDIT_POSTS = 5  # below this, top up from a general-Reddit keyword search


def _actor_endpoint() -> str:
    actor = settings.APIFY_REDDIT_ACTOR
    return f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"


def _lookback_window(since: datetime) -> str:
    """Map the discovery lookback to the actor's coarse `time` filter."""
    hours = (datetime.now(timezone.utc) - _aware(since)).total_seconds() / 3600
    if hours <= 24:
        return "day"
    if hours <= 24 * 7:
        return "week"
    if hours <= 24 * 31:
        return "month"
    return "year"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_created(value) -> datetime:
    """Actors return createdAt as ISO string or a unix epoch — accept both."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _first(item: dict, *keys, default=None):
    """Return the first present, non-empty value across candidate field names
    (actors differ: upVotes vs score, communityName vs subreddit, etc.)."""
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return default


def _clean_body(body: str) -> str:
    """Link posts have no selftext — the actor fills `body` with RSS boilerplate
    like 'submitted by /u/x [link] [comments]'. Treat that as empty."""
    stripped = body.strip()
    low = stripped.lower()
    if "submitted by" in low and "[link]" in low and "[comments]" in low:
        return ""
    return stripped


def _engagement(up_votes: int, num_comments: int) -> float:
    """Normalise Reddit signals into [0, 1] — same shape as the PRAW path.
    Comments weighted heavier than upvotes as a conversation signal."""
    up = min(max(up_votes, 0) / 500, 1) * 0.4
    comments = min(max(num_comments, 0) / 100, 1) * 0.6
    return round(up + comments, 4)


def _to_post(item: dict, since: datetime) -> UniversalPost | None:
    # Skip anything that isn't a post (some actors also emit comments).
    data_type = str(_first(item, "dataType", "type", default="post")).lower()
    if data_type and data_type not in ("post", "posts", "submission"):
        return None

    created = _parse_created(_first(item, "createdAt", "created", "created_utc"))
    if created < _aware(since):
        return None

    post_id = str(_first(item, "id", "parsedId", "postId", default=""))
    url = _first(item, "url", "link", "permalink", default="")
    if not post_id and not url:
        return None
    if not post_id:
        post_id = url.rstrip("/").split("/")[-1]

    title = html.unescape(str(_first(item, "title", default="")))
    body = _clean_body(html.unescape(str(_first(item, "body", "text", "selftext", "content", default=""))))
    community = _first(item, "communityName", "subreddit", "community", default="")
    community = str(community).replace("r/", "").strip("/ ")
    author = str(_first(item, "username", "author", default="[deleted]")).replace("u/", "")
    up_votes = int(_first(item, "upVotes", "score", "ups", default=0) or 0)
    num_comments = int(_first(item, "numberOfComments", "numComments", "num_comments", default=0) or 0)

    # For Reddit the title is often the whole point (a question), so keep both:
    # title + body reads best and gives analysis the full signal.
    content = f"{title}\n\n{body}".strip() if (title and body) else (body or title)

    return UniversalPost(
        platform="reddit",
        post_id=post_id,
        post_url=url or f"https://reddit.com/comments/{post_id}",
        author_name=author,
        author_id=author,
        title=title or None,
        content=content,
        thread_content=None,
        community_name=f"r/{community}" if community else None,
        community_id=community or None,
        posted_at=created,
        comment_count=num_comments,
        engagement_score=_engagement(up_votes, num_comments),
        raw_data={"id": post_id, "upVotes": up_votes, "source": "apify"},
    )


def _norm_subreddit(name: str) -> str:
    return name.replace("r/", "").strip("/ ")


async def _run_actor(payload: dict) -> list:
    """POST a single actor run and return dataset items ([] on failure). Retries
    once on an empty/failed result — the Apify proxy against Reddit intermittently
    times out or returns nothing, and a second attempt usually succeeds."""
    payload = {"skipComments": True, "proxy": {"useApifyProxy": True}, **payload}
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=_RUN_TIMEOUT_S + 20) as http:
                res = await http.post(
                    _actor_endpoint(),
                    params={"token": settings.APIFY_TOKEN, "timeout": _RUN_TIMEOUT_S},
                    json=payload,
                )
                res.raise_for_status()
                items = res.json()
            if isinstance(items, list) and items:
                return items
        except Exception:
            pass
        if attempt == 0:
            await asyncio.sleep(3)
    return []


async def _run_many(payloads: list[dict]) -> list:
    """Run several actor runs in parallel (bounded by _CONCURRENCY) and return
    all dataset items flattened. Failures are skipped."""
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _one(p: dict) -> list:
        async with sem:
            return await _run_actor(p)

    results = await asyncio.gather(*[_one(p) for p in payloads], return_exceptions=True)
    items: list = []
    for res in results:
        if isinstance(res, list):
            items.extend(res)
    return items


async def _scrape_subreddit(sub: str) -> list:
    """Scrape one subreddit's recent posts in a SINGLE request. Isolated single
    calls reliably return full post bodies; firing retries/bursts instead makes
    the Apify proxy throttle and return title-only listings — so we deliberately
    do one call per subreddit and keep the overall rate low (sequential + a gap
    between subreddits in the caller).

    Uses /new (recent) not /top (all-time) — top never changes, so every run
    would re-fetch the same posts and drop them all as duplicates. No "time"
    filter either: it returns nothing combined with "new" sorting, and the
    pipeline's since-filter (_to_post) already drops anything too old."""
    return await _run_actor(
        {
            "type": "posts",
            "startUrls": [{"url": f"https://www.reddit.com/r/{sub}/new/"}],
            "sort": "new",
            "maxItems": _SUBREDDIT_ITEMS,
            "maxPostCount": _SUBREDDIT_ITEMS,
        }
    )


def _dedupe_posts(items: list, since: datetime, limit: int) -> list[UniversalPost]:
    posts: list[UniversalPost] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        post = _to_post(item, since)
        if post is None or post.post_id in seen:
            continue
        seen.add(post.post_id)
        posts.append(post)
    posts.sort(key=lambda p: p.posted_at, reverse=True)
    return posts[:limit]


async def fetch_reddit_via_apify(
    keywords: list[str],
    communities: list[str],
    since: datetime,
    limit: int,
) -> list[UniversalPost]:
    """Fetch Reddit posts for discovery. Primary path scrapes on-topic
    subreddits (`communities`) — everything there is already relevant, so it
    clears the relevance floor far more often. Falls back to keyword search
    across all of Reddit only when no subreddits are known yet (bootstrap)."""
    if not settings.APIFY_TOKEN:
        return []

    window = _lookback_window(since)
    subreddits = [_norm_subreddit(c) for c in communities if c]

    posts: list[UniversalPost] = []
    if subreddits:
        # Primary: scrape known-relevant subreddits (gentle concurrency + a
        # body-aware retry so posts come back with their full text, not just the
        # title). Sample so runs rotate across the full set when there are many.
        chosen = random.sample(subreddits, min(_MAX_SUBREDDITS, len(subreddits)))
        sem = asyncio.Semaphore(_SCRAPE_CONCURRENCY)

        async def _one(s: str) -> list:
            async with sem:
                return await _scrape_subreddit(s)

        results = await asyncio.gather(*[_one(s) for s in chosen], return_exceptions=True)
        items: list = []
        for res in results:
            if isinstance(res, list):
                items.extend(res)
        posts = _dedupe_posts(items, since, limit)
        if len(posts) >= _MIN_SUBREDDIT_POSTS:
            return posts

    # Fallback / top-up: subreddits returned too little (or none known yet) —
    # search across all of Reddit by keyword in parallel (relevance sort beats
    # "new" for match quality) and merge, de-duplicating against what we have.
    pool = list(dict.fromkeys(k for k in keywords if k))
    if not pool:
        return posts
    searches = random.sample(pool, min(_MAX_SEARCHES, len(pool)))
    items = await _run_many(
        [
            {
                "type": "posts",
                "searches": [s],
                "sort": "relevance",
                "time": window,
                "maxItems": _MAX_ITEMS,
                "maxPostCount": _MAX_ITEMS,
            }
            for s in searches
        ]
    )
    seen = {p.post_id for p in posts}
    for p in _dedupe_posts(items, since, limit):
        if p.post_id not in seen:
            seen.add(p.post_id)
            posts.append(p)
    posts.sort(key=lambda p: p.posted_at, reverse=True)
    return posts[:limit]


async def search_subreddits_via_apify(keywords: list[str], limit: int = 12) -> list[dict]:
    """Discover subreddits relevant to the given keywords. The actor has no
    subreddit-search mode, so we keyword-search posts and tally which subreddits
    they come from — the subreddits that recur most for these keywords are the
    on-topic ones. Returns community dicts ranked by hit count, most relevant
    first. [] on failure or when no token is set."""
    if not settings.APIFY_TOKEN:
        return []
    pool = list(dict.fromkeys(k for k in keywords if k))[:_SEED_KEYWORDS]
    if not pool:
        return []
    # Search every keyword in parallel and tally which subreddits their posts
    # come from — the subreddits that recur across many keywords are the most
    # on-topic. Far better coverage than a single keyword.
    items = await _run_many(
        [
            {
                "type": "posts",
                "searches": [k],
                "sort": "relevance",
                "time": "month",
                "maxItems": 25,
                "maxPostCount": 25,
            }
            for k in pool
        ]
    )
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(_first(item, "dataType", "type", default="post")).lower() != "post":
            continue
        name = _norm_subreddit(str(_first(item, "communityName", "subreddit", default="")))
        if name:
            counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {
            "community_id": name,
            "community_name": f"r/{name}",
            "member_count": 0,
            "weekly_active": hits,  # hit count stands in for relevance/activity
            "activity_level": "high" if hits >= 4 else "medium" if hits >= 2 else "low",
        }
        for name, hits in ranked[:limit]
    ]
