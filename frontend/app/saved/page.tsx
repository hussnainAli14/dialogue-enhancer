"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bookmark, ExternalLink } from "lucide-react";
import { draftsApi } from "@/lib/api";
import type { DraftWithConversation } from "@/lib/types";
import { PLATFORM_BADGE_CLASSES, PLATFORM_LABELS, STYLE_LABELS } from "@/lib/constants";
import { cn, formatDate } from "@/lib/utils";
import { useToast } from "@/hooks/useToast";
import Button from "@/components/shared/Button";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import EmptyState from "@/components/shared/EmptyState";
import ErrorState from "@/components/shared/ErrorState";

export default function SavedPage() {
  const { showToast } = useToast();
  const [drafts, setDrafts] = useState<DraftWithConversation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await draftsApi.getDrafts({ status: "saved", page_size: 100 });
      setDrafts(res.drafts);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load saved drafts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Saved is a parked state — restoring puts the draft back in the normal
  // approve/edit/reject flow on its conversation page.
  const restore = async (d: DraftWithConversation) => {
    setBusy(d.id);
    try {
      await draftsApi.unapproveDraft(d.id);
      showToast("success", "Moved back to pending — review it on the conversation.");
      load();
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Restore failed");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error) return <ErrorState title="Couldn't load saved drafts" description={error} onRetry={load} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-text-primary">Saved for Later</h1>
        <span className="rounded-full border border-warning/40 bg-warning/15 px-2.5 py-0.5 text-xs font-medium text-warning">
          {total} saved
        </span>
      </div>

      {drafts.length === 0 ? (
        <EmptyState
          icon={<span className="text-4xl">🔖</span>}
          title="Nothing saved yet"
          description="Drafts you park with “Save for Later” on a conversation show up here."
        />
      ) : (
        <div className="space-y-3">
          {drafts.map((d) => {
            const conv = d.conversation;
            const body = d.edited_content ?? d.content;
            return (
              <div key={d.id} className="rounded-xl border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center gap-2">
                  {conv && (
                    <span
                      className={cn(
                        "inline-flex h-5 shrink-0 items-center rounded px-2 text-xs",
                        PLATFORM_BADGE_CLASSES[conv.platform]
                      )}
                    >
                      {PLATFORM_LABELS[conv.platform] ?? conv.platform}
                    </span>
                  )}
                  <span className="inline-flex h-5 items-center rounded-md border border-accent-light/40 bg-accent/25 px-2.5 text-xs font-medium text-accent-light">
                    {STYLE_LABELS[d.style] ?? d.style}
                  </span>
                  <span className="inline-flex h-5 items-center gap-1.5 rounded-md border border-warning/40 bg-warning/15 px-2.5 text-xs font-medium text-warning">
                    <Bookmark className="h-3 w-3" />
                    Saved
                  </span>
                  <span className="ml-auto text-xs text-text-muted">
                    {formatDate(d.created_at)}
                  </span>
                </div>

                {conv && (
                  <p className="mt-3 line-clamp-2 text-xs text-text-muted">
                    <span className="text-text-secondary">
                      {conv.post_author ? `@${conv.post_author.replace(/^@/, "")}` : "Original post"}:
                    </span>{" "}
                    {conv.original_post}
                  </p>
                )}

                <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
                  {body}
                </p>

                {d.value_explanation && (
                  <p className="mt-2 text-xs italic text-text-secondary">{d.value_explanation}</p>
                )}

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {conv && (
                    <Link href={`/conversations/${conv.id}`}>
                      <Button size="sm">Open conversation</Button>
                    </Link>
                  )}
                  <Button
                    size="sm"
                    className="border border-warning/40 bg-warning/15 text-warning hover:bg-warning/25"
                    loading={busy === d.id}
                    onClick={() => restore(d)}
                  >
                    Move back to pending
                  </Button>
                  {conv?.post_url && (
                    <a
                      href={conv.post_url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto inline-flex items-center gap-1 text-xs text-accent-light hover:underline"
                    >
                      View original <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
