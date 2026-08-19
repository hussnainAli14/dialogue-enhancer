"use client";

import { useEffect, useMemo, useState } from "react";
import { Users } from "lucide-react";
import AddCommunityForm from "@/components/community/AddCommunityForm";
import CommunityList, { Community } from "@/components/community/CommunityList";
import PlatformFilter from "@/components/community/PlatformFilter";
import EmptyState from "@/components/shared/EmptyState";
import { useToast } from "@/hooks/useToast";

const STORAGE_KEY = "dialogue-enhancer-communities";

export default function CommunityPage() {
  const { showToast } = useToast();
  const [communities, setCommunities] = useState<Community[]>([]);
  const [platformFilter, setPlatformFilter] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setCommunities(JSON.parse(stored));
    } catch {
      /* corrupt storage — start fresh */
    }
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (loaded) localStorage.setItem(STORAGE_KEY, JSON.stringify(communities));
  }, [communities, loaded]);

  const filtered = useMemo(
    () =>
      platformFilter
        ? communities.filter((c) => c.platform === platformFilter)
        : communities,
    [communities, platformFilter]
  );

  return (
    <div className="space-y-6">
      <p className="rounded-xl border border-border bg-surface p-4 text-sm text-text-secondary">
        Automatic community discovery and joining is a future module. For now,
        keep a working list of the communities and keywords you want the system
        to monitor. This list is stored locally in your browser.
      </p>

      <AddCommunityForm
        onAdd={(c) => {
          setCommunities((prev) => [
            ...prev,
            { ...c, id: String(Date.now()) },
          ]);
          showToast("success", "Community added.");
        }}
      />

      <PlatformFilter active={platformFilter} onChange={setPlatformFilter} />

      {filtered.length === 0 ? (
        <EmptyState
          icon={<Users className="h-12 w-12" />}
          title="No communities yet"
          description="Add the communities, subreddits, and groups you want to monitor."
        />
      ) : (
        <CommunityList
          communities={filtered}
          onRemove={(id) => {
            setCommunities((prev) => prev.filter((c) => c.id !== id));
            showToast("info", "Community removed.");
          }}
        />
      )}
    </div>
  );
}
