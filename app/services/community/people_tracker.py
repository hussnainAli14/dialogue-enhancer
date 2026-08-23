"""People-based community discovery — find communities people are active in."""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_supabase
from app.services.community import DiscoveredCommunity
from app.services.connections.factory import get_connector


class PeopleTracker:
    async def discover(
        self, people: list[dict], connected_platforms: set[str], limit: int = 10
    ) -> list[DiscoveredCommunity]:
        results: list[DiscoveredCommunity] = []
        supabase = get_supabase()
        for person in people:
            handles = person.get("platform_handles") or {}
            for platform, handle in handles.items():
                if platform not in connected_platforms or not handle:
                    continue  # skip silently if no handle / not connected
                connector = get_connector(platform)
                try:
                    found = await connector.get_person_communities(handle, limit=limit)
                except Exception:
                    found = []
                for c in found:
                    c.discovery_method = "people_based"
                    c.discovered_via_people = [person["name"]]
                    results.append(c)
            try:
                supabase.table("monitored_people").update(
                    {"last_checked_at": datetime.now(timezone.utc).isoformat()}
                ).eq("id", person["id"]).execute()
            except Exception:
                pass
        return results
