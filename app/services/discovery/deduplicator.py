"""Deduplicates discovered posts against the discovered_posts table."""

from __future__ import annotations

from app.database import get_supabase
from app.services.connections.base import UniversalPost


class Deduplicator:
    def __init__(self):
        self.supabase = get_supabase()

    async def filter_new(self, posts: list[UniversalPost]) -> list[UniversalPost]:
        """Return only posts not already in discovered_posts. One query for the
        whole batch rather than one per post."""
        if not posts:
            return []

        # Fetch existing (platform, post_id) pairs for the post_ids in this batch.
        post_ids = list({p.post_id for p in posts})
        existing: set[tuple[str, str]] = set()
        # Chunk the IN clause to stay well within URL/row limits.
        for i in range(0, len(post_ids), 200):
            chunk = post_ids[i : i + 200]
            rows = (
                self.supabase.table("discovered_posts")
                .select("platform, post_id")
                .in_("post_id", chunk)
                .execute()
            ).data or []
            for r in rows:
                existing.add((r["platform"], r["post_id"]))

        seen_in_batch: set[tuple[str, str]] = set()
        new_posts: list[UniversalPost] = []
        for p in posts:
            key = (p.platform, p.post_id)
            if key in existing or key in seen_in_batch:
                continue
            seen_in_batch.add(key)
            new_posts.append(p)
        return new_posts

    async def is_duplicate(self, platform: str, post_id: str) -> bool:
        rows = (
            self.supabase.table("discovered_posts")
            .select("id")
            .eq("platform", platform)
            .eq("post_id", post_id)
            .limit(1)
            .execute()
        ).data
        return bool(rows)

    async def mark_duplicate(self, platform: str, post_id: str) -> None:
        self.supabase.table("discovered_posts").update({"status": "duplicate"}).eq(
            "platform", platform
        ).eq("post_id", post_id).execute()
