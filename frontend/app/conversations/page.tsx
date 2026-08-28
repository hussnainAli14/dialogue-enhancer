"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, Trash2 } from "lucide-react";
import { conversationsApi } from "@/lib/api";
import type { CleanupScan } from "@/lib/types";
import { useConversations } from "@/hooks/useConversations";
import { useToast } from "@/hooks/useToast";
import { PLATFORMS, PLATFORM_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import PlatformBadge from "@/components/feed/PlatformBadge";
import StatusBadge from "@/components/feed/StatusBadge";
import RelevanceScore from "@/components/feed/RelevanceScore";
import Button from "@/components/shared/Button";
import Input from "@/components/shared/Input";
import Select from "@/components/shared/Select";
import ConversationsSkeleton from "@/components/conversation/ConversationsSkeleton";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";
import ConfirmDialog from "@/components/shared/ConfirmDialog";

export default function ConversationsPage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [statusFilter, setStatusFilter] = useState(() =>
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("status") ?? ""
      : ""
  );
  const [platformFilter, setPlatformFilter] = useState("");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  // Bulk cleanup of conversations whose source post was deleted on the platform.
  // The scan runs as a background job, so this polls it for live progress.
  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState<{ checked: number; total: number } | null>(null);
  const [scan, setScan] = useState<CleanupScan | null>(null);
  const [removing, setRemoving] = useState(false);

  const scanDeleted = async () => {
    setScanning(true);
    setProgress({ checked: 0, total: 0 });
    try {
      const { scan_id } = await conversationsApi.startCleanupScan();

      // Poll until the job reports completed or failed.
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const state = await conversationsApi.getCleanupScan(scan_id);
        setProgress({ checked: state.checked, total: state.total });

        if (state.status === "failed") {
          throw new Error(state.error || "Scan failed");
        }
        if (state.status === "completed") {
          if (state.deleted_count === 0) {
            showToast("success", `Checked ${state.checked} posts — all still live.`);
          } else {
            setScan(state);
          }
          break;
        }
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
      setProgress(null);
    }
  };

  const confirmCleanup = async () => {
    if (!scan) return;
    setRemoving(true);
    try {
      // Applies the ids the scan already found — no second pass over the APIs.
      const res = await conversationsApi.applyCleanupScan(scan.scan_id);
      showToast("success", `Removed ${res.deleted_count} deleted post(s).`);
      refetch();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setRemoving(false);
      setScan(null);
    }
  };

  const { data, loading, error, refetch } = useConversations({
    status: statusFilter || undefined,
    platform: platformFilter || undefined,
    page,
    page_size: 20,
  });

  const filtered = useMemo(() => {
    let rows = data?.conversations ?? [];
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (c) =>
          c.post_author?.toLowerCase().includes(q) ||
          (c.central_topic ?? "").toLowerCase().includes(q) ||
          (c.original_post ?? "").toLowerCase().includes(q)
      );
    }
    if (dateFrom) rows = rows.filter((c) => c.submitted_at >= dateFrom);
    if (dateTo) rows = rows.filter((c) => c.submitted_at <= dateTo + "T23:59:59");
    return rows;
  }, [data, search, dateFrom, dateTo]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / 20)) : 1;

  // A filter change refetches while the old results are still mounted, so both
  // the first load and a refetch render the skeleton. Sizing it to the last
  // result count keeps the page height steady instead of jumping.
  const refreshing = loading && !!data;
  const skeletonRows = Math.min(data?.conversations.length || 8, 8);

  if (error && !data) {
    return (
      <ErrorState
        title="Could not load conversations"
        description={error}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-medium text-text-primary">Conversations</h1>
        <div className="group relative">
          <Button
            size="sm"
            className="border border-danger/40 bg-danger/15 text-danger hover:bg-danger/25"
            iconLeft={<Trash2 className="h-4 w-4" />}
            onClick={scanDeleted}
            loading={scanning}
          >
            {scanning
              ? progress && progress.total > 0
                ? `Checking ${progress.checked}/${progress.total}…`
                : "Starting scan…"
              : "Clean up deleted"}
          </Button>
          <span
            role="tooltip"
            className="pointer-events-none absolute right-0 top-full z-20 mt-2 hidden w-80 rounded-lg border border-border bg-surface-raised p-3 text-xs leading-relaxed text-text-secondary shadow-lg group-hover:block group-focus-within:block"
          >
            <span className="block font-medium text-text-primary">Clean up deleted</span>
            Checks every conversation on your connected platforms (Bluesky, Mastodon,
            Reddit, Discord) to see whether the <span className="text-text-primary">original
            post still exists</span> — authors sometimes delete the post you were going to
            reply to.
            <span className="mt-2 block">
              This first runs a <span className="text-text-primary">scan only</span> and shows
              you what it found. Nothing is removed until you confirm.
            </span>
            <span className="mt-2 block text-warning">
              Confirming permanently deletes those conversations and their drafts. Posts it
              cannot check are always left alone.
            </span>
          </span>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-5">
        <Select
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setPage(1);
          }}
          disabled={refreshing}
          placeholder="All platforms"
          options={PLATFORMS.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))}
        />
        <Select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          disabled={refreshing}
          placeholder="All statuses"
          options={["pending", "analysed", "skipped", "error"].map((s) => ({
            value: s,
            label: s,
          }))}
        />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search author or topic"
        />
        <Input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      </div>

      {loading ? (
        <ConversationsSkeleton rows={skeletonRows} />
      ) : (
        <>
      {filtered.length === 0 ? (
        <EmptyState
          icon={<MessageSquare className="h-12 w-12" />}
          title="No conversations found"
          description="Try adjusting your filters, or submit a conversation to get started."
        />
      ) : (
        <>
          {/* Desktop table */}
          <div className="mt-4 hidden overflow-x-auto rounded-xl border border-border bg-surface md:block">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-text-muted">
                  <th className="p-4 font-medium">Platform</th>
                  <th className="p-4 font-medium">Author</th>
                  <th className="p-4 font-medium">Topic</th>
                  <th className="p-4 font-medium">Status</th>
                  <th className="p-4 font-medium">Relevance</th>
                  <th className="p-4 font-medium">Drafts</th>
                  <th className="p-4 font-medium">Submitted</th>
                  <th className="p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id} className="border-b border-border/50 hover:bg-surface-raised transition-colors">
                    <td className="p-4">
                      <PlatformBadge platform={c.platform} />
                    </td>
                    <td className="p-4 text-text-primary">{c.post_author ?? "—"}</td>
                    <td className="max-w-xs truncate p-4 text-text-secondary">
                      {c.central_topic || (c.original_post ?? "").slice(0, 80) || "—"}
                    </td>
                    <td className="p-4">
                      <StatusBadge status={c.analysis_status} />
                    </td>
                    <td className="p-4">
                      <RelevanceScore score={c.relevance_score} />
                    </td>
                    <td className="p-4 text-text-secondary">
                      <span className="flex items-center gap-1.5">
                        {c.draft_count}
                        {c.has_posted_reply && (
                          <span className="rounded-full bg-success/20 px-1.5 py-0.5 text-xs text-success">
                            commented
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="p-4 text-xs text-text-muted">
                      {formatDate(c.submitted_at)}
                    </td>
                    <td className="p-4">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => router.push(`/conversations/${c.id}`)}
                      >
                        View
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="mt-4 space-y-3 md:hidden">
            {filtered.map((c) => (
              <div key={c.id} className="rounded-xl border border-border bg-surface p-4">
                <div className="flex items-center gap-2">
                  <PlatformBadge platform={c.platform} />
                  <StatusBadge status={c.analysis_status} />
                  <span className="ml-auto text-xs text-text-muted">
                    {formatDate(c.submitted_at)}
                  </span>
                </div>
                <p className="mt-2 text-sm text-text-primary">
                  {c.central_topic ?? (c.original_post ?? "").slice(0, 120)}…
                </p>
                <div className="mt-3 flex items-center justify-between">
                  <RelevanceScore score={c.relevance_score} />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => router.push(`/conversations/${c.id}`)}
                  >
                    View
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 flex items-center justify-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              disabled={page <= 1 || refreshing}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-xs text-text-muted">
              Page {page} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={page >= totalPages || refreshing}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </>
      )}
        </>
      )}

      <ConfirmDialog
        open={scan !== null}
        title="Remove deleted posts?"
        description={`${scan?.deleted_count ?? 0} of ${scan?.checked ?? 0} checked conversation(s) have a source post that was deleted on the platform. Remove them and their drafts from your portal? This cannot be undone.`}
        confirmLabel="Remove them"
        destructive
        loading={removing}
        onConfirm={confirmCleanup}
        onCancel={() => setScan(null)}
      />
    </div>
  );
}
