"use client";

import { useEffect, useState } from "react";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import { useToast } from "@/hooks/useToast";
import ConnectionsSection from "@/components/settings/ConnectionsSection";
import DiscoverySettingsSection from "@/components/settings/DiscoverySettingsSection";
import { PLATFORM_LABELS } from "@/lib/constants";

const STORAGE_KEY = "dialogue-enhancer-settings";

interface Settings {
  relevanceThreshold: string;
  dailyLimit: string;
  keywords: string;
}

const DEFAULTS: Settings = {
  relevanceThreshold: "0.65",
  dailyLimit: "5",
  keywords: "coaching, leadership, personal growth, spirituality, community",
};

export default function SettingsPage() {
  const { showToast } = useToast();
  const [settings, setSettings] = useState<Settings>(DEFAULTS);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setSettings({ ...DEFAULTS, ...JSON.parse(stored) });
    } catch {
      /* corrupt storage — use defaults */
    }
  }, []);

  // Handle the OAuth callback redirect (?connected=1 or ?error=...&platform=...).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const platform = params.get("platform");
    if (params.get("connected")) {
      showToast(
        "success",
        `${platform ? PLATFORM_LABELS[platform] ?? platform : "Platform"} connected successfully.`
      );
    } else if (params.get("error")) {
      showToast(
        "error",
        `Connection failed${platform ? ` for ${PLATFORM_LABELS[platform] ?? platform}` : ""}: ${params.get("error")}`
      );
    }
    if (params.get("connected") || params.get("error")) {
      // Clean the URL but keep the #connections hash so the section stays in view.
      window.history.replaceState({}, "", "/settings#connections");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    showToast("success", "Settings saved.");
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <ConnectionsSection />

      <DiscoverySettingsSection />

      <div className="mx-auto max-w-xl space-y-6">
      <p className="rounded-xl border border-border bg-surface p-4 text-sm text-text-secondary">
        Backend configuration (API keys, models, thresholds) is managed via
        environment variables on the server. These preferences are stored locally
        in your browser and will move to the backend in a future build.
      </p>

      <div className="rounded-xl border border-border bg-surface p-6 space-y-4">
        <Input
          id="threshold"
          label="Relevance score threshold (0–1)"
          type="number"
          min="0"
          max="1"
          step="0.05"
          value={settings.relevanceThreshold}
          onChange={(e) =>
            setSettings((s) => ({ ...s, relevanceThreshold: e.target.value }))
          }
        />
        <Input
          id="daily-limit"
          label="Max conversations surfaced per day"
          type="number"
          min="1"
          max="20"
          value={settings.dailyLimit}
          onChange={(e) => setSettings((s) => ({ ...s, dailyLimit: e.target.value }))}
        />
        <Input
          id="keywords"
          label="Topic keywords"
          value={settings.keywords}
          onChange={(e) => setSettings((s) => ({ ...s, keywords: e.target.value }))}
        />
        <Button onClick={save}>Save Settings</Button>
      </div>
      </div>
    </div>
  );
}
