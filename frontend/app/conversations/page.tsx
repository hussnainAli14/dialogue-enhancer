"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { MessageSquare, Trash2 } from "lucide-react";
import { conversationsApi } from "@/lib/api";
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
import LoadingSpinner from "@/components/shared/LoadingSpinner";
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

  // Bulk cleanup of deleted source posts (Bluesky/Mastodon).
  const [scanning, setScanning] = useState(false);
  const [cleanupCount, setCleanupCount] = useState<number | null>(null);
  const [removing, setRemoving] = useState(false);

  const scanDeleted = async () => {
    setScanning(true);
    try {
      const res = await conversationsApi.cleanupDeleted(true); // dry run
      if (res.deleted_count === 0) {
        showToast("success", "No deleted posts found — everything is still live.");
      } else {
        setCleanupCount(res.deleted_count);
      }
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const confirmCleanup = async () => {
    setRemoving(true);
    try {
      const res = await conversationsApi.cleanupDeleted(false); // delete
      showToast("success", `Removed ${res.deleted_count} deleted post(s).`);
      refetch();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setRemoving(false);
      setCleanupCount(null);
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
        <Button
          variant="ghost"
          size="sm"
          iconLeft={<Trash2 className="h-4 w-4" />}
          onClick={scanDeleted}
          loading={scanning}
          title="Scan Bluesky/Mastodon conversations and remove ones whose source post was deleted"
        >
          Clean up deleted
        </Button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-5">
        <Select
          value={platformFilter}
          onChange={(e) => {
            setPlatformFilter(e.target.value);
            setPage(1);
          }}
          placeholder="All platforms"
          options={PLATFORMS.map((p) => ({ value: p, label: PLATFORM_LABELS[p] }))}
        />
        <Select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
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

      {loading && !data ? (
        <div className="flex justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : filtered.length === 0 ? (
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
              disabled={page <= 1}
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
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </>
      )}

      <ConfirmDialog
        open={cleanupCount !== null}
        title="Remove deleted posts?"
        description={`${cleanupCount ?? 0} conversation(s) have a source post that was deleted on the platform. Remove them and their drafts from your portal? This cannot be undone.`}
        confirmLabel="Remove them"
        destructive
        loading={removing}
        onConfirm={confirmCleanup}
        onCancel={() => setCleanupCount(null)}
      />
    </div>
  );
}
