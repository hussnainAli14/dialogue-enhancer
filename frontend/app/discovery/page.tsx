"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Radar } from "lucide-react";
import { discoveryApi } from "@/lib/api";
import type {
  DiscoveredPost,
  DiscoveryRun,
  DiscoveryStatus,
  MonitoredCommunity,
} from "@/lib/types";
import { PLATFORM_BADGE_CLASSES, PLATFORM_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Select from "@/components/shared/Select";
import Modal from "@/components/shared/Modal";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import EmptyState from "@/components/shared/EmptyState";

const TABS = ["Overview", "Posts", "Communities", "Run History"] as const;
type Tab = (typeof TABS)[number];

const RUN_STATUS_STYLES: Record<string, string> = {
  running: "bg-warning/20 text-warning",
  completed: "bg-success/20 text-success",
  failed: "bg-danger/20 text-danger",
  partial: "bg-info/20 text-info",
};

function scoreColor(score: number | null): string {
  if (score === null) return "bg-text-muted/20 text-text-muted";
  if (score >= 0.8) return "bg-success/20 text-success";
  if (score >= 0.65) return "bg-warning/20 text-warning";
  return "bg-danger/20 text-danger";
}

const POST_STATUS_STYLES: Record<string, string> = {
  fetched: "bg-text-muted/20 text-text-muted",
  scored: "bg-info/20 text-info",
  submitted: "bg-success/20 text-success",
  filtered_out: "bg-text-muted/20 text-text-muted",
  duplicate: "bg-text-muted/20 text-text-muted",
  error: "bg-danger/20 text-danger",
};

export default function DiscoveryPage() {
  const [tab, setTab] = useState<Tab>("Overview");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm transition-colors border-b-2 -mb-px",
              tab === t
                ? "border-accent text-accent-light"
                : "border-transparent text-text-secondary hover:text-text-primary"
            )}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Overview" && <OverviewTab />}
      {tab === "Posts" && <PostsTab />}
      {tab === "Communities" && <CommunitiesTab />}
      {tab === "Run History" && <RunHistoryTab />}
    </div>
  );
}

// ── Overview ──────────────────────────────────────────
function OverviewTab() {
  const { showToast } = useToast();
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [runs, setRuns] = useState<DiscoveryRun[]>([]);
  const [triggering, setTriggering] = useState(false);
  const [runningRun, setRunningRun] = useState<DiscoveryRun | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Poll an in-progress run until it finishes, showing live counts.
  const pollRun = useCallback(
    async (id: string) => {
      try {
        const { run } = await discoveryApi.getRun(id);
        setRunningRun(run);
        if (run.status === "running") {
          pollRef.current = setTimeout(() => pollRun(id), 3000);
        } else {
          setRunningRun(null);
          showToast(
            run.status === "completed" ? "success" : "error",
            `Discovery ${run.status}: fetched ${run.posts_fetched}, submitted ${run.posts_submitted}.`
          );
          load();
        }
      } catch {
        pollRef.current = setTimeout(() => pollRun(id), 4000);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [showToast]
  );

  useEffect(() => () => {
    if (pollRef.current) clearTimeout(pollRef.current);
  }, []);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        discoveryApi.getStatus(),
        discoveryApi.getRuns({ page: 1 }),
      ]);
      setStatus(s);
      setRuns(r.runs.slice(0, 5));
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const runNow = async () => {
    setTriggering(true);
    try {
      const res = await discoveryApi.trigger();
      if (res.run_id) {
        setRunningRun({
          id: res.run_id,
          trigger_type: "manual",
          status: "running",
          platforms_checked: null,
          posts_fetched: 0,
          posts_scored: 0,
          posts_submitted: 0,
          posts_filtered: 0,
          posts_duplicated: 0,
          error_message: null,
          started_at: new Date().toISOString(),
          completed_at: null,
          duration_seconds: null,
        });
        pollRun(res.run_id);
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  const toggleEnabled = async () => {
    if (!status) return;
    try {
      const updated = await discoveryApi.updateSettings({ is_enabled: !status.is_enabled });
      setStatus({ ...status, is_enabled: updated.is_enabled });
      showToast("success", updated.is_enabled ? "Discovery enabled." : "Discovery paused.");
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Update failed");
    }
  };

  if (!status) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={runNow} loading={triggering || !!runningRun} disabled={!!runningRun}>
          {runningRun ? "Discovery running…" : "Run Discovery Now"}
        </Button>
        <Button
          variant={status.is_enabled ? "ghost" : "secondary"}
          onClick={toggleEnabled}
          disabled={!!runningRun}
        >
          {status.is_enabled ? "Pause Discovery" : "Enable Discovery"}
        </Button>
      </div>

      {runningRun && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-accent/40 bg-accent/10 p-4">
          <LoadingSpinner size="sm" />
          <span className="text-sm font-medium text-accent-light">
            Discovery running…
          </span>
          <span className="text-sm text-text-secondary">
            fetched {runningRun.posts_fetched} · scored {runningRun.posts_scored} · submitted{" "}
            {runningRun.posts_submitted} · filtered {runningRun.posts_filtered}
          </span>
          <span className="ml-auto text-xs text-text-muted">
            Fetching &amp; scoring can take a little while — this updates live.
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Scheduler" value={status.scheduler_running ? "Running" : "Stopped"} />
        <Stat label="Status" value={status.is_enabled ? "Enabled" : "Paused"} />
        <Stat label="Submitted today" value={`${status.today_submitted} / ${status.today_limit}`} />
        <Stat label="Communities" value={String(status.monitored_communities)} />
        <Stat label="Interval" value={`${status.schedule_interval_minutes} min`} />
        <Stat
          label="Next run"
          value={status.next_run_at ? new Date(status.next_run_at).toLocaleTimeString() : "—"}
        />
        <Stat label="Connected" value={String(status.connected_platforms.length)} />
        <Stat
          label="Last run"
          value={status.last_run ? status.last_run.status : "—"}
        />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-text-primary">Recent runs</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-text-muted">No runs yet.</p>
        ) : (
          <ul className="space-y-2">
            {runs.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-surface p-4 text-sm"
              >
                <span className={cn("rounded px-2 py-0.5 text-xs capitalize", RUN_STATUS_STYLES[r.status])}>
                  {r.status}
                </span>
                <span className="text-text-muted capitalize">{r.trigger_type}</span>
                <span className="text-text-secondary">
                  fetched {r.posts_fetched} · scored {r.posts_scored} · submitted {r.posts_submitted} · filtered {r.posts_filtered} · dupes {r.posts_duplicated}
                </span>
                <span className="ml-auto text-xs text-text-muted">
                  {r.duration_seconds ? `${r.duration_seconds}s · ` : ""}
                  {new Date(r.started_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="mt-1 text-lg font-medium text-text-primary">{value}</p>
    </div>
  );
}

// ── Posts ─────────────────────────────────────────────
function PostsTab() {
  const { showToast } = useToast();
  const [posts, setPosts] = useState<DiscoveredPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [platform, setPlatform] = useState("");
  const [status, setStatus] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await discoveryApi.getPosts({
        platform: platform || undefined,
        status: status || undefined,
        min_relevance_score: minScore || undefined,
        page,
      });
      setPosts(res.posts);
      setTotal(res.total);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [platform, status, minScore, page]);

  useEffect(() => {
    load();
  }, [load]);

  const submitAnyway = async (id: string) => {
    setBusy(id);
    try {
      await discoveryApi.submitPost(id);
      showToast("success", "Submitted for analysis.");
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Select
          value={platform}
          onChange={(e) => { setPlatform(e.target.value); setPage(1); }}
          placeholder="All platforms"
          options={["reddit", "bluesky", "mastodon", "discord", "telegram", "threads", "youtube"].map(
            (p) => ({ value: p, label: PLATFORM_LABELS[p] })
          )}
        />
        <Select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          placeholder="All statuses"
          options={["fetched", "scored", "submitted", "filtered_out", "duplicate", "error"].map(
            (s) => ({ value: s, label: s })
          )}
        />
        <div>
          <label className="text-xs text-text-secondary">Min score: {(minScore * 100).toFixed(0)}%</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            onChange={(e) => { setMinScore(Number(e.target.value)); setPage(1); }}
            className="w-full accent-accent"
          />
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
      ) : posts.length === 0 ? (
        <EmptyState icon={<Radar className="h-12 w-12" />} title="No discovered posts" description="Run discovery or adjust filters." />
      ) : (
        <div className="space-y-3">
          {posts.map((p) => (
            <div key={p.id} className="rounded-xl border border-border bg-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={cn("rounded px-2 py-0.5 text-xs", PLATFORM_BADGE_CLASSES[p.platform])}>
                  {PLATFORM_LABELS[p.platform] ?? p.platform}
                </span>
                {p.community_name && (
                  <span className="text-xs text-text-muted">{p.community_name}</span>
                )}
                {p.analysis_score != null ? (
                  <span
                    className={cn("rounded px-2 py-0.5 text-xs", scoreColor(p.analysis_score))}
                    title="Full AI analysis relevance"
                  >
                    {(p.analysis_score * 100).toFixed(0)}% analysis
                  </span>
                ) : (
                  <span
                    className={cn("rounded px-2 py-0.5 text-xs", scoreColor(p.relevance_score))}
                    title={p.relevance_reasoning ?? "Discovery pre-screen score"}
                  >
                    {p.relevance_score !== null
                      ? `${(p.relevance_score * 100).toFixed(0)}% screen`
                      : "unscored"}
                  </span>
                )}
                <span className={cn("rounded px-2 py-0.5 text-xs", POST_STATUS_STYLES[p.status])}>
                  {p.status}
                </span>
                <div className="ml-auto flex gap-2">
                  {p.status === "submitted" && p.conversation_id && (
                    <Link href={`/conversations/${p.conversation_id}`}>
                      <Button size="sm" variant="ghost">View Conversation</Button>
                    </Link>
                  )}
                  {p.status !== "submitted" && (
                    <Button size="sm" variant="secondary" loading={busy === p.id} onClick={() => submitAnyway(p.id)}>
                      Submit Anyway
                    </Button>
                  )}
                </div>
              </div>
              <p className="mt-2 text-sm text-text-primary">{p.content.slice(0, 150)}{p.content.length > 150 ? "…" : ""}</p>
              {p.relevance_reasoning && (
                <p className="mt-1 text-xs italic text-text-secondary">{p.relevance_reasoning}</p>
              )}
            </div>
          ))}
          <Pagination page={page} totalPages={totalPages} onPage={setPage} />
        </div>
      )}
    </div>
  );
}

// ── Communities ───────────────────────────────────────
function CommunitiesTab() {
  const { showToast } = useToast();
  const [grouped, setGrouped] = useState<Record<string, MonitoredCommunity[]>>({});
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  // add form
  const [fPlatform, setFPlatform] = useState("reddit");
  const [fId, setFId] = useState("");
  const [fName, setFName] = useState("");
  const [fKeywords, setFKeywords] = useState("");
  const [fPriority, setFPriority] = useState(1);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await discoveryApi.getCommunities();
      setGrouped(res.communities);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setSaving(true);
    try {
      await discoveryApi.addCommunity({
        platform: fPlatform,
        community_id: fId.trim(),
        community_name: fName.trim() || fId.trim(),
        keywords: fKeywords.split(",").map((k) => k.trim()).filter(Boolean),
        priority: fPriority,
      });
      showToast("success", "Community added.");
      setAddOpen(false);
      setFId(""); setFName(""); setFKeywords(""); setFPriority(1);
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Add failed");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (c: MonitoredCommunity) => {
    try {
      await discoveryApi.updateCommunity(c.id, { is_active: !c.is_active });
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Update failed");
    }
  };

  const remove = async () => {
    if (!removeTarget) return;
    try {
      await discoveryApi.deleteCommunity(removeTarget);
      showToast("success", "Community removed.");
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Delete failed");
    } finally {
      setRemoveTarget(null);
    }
  };

  const platforms = Object.keys(grouped);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setAddOpen(true)}>Add Community</Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
      ) : platforms.length === 0 ? (
        <EmptyState icon={<Radar className="h-12 w-12" />} title="No communities" description="Add a community to start monitoring, or run the seed SQL." />
      ) : (
        platforms.map((platform) => (
          <div key={platform} className="space-y-2">
            <h3 className="text-sm font-medium text-text-primary">{PLATFORM_LABELS[platform] ?? platform}</h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {grouped[platform].map((c) => (
                <div key={c.id} className="rounded-xl border border-border bg-surface p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text-primary">{c.community_name}</span>
                    <span className="text-xs text-text-muted">P{c.priority}</span>
                  </div>
                  <p className="text-xs text-text-muted">{c.community_id}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.keywords.map((k) => (
                      <span key={k} className="rounded bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">{k}</span>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-text-muted">
                    <span>{c.fetch_count} fetches</span>
                    {c.last_fetched_at && <span>· last {new Date(c.last_fetched_at).toLocaleDateString()}</span>}
                    <div className="ml-auto flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => toggleActive(c)}>
                        {c.is_active ? "Active" : "Paused"}
                      </Button>
                      <Button size="sm" variant="ghost" className="text-danger" onClick={() => setRemoveTarget(c.id)}>
                        Remove
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Community">
        <div className="space-y-3">
          <Select
            label="Platform"
            value={fPlatform}
            onChange={(e) => setFPlatform(e.target.value)}
            options={["reddit", "bluesky", "mastodon", "discord", "telegram", "threads", "youtube"].map(
              (p) => ({ value: p, label: PLATFORM_LABELS[p] })
            )}
          />
          <Input
            label="Community ID"
            value={fId}
            onChange={(e) => setFId(e.target.value)}
            placeholder={communityHint(fPlatform)}
          />
          <Input label="Community Name" value={fName} onChange={(e) => setFName(e.target.value)} placeholder="Human-readable name" />
          <Input label="Keywords (comma separated)" value={fKeywords} onChange={(e) => setFKeywords(e.target.value)} placeholder="leadership, coaching" />
          <div>
            <label className="text-xs text-text-secondary">Priority: {fPriority}</label>
            <input type="range" min={1} max={5} value={fPriority} onChange={(e) => setFPriority(Number(e.target.value))} className="w-full accent-accent" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={add} loading={saving} disabled={!fId.trim()}>Save</Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={!!removeTarget}
        title="Remove community?"
        description="It will no longer be monitored for new posts."
        confirmLabel="Remove"
        destructive
        onConfirm={remove}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  );
}

function communityHint(platform: string): string {
  switch (platform) {
    case "reddit": return "subreddit name, e.g. leadership";
    case "bluesky": return "keyword/hashtag, e.g. leadership";
    case "mastodon": return "hashtag, e.g. leadership";
    case "discord": return "channel ID, e.g. 123456789";
    case "telegram": return "channel username, e.g. mychannel";
    case "youtube": return "search keyword, e.g. executive coaching";
    default: return "";
  }
}

// ── Run History ───────────────────────────────────────
function RunHistoryTab() {
  const [runs, setRuns] = useState<DiscoveryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [triggerFilter, setTriggerFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await discoveryApi.getRuns({
        status: statusFilter || undefined,
        trigger_type: triggerFilter || undefined,
        page,
      });
      setRuns(res.runs);
      setTotal(res.total);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [statusFilter, triggerFilter, page]);

  useEffect(() => { load(); }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:w-1/2">
        <Select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          placeholder="All statuses"
          options={["running", "completed", "failed", "partial"].map((s) => ({ value: s, label: s }))}
        />
        <Select
          value={triggerFilter}
          onChange={(e) => { setTriggerFilter(e.target.value); setPage(1); }}
          placeholder="All triggers"
          options={["scheduled", "manual", "api"].map((s) => ({ value: s, label: s }))}
        />
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
      ) : runs.length === 0 ? (
        <EmptyState icon={<Radar className="h-12 w-12" />} title="No runs" description="Discovery has not run yet." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-text-muted">
                <th className="p-3">Trigger</th><th className="p-3">Status</th>
                <th className="p-3">Fetched</th><th className="p-3">Scored</th>
                <th className="p-3">Submitted</th><th className="p-3">Filtered</th>
                <th className="p-3">Duration</th><th className="p-3">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <Fragment key={r.id}>
                  <tr
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                    className="cursor-pointer border-b border-border/50 hover:bg-surface-raised"
                  >
                    <td className="p-3 capitalize text-text-secondary">{r.trigger_type}</td>
                    <td className="p-3">
                      <span className={cn("rounded px-2 py-0.5 text-xs capitalize", RUN_STATUS_STYLES[r.status])}>{r.status}</span>
                    </td>
                    <td className="p-3">{r.posts_fetched}</td>
                    <td className="p-3">{r.posts_scored}</td>
                    <td className="p-3">{r.posts_submitted}</td>
                    <td className="p-3">{r.posts_filtered}</td>
                    <td className="p-3">{r.duration_seconds ? `${r.duration_seconds}s` : "—"}</td>
                    <td className="p-3 text-xs text-text-muted">{new Date(r.started_at).toLocaleString()}</td>
                  </tr>
                  {expanded === r.id && (
                    <tr className="border-b border-border/50 bg-background/40">
                      <td colSpan={8} className="p-3 text-xs text-text-secondary">
                        Platforms: {(r.platforms_checked || []).join(", ") || "—"} · Duplicates: {r.posts_duplicated}
                        {r.error_message && (
                          <span className={r.status === "failed" ? "text-danger" : "text-text-secondary"}>
                            {" "}· {r.status === "failed" ? "Error" : "Outcome"}: {r.error_message}
                          </span>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} totalPages={totalPages} onPage={setPage} />
    </div>
  );
}

function Pagination({ page, totalPages, onPage }: { page: number; totalPages: number; onPage: (p: number) => void }) {
  return (
    <div className="flex items-center justify-center gap-3">
      <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <span className="text-xs text-text-muted">Page {page} of {totalPages}</span>
      <Button size="sm" variant="ghost" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next</Button>
    </div>
  );
}
