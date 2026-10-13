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
_SCRAPE_CONCURRENCY = 1  # scrape subreddits one at a time — parallel scraping
# degrades the proxy into title-only (body-less) responses, even at low maxItems.
_MAX_SUBREDDITS = 5  # subreddits scraped per discovery run (covers full list)
_SUBREDDIT_ITEMS = 15  # posts per subreddit — the actor fetches FULL post bodies
# up to ~15 items, then switches to title-only listing mode above that. Keep at
# or below 15 so every post comes back with its body/selftext.
_MAX_SEARCHES = 8  # keyword terms in the general-Reddit fallback path
_MAX_ITEMS = 15  # posts per keyword (fallback)
_SEED_KEYWORDS = 25  # keywords used to discover subreddits during seeding
_MIN_SUBREDDIT_POSTS = 5  # below this, top up from a general-Reddit keyword search
_MIN_KEYWORD_MATCHES = 2  # a subreddit must match this many DISTINCT keywords to
# be auto-activated — drops one-off broad matches (e.g. r/HeistTeams, r/psychology
# showing up for a single generic keyword).

# Generic / off-fit subreddits that match many topics loosely but aren't the
# right audience — never seed these (lowercased, matched exactly).
_SUBREDDIT_BLOCKLIST = {
    "askreddit", "askanything", "ask", "nostupidquestions", "tooafraidtoask",
    "explainlikeimfive", "askmenadvice", "askwomenadvice", "advice",
    "relationship_advice", "relationships", "cptsd", "ptsd", "mentalhealth",
    "depression", "anxiety", "offmychest", "trueoffmychest", "rant", "vent",
    "teenagers", "memes", "funny", "pics", "videos", "news", "worldnews",
    "heistteams", "therapists", "teachinguk", "prevets", "upsc", "disability",
    "spiritualawakening", "peersupportspecialist",
}


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


def _reddit_url(item: dict, post_id: str) -> str:
    """Prefer the reddit permalink (always a reddit.com path) over `url`, which
    is the external link for link-posts."""
    permalink = _first(item, "permalink", default="")
    if permalink:
        p = str(permalink)
        return p if p.startswith("http") else f"https://www.reddit.com{p}"
    return _first(item, "url", "link", default="") or f"https://reddit.com/comments/{post_id}"


def _to_post(item: dict, since: datetime) -> UniversalPost | None:
    # Skip anything that isn't a post (some actors also emit comments).
    data_type = str(_first(item, "dataType", "type", default="post")).lower()
    if data_type and data_type not in ("post", "posts", "submission"):
        return None

    created = _parse_created(_first(item, "createdAt", "created", "created_utc", "createdAtIso"))
    if created < _aware(since):
        return None

    post_id = str(_first(item, "id", "parsedId", "postId", "fullname", default=""))
    if not post_id:
        return None

    title = html.unescape(str(_first(item, "title", default="")))
    body = _clean_body(html.unescape(str(_first(item, "selftext", "body", "text", "content", default=""))))
    community = _first(item, "subreddit", "communityName", "community", default="")
    community = str(community).replace("r/", "").strip("/ ")
    author = str(_first(item, "author", "username", default="[deleted]")).replace("u/", "")
    up_votes = int(_first(item, "score", "upVotes", "ups", default=0) or 0)
    num_comments = int(_first(item, "numComments", "numberOfComments", "num_comments", default=0) or 0)
    url = _reddit_url(item, post_id)

    # For Reddit the title is often the whole point (a question), so keep both:
    # title + body reads best and gives analysis the full signal.
    content = f"{title}\n\n{body}".strip() if (title and body) else (body or title)

    return UniversalPost(
        platform="reddit",
        post_id=post_id,
        post_url=url,
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


async def _run_queries(queries: list[str], max_items: int) -> list:
    """Run the thirdwatch Reddit actor for a set of `queries` in a single run.
    A query is a subreddit listing ("r/managers"), a search within a subreddit
    ("r/managers: burnout"), or a plain-text search across Reddit ("leadership").
    One run handles many queries, returning posts with score, numComments and
    selftext. Retries once on empty/failure. Returns [] on failure."""
    queries = [q for q in queries if q]
    if not queries:
        return []
    payload = {"queries": queries, "maxItems": max_items}
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

    subreddits = [_norm_subreddit(c) for c in communities if c]

    posts: list[UniversalPost] = []
    if subreddits:
        # Primary: scrape known-relevant subreddits. thirdwatch handles many
        # subreddits in ONE run (queries=["r/sub", ...]), returning posts with
        # score, numComments and full selftext — no per-subreddit throttling.
        chosen = random.sample(subreddits, min(_MAX_SUBREDDITS, len(subreddits)))
        items = await _run_queries(
            [f"r/{s}" for s in chosen], max_items=len(chosen) * _SUBREDDIT_ITEMS
        )
        posts = _dedupe_posts(items, since, limit)
        if len(posts) >= _MIN_SUBREDDIT_POSTS:
            return posts

    # Fallback / top-up: subreddits returned too little (or none known yet) —
    # plain-text search across all of Reddit, merged and de-duplicated.
    pool = list(dict.fromkeys(k for k in keywords if k))
    if not pool:
        return posts
    searches = random.sample(pool, min(_MAX_SEARCHES, len(pool)))
    items = await _run_queries(searches, max_items=_MAX_SEARCHES * _MAX_ITEMS)
    seen = {p.post_id for p in posts}
    for p in _dedupe_posts(items, since, limit):
        if p.post_id not in seen:
            seen.add(p.post_id)
            posts.append(p)
    posts.sort(key=lambda p: p.posted_at, reverse=True)
    return posts[:limit]


async def search_subreddits_via_apify(keywords: list[str], limit: int = 12) -> list[dict]:
    """Discover subreddits relevant to the given keywords. Searches the keywords
    (one run) and counts how many DISTINCT keywords each subreddit appeared for —
    a sub that recurs across several of your topics is genuinely relevant; a
    one-off match (r/HeistTeams for a single broad keyword) is noise and gets
    dropped by the caller's threshold. Blocklisted generic subs are excluded.
    Ranked by distinct-keyword count. [] on failure or when no token is set."""
    if not settings.APIFY_TOKEN:
        return []
    pool = list(dict.fromkeys(k for k in keywords if k))[:_SEED_KEYWORDS]
    if not pool:
        return []
    # One run per keyword's worth of results, but we still need per-keyword
    # attribution — so tag each result by which query produced it via sourceQuery.
    items = await _run_queries(pool, max_items=len(pool) * 15)
    # Map results to their originating keyword using the actor's sourceQuery.
    by_kw: dict[str, set[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _norm_subreddit(str(_first(item, "subreddit", "communityName", default="")))
        if not name or name.lower() in _SUBREDDIT_BLOCKLIST:
            continue
        kw = str(item.get("sourceQuery") or "")
        by_kw.setdefault(kw, set()).add(name)
    counts: dict[str, int] = {}
    for subs in by_kw.values():
        for name in subs:
            counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {
            "community_id": name,
            "community_name": f"r/{name}",
            "member_count": 0,
            # distinct-keyword match count — how many of your topics this sub fits
            "weekly_active": hits,
            "activity_level": "high" if hits >= 4 else "medium" if hits >= 2 else "low",
        }
        for name, hits in ranked[:limit]
    ]
