"""Keyword-based community discovery, per platform."""

from __future__ import annotations

from app.services.community import DiscoveredCommunity
from app.services.connections.factory import get_connector


class KeywordSearcher:
    async def search_platform(
        self, platform: str, topics: list[dict], limit: int
    ) -> list[DiscoveredCommunity]:
        """Search one platform across all topics, dedup by community_id, and tag
        each result with the keywords that surfaced it."""
        connector = get_connector(platform)
        merged: dict[str, DiscoveredCommunity] = {}
        for topic in topics:
            keywords = topic.get("keywords") or []
            if not keywords:
                continue
            try:
                found = await connector.search_communities(keywords, limit=limit)
            except Exception:
                found = []
            for c in found:
                existing = merged.get(c.community_id)
                if existing:
                    existing.discovered_via_keywords = sorted(
                        set(existing.discovered_via_keywords) | set(c.discovered_via_keywords or keywords)
                    )
                else:
                    c.discovery_method = "keyword"
                    if not c.discovered_via_keywords:
                        c.discovered_via_keywords = list(keywords)
                    merged[c.community_id] = c
        return list(merged.values())
