"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Inbox, RefreshCw } from "lucide-react";
import { conversationsApi, discoveryApi, draftsApi } from "@/lib/api";
import type { Conversation } from "@/lib/types";
import { isWithinLast24Hours } from "@/lib/utils";
import { useConversations } from "@/hooks/useConversations";
import { useToast } from "@/hooks/useToast";
import ConversationCard from "@/components/feed/ConversationCard";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";
import Button from "@/components/shared/Button";

const PAGE_SIZE = 10;

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center gap-3">
        <div className="h-5 w-16 rounded-full bg-surface-raised" />
        <div className="h-4 w-24 rounded bg-surface-raised" />
        <div className="ml-auto h-3 w-16 rounded bg-surface-raised" />
      </div>
      <div className="mt-4 h-4 w-full rounded bg-surface-raised" />
      <div className="mt-2 h-4 w-3/4 rounded bg-surface-raised" />
      <div className="mt-4 flex items-center gap-4">
        <div className="h-2 w-24 rounded-full bg-surface-raised" />
        <div className="ml-auto flex gap-2">
          <div className="h-8 w-20 rounded-lg bg-surface-raised" />
          <div className="h-8 w-20 rounded-lg bg-surface-raised" />
        </div>
      </div>
    </div>
  );
}

export default function FeedPage() {
  const { showToast } = useToast();
  const { data, loading, error, refetch } = useConversations(
    { page_size: 100 },
    60000
  );
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [dismissingId, setDismissingId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [postedToday, setPostedToday] = useState(0);
  const [discoveredToday, setDiscoveredToday] = useState(0);
  const [triggering, setTriggering] = useState(false);

  const loadDiscoveredToday = useCallback(async () => {
    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await discoveryApi.getPosts({ date_from: today, page: 1 });
      setDiscoveredToday(res.total);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    loadDiscoveredToday();
  }, [loadDiscoveredToday]);

  const triggerDiscovery = async () => {
    setTriggering(true);
    try {
      await discoveryApi.trigger();
      showToast("success", "Discovery run started.");
      setTimeout(() => {
        loadDiscoveredToday();
        refetch();
      }, 2000);
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Trigger failed");
    } finally {
      setTriggering(false);
    }
  };

  const reviewable = useMemo(
    () =>
      (data?.conversations ?? [])
        .filter(
          (c) =>
            c.analysis_status === "analysed" &&
            c.draft_count > 0 &&
            !dismissed.has(c.id)
        )
        .sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0)),
    [data, dismissed]
  );

  const todayCount = useMemo(
    () =>
      (data?.conversations ?? []).filter((c) =>
        isWithinLast24Hours(c.submitted_at)
      ).length,
    [data]
  );

  // Conversations submitted but still being analysed (no drafts yet).
  const analysingCount = useMemo(
    () => (data?.conversations ?? []).filter((c) => c.analysis_status === "pending").length,
    [data]
  );

  // Posted-today count needs draft-level data; sample recent conversations.
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const recent = (data?.conversations ?? [])
          .filter((c) => c.draft_count > 0)
          .slice(0, 15);
        const details = await Promise.all(
          recent.map((c) => conversationsApi.getConversation(c.id).catch(() => null))
        );
        if (!mounted) return;
        let count = 0;
        details.forEach((d) => {
          d?.drafts.forEach((draft) => {
            if (
              draft.status === "posted" &&
              draft.posted_at &&
              isWithinLast24Hours(draft.posted_at)
            ) {
              count++;
            }
          });
        });
        setPostedToday(count);
      } catch {
        /* stat is non-critical */
      }
    })();
    return () => {
      mounted = false;
    };
  }, [data]);

  const handleDismiss = async (conversation: Conversation) => {
    setDismissingId(conversation.id);
    // Optimistic removal
    setDismissed((prev) => new Set(prev).add(conversation.id));
    try {
      const detail = await conversationsApi.getConversation(conversation.id);
      await Promise.all(
        detail.drafts
          .filter((d) => d.status === "pending")
          .map((d) => draftsApi.rejectDraft(d.id, "dismissed from feed"))
      );
      showToast("info", "Conversation dismissed.");
    } catch {
      setDismissed((prev) => {
        const next = new Set(prev);
        next.delete(conversation.id);
        return next;
      });
      showToast("error", "Failed to dismiss conversation.");
    } finally {
      setDismissingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(reviewable.length / PAGE_SIZE));
  const pageItems = reviewable.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  if (error && !data) {
    return (
      <ErrorState
        title="Could not load your feed"
        description={error}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          { label: "Conversations today", value: todayCount },
          { label: "Awaiting review", value: reviewable.length },
          { label: "Posted today", value: postedToday },
        ].map((s) => (
          <div
            key={s.label}
            className="rounded-xl border border-border bg-surface p-4 text-center"
          >
            <p className="text-2xl font-semibold text-text-primary">{s.value}</p>
            <p className="text-xs text-text-muted">{s.label}</p>
          </div>
        ))}
        <div className="relative rounded-xl border border-border bg-surface p-4 text-center">
          <button
            onClick={triggerDiscovery}
            disabled={triggering}
            title="Run discovery now"
            className="absolute right-2 top-2 text-text-muted transition-colors hover:text-accent-light disabled:opacity-50"
            aria-label="Run discovery now"
          >
            <RefreshCw className={triggering ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </button>
          <p className="text-2xl font-semibold text-text-primary">{discoveredToday}</p>
          <p className="text-xs text-text-muted">Discovered today</p>
        </div>
      </div>

      {analysingCount > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-accent/40 bg-accent/10 p-4">
          <RefreshCw className="h-4 w-4 animate-spin text-accent-light" />
          <span className="text-sm text-text-primary">
            <strong>{analysingCount}</strong> conversation{analysingCount === 1 ? "" : "s"} being
            analysed…
          </span>
          <span className="text-sm text-text-secondary">
            New drafts appear here automatically when ready (usually under a minute). Some may be
            skipped if the system recommends not commenting.
          </span>
          <a
            href="/conversations?status=pending"
            className="ml-auto text-xs text-accent-light hover:underline"
          >
            View in progress →
          </a>
        </div>
      )}

      <div className="mt-6 space-y-4">
        {loading && !data ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : pageItems.length === 0 ? (
          <EmptyState
            icon={<Inbox className="h-12 w-12" />}
            title="You are all caught up"
            description="No conversations need your attention right now."
          />
        ) : (
          pageItems.map((c) => (
            <ConversationCard
              key={c.id}
              conversation={c}
              onDismiss={() => handleDismiss(c)}
              dismissing={dismissingId === c.id}
            />
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-center gap-3">
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
      )}
    </div>
  );
}
