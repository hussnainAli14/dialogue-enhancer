"use client";

import { useCallback, useEffect, useState } from "react";
import { ExternalLink, Send } from "lucide-react";
import { postsApi, type PostedItem } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import PlatformBadge from "@/components/feed/PlatformBadge";
import Button from "@/components/shared/Button";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";
import LoadingSpinner from "@/components/shared/LoadingSpinner";

const PAGE_SIZE = 50;

export default function PostedPage() {
  const [items, setItems] = useState<PostedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [kind, setKind] = useState<"all" | "post" | "reply">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await postsApi.getHistory(
        page,
        PAGE_SIZE,
        kind === "all" ? undefined : kind
      );
      setItems(res.items);
      setTotal(res.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load posted history");
    } finally {
      setLoading(false);
    }
  }, [page, kind]);

  useEffect(() => {
    load();
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (error) {
    return <ErrorState title="Could not load posted history" description={error} onRetry={load} />;
  }

  const filters: { key: "all" | "post" | "reply"; label: string }[] = [
    { key: "all", label: "All" },
    { key: "post", label: "Posts" },
    { key: "reply", label: "Replies" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => {
              setKind(f.key);
              setPage(1);
            }}
            className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
              kind === f.key
                ? "bg-accent text-white"
                : "bg-surface-raised text-text-secondary hover:text-text-primary"
            }`}
          >
            {f.label}
          </button>
        ))}
        {!loading && (
          <span className="ml-auto text-sm text-text-secondary">{total} published</span>
        )}
      </div>

      {loading && items.length === 0 ? (
        <div className="flex justify-center py-20">
          <LoadingSpinner size="lg" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Send className="h-12 w-12" />}
          title="Nothing here yet"
          description="Posts you publish from Compose, and replies you post, will show up here with a link to the live post."
        />
      ) : (
        <>
      <div className="space-y-3">
        {items.map((it, i) => (
          <div
            key={i}
            className="rounded-xl border border-border bg-surface p-4"
          >
            <div className="flex items-center gap-2">
              {it.platform && <PlatformBadge platform={it.platform} />}
              <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">
                {it.type === "reply" ? "Reply" : "Post"}
              </span>
              {it.in_reply_to && (
                <span className="text-xs text-text-muted">to {it.in_reply_to}</span>
              )}
              <span className="ml-auto text-xs text-text-muted">
                {it.posted_at ? formatDate(it.posted_at) : "—"}
              </span>
            </div>

            <p className="mt-2 whitespace-pre-wrap text-sm text-text-primary">
              {it.content || "—"}
            </p>

            {it.url && (
              <a
                href={it.url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline"
              >
                View post <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <Button
            size="sm"
            variant="ghost"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-text-secondary">
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
        </>
      )}
    </div>
  );
}
