"""Module 3 — community discovery. Shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiscoveredCommunity:
    """A community/group/hashtag/channel found on a platform."""

    platform: str
    community_id: str
    community_name: str
    community_url: str | None = None
    description: str | None = None
    member_count: int | None = None
    activity_level: str = "unknown"  # high / medium / low / unknown
    discovery_method: str = "keyword"  # keyword / people_based / both
    discovered_via_keywords: list[str] = field(default_factory=list)
    discovered_via_people: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


@dataclass
class ScoredCommunity:
    community: DiscoveredCommunity
    final_score: float = 0.0
    topic_relevance: float = 0.0
    audience_fit: float = 0.0
    discussion_quality: float = 0.0
    contribution_opportunity: float = 0.0
    reasoning: str = ""
    suggested_keywords: list[str] = field(default_factory=list)
