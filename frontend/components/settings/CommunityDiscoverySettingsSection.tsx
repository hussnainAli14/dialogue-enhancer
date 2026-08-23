"use client";

import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { discoveryApi } from "@/lib/api";
import type { DiscoverySettings } from "@/lib/types";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import LoadingSpinner from "@/components/shared/LoadingSpinner";

export default function CommunityDiscoverySettingsSection() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<DiscoverySettings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    discoveryApi.getSettings().then(setSettings).catch(() => setSettings(null));
  }, []);

  const set = <K extends keyof DiscoverySettings>(key: K, value: DiscoverySettings[K]) =>
    setSettings((s) => (s ? { ...s, [key]: value } : s));

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      const updated = await discoveryApi.updateSettings({
        community_discovery_enabled: settings.community_discovery_enabled,
        community_schedule_hours: settings.community_schedule_hours,
        max_communities_per_platform: settings.max_communities_per_platform,
        min_community_relevance_score: settings.min_community_relevance_score,
        max_community_suggestions: settings.max_community_suggestions,
      });
      setSettings(updated);
      showToast("success", "Community discovery settings saved.");
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-medium text-text-primary">
          <Users className="h-5 w-5 text-accent-light" />
          Community Discovery Settings
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Control how the system finds and suggests new communities to monitor.
        </p>
      </div>

      {!settings ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner size="md" />
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-border bg-surface p-6">
          <label className="flex items-center justify-between">
            <span className="text-sm text-text-primary">Community Discovery Enabled</span>
            <button
              onClick={() => set("community_discovery_enabled", !settings.community_discovery_enabled)}
              className={
                "relative h-6 w-11 rounded-full transition-colors " +
                (settings.community_discovery_enabled ? "bg-accent" : "bg-surface-raised")
              }
              aria-label="Toggle community discovery"
            >
              <span
                className={
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform " +
                  (settings.community_discovery_enabled ? "translate-x-5" : "translate-x-0.5")
                }
              />
            </button>
          </label>

          <Input
            label="Discovery Schedule (hours)"
            type="number"
            min="1"
            value={String(settings.community_schedule_hours ?? 24)}
            onChange={(e) => set("community_schedule_hours", Number(e.target.value))}
          />
          <Input
            label="Max Communities Per Platform"
            type="number"
            min="1"
            value={String(settings.max_communities_per_platform ?? 20)}
            onChange={(e) => set("max_communities_per_platform", Number(e.target.value))}
          />
          <div>
            <label className="text-xs text-text-secondary">
              Minimum Relevance Score: {((settings.min_community_relevance_score ?? 0.6) * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={settings.min_community_relevance_score ?? 0.6}
              onChange={(e) => set("min_community_relevance_score", Number(e.target.value))}
              className="w-full accent-accent"
            />
            <p className="mt-1 text-xs text-text-muted">
              Communities scoring below this are not added to the suggestions queue.
            </p>
          </div>
          <Input
            label="Max Suggestions Per Run"
            type="number"
            min="1"
            value={String(settings.max_community_suggestions ?? 50)}
            onChange={(e) => set("max_community_suggestions", Number(e.target.value))}
          />

          <Button onClick={save} loading={saving}>
            Save Community Discovery Settings
          </Button>
        </div>
      )}
    </section>
  );
}
