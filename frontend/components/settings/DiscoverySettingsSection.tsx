"use client";

import { useEffect, useState } from "react";
import { Radar } from "lucide-react";
import { discoveryApi } from "@/lib/api";
import type { DiscoverySettings } from "@/lib/types";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import LoadingSpinner from "@/components/shared/LoadingSpinner";

export default function DiscoverySettingsSection() {
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
      const updated = await discoveryApi.updateSettings(settings);
      setSettings(updated);
      showToast("success", "Discovery settings saved.");
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
          <Radar className="h-5 w-5 text-accent-light" />
          Discovery Settings
        </h2>
        <p className="mt-1 text-sm text-text-secondary">
          Control how the automatic discovery worker fetches and submits conversations.
        </p>
      </div>

      {!settings ? (
        <div className="flex justify-center py-8">
          <LoadingSpinner size="md" />
        </div>
      ) : (
        <div className="space-y-4 rounded-xl border border-border bg-surface p-6">
          <label className="flex items-center justify-between">
            <span className="text-sm text-text-primary">Discovery Enabled</span>
            <button
              onClick={() => set("is_enabled", !settings.is_enabled)}
              className={
                "relative h-6 w-11 rounded-full transition-colors " +
                (settings.is_enabled ? "bg-accent" : "bg-surface-raised")
              }
              aria-label="Toggle discovery"
            >
              <span
                className={
                  "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform " +
                  (settings.is_enabled ? "translate-x-5" : "translate-x-0.5")
                }
              />
            </button>
          </label>

          <Input
            label="Schedule Interval (minutes)"
            type="number"
            min="1"
            value={String(settings.schedule_interval_minutes)}
            onChange={(e) => set("schedule_interval_minutes", Number(e.target.value))}
          />

          <Input
            label="Max Posts Per Run"
            type="number"
            min="1"
            value={String(settings.max_posts_per_run)}
            onChange={(e) => set("max_posts_per_run", Number(e.target.value))}
          />

          <div>
            <Input
              label="Max Conversations Per Day"
              type="number"
              min="0"
              value={String(settings.max_conversations_per_day)}
              onChange={(e) => set("max_conversations_per_day", Number(e.target.value))}
            />
            <p className="mt-1 text-xs text-text-muted">
              The system stops submitting conversations for today once this limit is reached.
            </p>
          </div>

          <div>
            <label className="text-xs text-text-secondary">
              Minimum Relevance Score: {(settings.min_relevance_score * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={settings.min_relevance_score}
              onChange={(e) => set("min_relevance_score", Number(e.target.value))}
              className="w-full accent-accent"
            />
            <p className="mt-1 text-xs text-text-muted">
              Posts below this score are fetched and stored but not submitted for analysis.
            </p>
          </div>

          <Button onClick={save} loading={saving}>
            Save Discovery Settings
          </Button>
        </div>
      )}
    </section>
  );
}
