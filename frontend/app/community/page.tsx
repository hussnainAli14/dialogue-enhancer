"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { communityApi } from "@/lib/api";
import type {
  CommunityDiscoveryRun,
  CommunitySuggestion,
  DiscoveryTopic,
  MonitoredCommunity,
  MonitoredPerson,
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

const PLATFORMS7 = ["reddit", "bluesky", "mastodon", "discord", "telegram", "threads", "youtube"];
const TABS = ["Suggestions", "Active Communities", "Topics", "People", "Discovery History"] as const;
type Tab = (typeof TABS)[number];

function scoreColor(s: number | null): string {
  if (s === null) return "text-text-muted";
  if (s >= 0.75) return "text-success";
  if (s >= 0.6) return "text-warning";
  return "text-danger";
}

export default function CommunityPage() {
  const [tab, setTab] = useState<Tab>("Suggestions");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-border">
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
      {tab === "Suggestions" && <SuggestionsTab />}
      {tab === "Active Communities" && <ActiveTab />}
      {tab === "Topics" && <TopicsTab />}
      {tab === "People" && <PeopleTab />}
      {tab === "Discovery History" && <HistoryTab />}
    </div>
  );
}

// ── Suggestions ───────────────────────────────────────
function SuggestionsTab() {
  const { showToast } = useToast();
  const [suggestions, setSuggestions] = useState<CommunitySuggestion[]>([]);
  const [counts, setCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [keywordEdits, setKeywordEdits] = useState<Record<string, string[]>>({});
  const [approveThreshold, setApproveThreshold] = useState(0.75);
  const [rejectThreshold, setRejectThreshold] = useState(0.6);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await communityApi.getSuggestions({ status: "pending" });
      setSuggestions(res.suggestions);
      setCounts(res.counts);
      const edits: Record<string, string[]> = {};
      res.suggestions.forEach((s) => (edits[s.id] = s.suggested_keywords || []));
      setKeywordEdits(edits);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runDiscovery = async () => {
    setRunning(true);
    try {
      await communityApi.discover({});
      showToast("success", "Community discovery started. Suggestions appear here when it finishes.");
      setTimeout(load, 3000);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to run discovery");
    } finally {
      setRunning(false);
    }
  };

  const approve = async (s: CommunitySuggestion) => {
    setBusy(s.id);
    try {
      await communityApi.approveSuggestion(s.id, keywordEdits[s.id]);
      showToast("success", `Now monitoring ${s.community_name}.`);
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Approve failed");
    } finally {
      setBusy(null);
    }
  };

  const reject = async (s: CommunitySuggestion) => {
    setBusy(s.id);
    try {
      await communityApi.rejectSuggestion(s.id);
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy(null);
    }
  };

  const bulkApprove = async () => {
    try {
      const res = await communityApi.approveAll(approveThreshold);
      showToast("success", `Approved ${res.approved} communities.`);
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Bulk approve failed");
    }
  };

  const bulkReject = async () => {
    try {
      const res = await communityApi.rejectAll(rejectThreshold);
      showToast("info", `Rejected ${res.rejected} low-scoring suggestions.`);
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Bulk reject failed");
    }
  };

  const removeKeyword = (id: string, kw: string) =>
    setKeywordEdits((prev) => ({ ...prev, [id]: (prev[id] || []).filter((k) => k !== kw) }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        {[
          { label: "Awaiting Review", value: counts.pending },
          { label: "Approved", value: counts.approved },
          { label: "Rejected", value: counts.rejected },
        ].map((c) => (
          <div key={c.label} className="rounded-xl border border-border bg-surface px-4 py-2 text-center">
            <span className="text-lg font-semibold text-text-primary">{c.value}</span>
            <span className="ml-2 text-xs text-text-muted">{c.label}</span>
          </div>
        ))}
        <Button className="ml-auto" onClick={runDiscovery} loading={running}>
          Run Discovery Now
        </Button>
      </div>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-6 rounded-xl border border-border bg-surface p-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-text-secondary">Approve all above {(approveThreshold * 100).toFixed(0)}%</span>
            <input type="range" min={0} max={1} step={0.05} value={approveThreshold}
              onChange={(e) => setApproveThreshold(Number(e.target.value))} className="accent-accent" />
            <Button size="sm" variant="secondary" onClick={bulkApprove}>Approve</Button>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-text-secondary">Reject all below {(rejectThreshold * 100).toFixed(0)}%</span>
            <input type="range" min={0} max={1} step={0.05} value={rejectThreshold}
              onChange={(e) => setRejectThreshold(Number(e.target.value))} className="accent-accent" />
            <Button size="sm" variant="ghost" className="text-danger" onClick={bulkReject}>Reject</Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
      ) : suggestions.length === 0 ? (
        <EmptyState
          icon={<span className="text-4xl">🧭</span>}
          title="No suggestions yet"
          description="Run discovery to find communities matching your topics and the people you follow."
        />
      ) : (
        <div className="space-y-3">
          {suggestions.map((s) => (
            <div key={s.id} className="rounded-xl border border-border bg-surface p-4">
              <div className="flex items-start gap-3">
                <span className={cn("rounded px-2 py-0.5 text-xs", PLATFORM_BADGE_CLASSES[s.platform])}>
                  {PLATFORM_LABELS[s.platform] ?? s.platform}
                </span>
                <div className="min-w-0 flex-1">
                  {s.community_url ? (
                    <a href={s.community_url} target="_blank" rel="noreferrer"
                      className="text-sm font-medium text-accent-light hover:underline">
                      {s.community_name}
                    </a>
                  ) : (
                    <span className="text-sm font-medium text-text-primary">{s.community_name}</span>
                  )}
                  {s.description && (
                    <p className="text-xs text-text-secondary">{s.description.slice(0, 100)}{s.description.length > 100 ? "…" : ""}</p>
                  )}
                  <p className="mt-1 text-xs text-text-muted">
                    {s.member_count != null && `${s.member_count.toLocaleString()} members · `}
                    {s.activity_level && s.activity_level !== "unknown" && `${s.activity_level} activity · `}
                    {s.discovered_via_keywords.length > 0 && `via keywords: ${s.discovered_via_keywords.join(", ")}`}
                    {s.discovered_via_people.length > 0 && ` · via: ${s.discovered_via_people.join(", ")}`}
                  </p>
                  {s.relevance_reasoning && (
                    <p className="mt-1 text-xs italic text-text-secondary">{s.relevance_reasoning}</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(keywordEdits[s.id] || []).map((kw) => (
                      <button key={kw} onClick={() => removeKeyword(s.id, kw)}
                        className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-text-secondary hover:text-danger">
                        {kw} ✕
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span className={cn("text-xl font-semibold", scoreColor(s.relevance_score))}>
                    {s.relevance_score != null ? `${(s.relevance_score * 100).toFixed(0)}%` : "—"}
                  </span>
                  <div className="flex gap-2">
                    <Button size="sm" className="bg-success hover:bg-success/80" loading={busy === s.id}
                      onClick={() => approve(s)}>Approve</Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => reject(s)}>Reject</Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Active Communities ────────────────────────────────
function ActiveTab() {
  const { showToast } = useToast();
  const [grouped, setGrouped] = useState<Record<string, MonitoredCommunity[]>>({});
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);
  const [f, setF] = useState({ platform: "reddit", community_id: "", community_name: "", keywords: "", priority: 1 });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await communityApi.getMonitored();
      setGrouped(res.communities);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setSaving(true);
    try {
      await communityApi.addMonitored({
        platform: f.platform, community_id: f.community_id.trim(),
        community_name: f.community_name.trim() || f.community_id.trim(),
        keywords: f.keywords.split(",").map((k) => k.trim()).filter(Boolean), priority: f.priority,
      });
      showToast("success", "Community added.");
      setAddOpen(false); setF({ platform: "reddit", community_id: "", community_name: "", keywords: "", priority: 1 }); load();
    } catch (err) { showToast("error", err instanceof Error ? err.message : "Add failed"); }
    finally { setSaving(false); }
  };
  const toggle = async (c: MonitoredCommunity) => {
    try { await communityApi.updateMonitored(c.id, { is_active: !c.is_active }); load(); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Update failed"); }
  };
  const setPriority = async (c: MonitoredCommunity, p: number) => {
    try { await communityApi.updateMonitored(c.id, { priority: p }); load(); } catch { /* ignore */ }
  };
  const remove = async () => {
    if (!removeTarget) return;
    try { await communityApi.deleteMonitored(removeTarget); showToast("success", "Removed."); load(); }
    catch (err) { showToast("error", err instanceof Error ? err.message : "Delete failed"); }
    finally { setRemoveTarget(null); }
  };

  const platforms = Object.keys(grouped);
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setAddOpen(true)}>Add Manually</Button></div>
      {loading ? <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
        : platforms.length === 0 ? <EmptyState icon={<span className="text-4xl">📡</span>} title="No active communities" description="Approve suggestions or add one manually." />
        : platforms.map((platform) => (
          <div key={platform} className="space-y-2">
            <h3 className="text-sm font-medium text-text-primary">
              {PLATFORM_LABELS[platform] ?? platform} <span className="text-text-muted">({grouped[platform].length})</span>
            </h3>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {grouped[platform].map((c) => (
                <div key={c.id} className="rounded-xl border border-border bg-surface p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-text-primary">{c.community_name}</span>
                    <div className="flex gap-0.5">
                      {[1, 2, 3, 4, 5].map((p) => (
                        <button key={p} onClick={() => setPriority(c, p)}
                          className={p <= c.priority ? "text-warning" : "text-text-muted"}>★</button>
                      ))}
                    </div>
                  </div>
                  <p className="text-xs text-text-muted">{c.community_id}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.keywords.map((k) => (
                      <span key={k} className="rounded bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">{k}</span>
                    ))}
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-text-muted">
                    <span>{c.fetch_count} fetches</span>
                    {c.last_fetched_at && <span>· {new Date(c.last_fetched_at).toLocaleDateString()}</span>}
                    <div className="ml-auto flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => toggle(c)}>{c.is_active ? "Active" : "Paused"}</Button>
                      <Button size="sm" variant="ghost" className="text-danger" onClick={() => setRemoveTarget(c.id)}>Remove</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Community">
        <div className="space-y-3">
          <Select label="Platform" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}
            options={PLATFORMS7.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))} />
          <Input label="Community ID" value={f.community_id} onChange={(e) => setF({ ...f, community_id: e.target.value })} placeholder="subreddit / hashtag / channel id" />
          <Input label="Community Name" value={f.community_name} onChange={(e) => setF({ ...f, community_name: e.target.value })} />
          <Input label="Keywords (comma separated)" value={f.keywords} onChange={(e) => setF({ ...f, keywords: e.target.value })} />
          <div>
            <label className="text-xs text-text-secondary">Priority: {f.priority}</label>
            <input type="range" min={1} max={5} value={f.priority} onChange={(e) => setF({ ...f, priority: Number(e.target.value) })} className="w-full accent-accent" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={add} loading={saving} disabled={!f.community_id.trim()}>Save</Button>
          </div>
        </div>
      </Modal>
      <ConfirmDialog open={!!removeTarget} title="Remove community?" description="It will no longer be monitored."
        confirmLabel="Remove" destructive onConfirm={remove} onCancel={() => setRemoveTarget(null)} />
    </div>
  );
}

// ── Topics ────────────────────────────────────────────
function TopicsTab() {
  const { showToast } = useToast();
  const [topics, setTopics] = useState<DiscoveryTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [nt, setNt] = useState({ topic: "", keywords: "", description: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try { setTopics((await communityApi.getTopics()).topics); } catch { /* */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    try {
      await communityApi.addTopic({ topic: nt.topic.trim(), keywords: nt.keywords.split(",").map((k) => k.trim()).filter(Boolean), description: nt.description || undefined });
      setAddOpen(false); setNt({ topic: "", keywords: "", description: "" }); load();
    } catch (err) { showToast("error", err instanceof Error ? err.message : "Add failed"); }
  };
  const toggle = async (t: DiscoveryTopic) => { try { await communityApi.updateTopic(t.id, { is_active: !t.is_active }); load(); } catch { /* */ } };
  const del = async (id: string) => { try { await communityApi.deleteTopic(id); load(); } catch { /* */ } };

  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setAddOpen(true)}>Add Topic</Button></div>
      {loading ? <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
        : <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {topics.map((t) => (
            <div key={t.id} className="rounded-xl border border-border bg-surface p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-text-primary">{t.topic}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => toggle(t)}>{t.is_active ? "Active" : "Paused"}</Button>
                  <Button size="sm" variant="ghost" className="text-danger" onClick={() => del(t.id)}>Delete</Button>
                </div>
              </div>
              {t.description && <p className="text-xs text-text-secondary">{t.description}</p>}
              <div className="mt-2 flex flex-wrap gap-1">
                {t.keywords.map((k) => <span key={k} className="rounded bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">{k}</span>)}
              </div>
            </div>
          ))}
        </div>}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Topic">
        <div className="space-y-3">
          <Input label="Topic name" value={nt.topic} onChange={(e) => setNt({ ...nt, topic: e.target.value })} />
          <Input label="Keywords (comma separated)" value={nt.keywords} onChange={(e) => setNt({ ...nt, keywords: e.target.value })} />
          <Input label="Description (optional)" value={nt.description} onChange={(e) => setNt({ ...nt, description: e.target.value })} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={add} disabled={!nt.topic.trim()}>Save</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ── People ────────────────────────────────────────────
const HANDLE_HINTS: Record<string, string> = {
  reddit: "u/username", bluesky: "name.bsky.social", mastodon: "@name@instance.social",
  youtube: "@channelhandle or channel ID", threads: "username", discord: "user ID (numeric)", telegram: "@username",
};

function PeopleTab() {
  const { showToast } = useToast();
  const [people, setPeople] = useState<MonitoredPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [handles, setHandles] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try { setPeople((await communityApi.getPeople()).people); } catch { /* */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    const filled = Object.fromEntries(Object.entries(handles).filter(([, v]) => v.trim()));
    if (Object.keys(filled).length === 0) { showToast("error", "Add at least one platform handle."); return; }
    try {
      await communityApi.addPerson({ name: name.trim(), description: description || undefined, platform_handles: filled });
      setAddOpen(false); setName(""); setDescription(""); setHandles({}); load();
    } catch (err) { showToast("error", err instanceof Error ? err.message : "Add failed"); }
  };
  const toggle = async (p: MonitoredPerson) => { try { await communityApi.updatePerson(p.id, { is_active: !p.is_active }); load(); } catch { /* */ } };
  const del = async (id: string) => { try { await communityApi.deletePerson(id); load(); } catch { /* */ } };

  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setAddOpen(true)}>Add Person</Button></div>
      {loading ? <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>
        : people.length === 0 ? <EmptyState icon={<span className="text-4xl">👤</span>} title="No people yet" description="Add coaches/authors to discover the communities they're active in." />
        : <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {people.map((p) => (
            <div key={p.id} className="rounded-xl border border-border bg-surface p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-text-primary">{p.name}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => toggle(p)}>{p.is_active ? "Active" : "Paused"}</Button>
                  <Button size="sm" variant="ghost" className="text-danger" onClick={() => del(p.id)}>Delete</Button>
                </div>
              </div>
              {p.description && <p className="text-xs text-text-secondary">{p.description}</p>}
              <div className="mt-2 space-y-0.5">
                {Object.entries(p.platform_handles).map(([plat, h]) => (
                  <p key={plat} className="text-xs text-text-muted">
                    <span className="text-text-secondary">{PLATFORM_LABELS[plat] ?? plat}:</span> {h}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} title="Add Person">
        <div className="space-y-3">
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          <p className="text-xs text-text-secondary">Handles (fill at least one):</p>
          {PLATFORMS7.map((plat) => (
            <Input key={plat} label={PLATFORM_LABELS[plat] ?? plat} placeholder={HANDLE_HINTS[plat]}
              value={handles[plat] ?? ""} onChange={(e) => setHandles({ ...handles, [plat]: e.target.value })} />
          ))}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button onClick={add} disabled={!name.trim()}>Save</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

// ── Discovery History ─────────────────────────────────
function HistoryTab() {
  const [runs, setRuns] = useState<CommunityDiscoveryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    communityApi.getRuns(1).then((r) => setRuns(r.runs)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const STYLES: Record<string, string> = {
    running: "bg-warning/20 text-warning", completed: "bg-success/20 text-success",
    failed: "bg-danger/20 text-danger", partial: "bg-info/20 text-info",
  };

  if (loading) return <div className="flex justify-center py-16"><LoadingSpinner size="lg" /></div>;
  if (runs.length === 0) return <EmptyState icon={<span className="text-4xl">🕘</span>} title="No runs yet" description="Run community discovery to see history." />;

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-text-muted">
            <th className="p-3">Started</th><th className="p-3">Status</th><th className="p-3">Platforms</th>
            <th className="p-3">Found</th><th className="p-3">New</th><th className="p-3">Duration</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <Fragment key={r.id}>
              <tr onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                className="cursor-pointer border-b border-border/50 hover:bg-surface-raised">
                <td className="p-3 text-xs text-text-muted">{new Date(r.started_at).toLocaleString()}</td>
                <td className="p-3"><span className={cn("rounded px-2 py-0.5 text-xs capitalize", STYLES[r.status])}>{r.status}</span></td>
                <td className="p-3 text-text-secondary">{(r.platforms_searched || []).length}</td>
                <td className="p-3">{r.communities_found}</td>
                <td className="p-3">{r.communities_new}</td>
                <td className="p-3">{r.duration_seconds ? `${r.duration_seconds}s` : "—"}</td>
              </tr>
              {expanded === r.id && (
                <tr className="border-b border-border/50 bg-background/40">
                  <td colSpan={6} className="p-3 text-xs text-text-secondary">
                    Modes: {(r.discovery_modes || []).join(", ") || "—"} · Platforms: {(r.platforms_searched || []).join(", ") || "—"} · Already known: {r.communities_already_known}
                    {r.error_message && <span className={r.status === "failed" ? "text-danger" : "text-text-secondary"}> · {r.status === "failed" ? "Error" : "Outcome"}: {r.error_message}</span>}
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
