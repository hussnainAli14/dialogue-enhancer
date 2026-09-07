"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, X, Plus } from "lucide-react";
import { discoveryApi } from "@/lib/api";
import type { DiscoveryKeyword } from "@/lib/types";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";

export default function KeywordsSection() {
  const { showToast } = useToast();
  const [keywords, setKeywords] = useState<DiscoveryKeyword[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [searchCap, setSearchCap] = useState(30);
  const [loading, setLoading] = useState(true);
  const [newKeyword, setNewKeyword] = useState("");
  const [adding, setAdding] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await discoveryApi.getKeywords();
      setKeywords(res.keywords);
      setActiveCount(res.active_count);
      setSearchCap(res.search_cap);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to load keywords");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    const kw = newKeyword.trim();
    if (!kw) return;
    setAdding(true);
    try {
      await discoveryApi.addKeyword(kw);
      setNewKeyword("");
      await load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to add keyword");
    } finally {
      setAdding(false);
    }
  };

  const toggle = async (k: DiscoveryKeyword) => {
    try {
      await discoveryApi.updateKeyword(k.id, !k.is_active);
      await load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to update keyword");
    }
  };

  const remove = async (k: DiscoveryKeyword) => {
    try {
      await discoveryApi.deleteKeyword(k.id);
      setKeywords((prev) => prev.filter((x) => x.id !== k.id));
      setActiveCount((c) => (k.is_active ? c - 1 : c));
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to delete keyword");
    }
  };

  const rescan = async () => {
    setRescanning(true);
    try {
      await discoveryApi.rescanKeywords();
      showToast("info", "Scanning your knowledge base for keywords… refresh in a moment.");
      setTimeout(load, 4000);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Rescan failed");
    } finally {
      setRescanning(false);
    }
  };

  const overCap = activeCount > searchCap;

  // Active (selected) keywords first, everything else alphabetical.
  const q = query.trim().toLowerCase();
  const sortedKeywords = [...keywords]
    .filter((k) => !q || k.keyword.toLowerCase().includes(q))
    .sort((a, b) => {
      if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
      return a.keyword.localeCompare(b.keyword);
    });

  return (
    <section id="keywords" className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">Discovery keywords</h2>
          <p className="mt-1 text-sm text-text-secondary">
            These drive what gets discovered across your connected platforms. Keywords are
            pulled from your knowledge base automatically; add or remove your own below.
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={rescan} disabled={rescanning}>
          <RefreshCw className={rescanning ? "mr-2 h-4 w-4 animate-spin" : "mr-2 h-4 w-4"} />
          Rescan
        </Button>
      </div>

      <p className="mt-3 text-xs text-text-muted">
        Searching with{" "}
        <span className={overCap ? "font-semibold text-warning" : "font-semibold text-text-primary"}>
          {Math.min(activeCount, searchCap)}
        </span>{" "}
        of {activeCount} active keywords (cap {searchCap} per run to control cost).
        {overCap && " Remove or deactivate some to change which are searched."}
      </p>

      <div className="mt-4 flex items-end gap-2">
        <div className="flex-1">
          <Input
            id="new-keyword"
            placeholder="Add a keyword, e.g. shadow work"
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") add();
            }}
          />
        </div>
        <Button onClick={add} disabled={adding || !newKeyword.trim()}>
          <Plus className="mr-1 h-4 w-4" />
          Add
        </Button>
      </div>

      {keywords.length > 0 && (
        <div className="mt-4">
          <Input
            id="keyword-search"
            placeholder="Search keywords to find and enable one…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {loading ? (
          <span className="text-sm text-text-muted">Loading…</span>
        ) : keywords.length === 0 ? (
          <span className="text-sm text-text-muted">
            No keywords yet. Upload files to your knowledge base or add one above.
          </span>
        ) : sortedKeywords.length === 0 ? (
          <span className="text-sm text-text-muted">
            No keywords match &ldquo;{query}&rdquo;.
          </span>
        ) : (
          sortedKeywords.map((k) => (
            <span
              key={k.id}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition-colors ${
                k.is_active
                  ? "border-accent/40 bg-accent/10 text-text-primary"
                  : "border-border bg-surface-raised text-text-muted line-through"
              }`}
            >
              <button
                onClick={() => toggle(k)}
                title={k.is_active ? "Deactivate (stop searching)" : "Activate"}
                className="max-w-[180px] truncate"
              >
                {k.keyword}
              </button>
              <span
                className={`rounded px-1 text-[10px] uppercase ${
                  k.source === "kb"
                    ? "bg-accent/20 text-accent-light"
                    : "bg-surface text-text-muted"
                }`}
              >
                {k.source === "kb" ? "KB" : "manual"}
              </span>
              <button
                onClick={() => remove(k)}
                title="Delete keyword"
                className="text-text-muted transition-colors hover:text-danger"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))
        )}
      </div>
    </section>
  );
}
