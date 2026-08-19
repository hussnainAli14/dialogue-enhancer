"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, RefreshCw } from "lucide-react";
import { conversationsApi, draftsApi } from "@/lib/api";
import type { ResponseDraft } from "@/lib/types";
import { useConversation } from "@/hooks/useConversation";
import { useToast } from "@/hooks/useToast";
import ConversationThread from "@/components/conversation/ConversationThread";
import AnalysisPanel from "@/components/conversation/AnalysisPanel";
import DraftGrid from "@/components/conversation/DraftGrid";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import ErrorState from "@/components/shared/ErrorState";
import Button from "@/components/shared/Button";
import ConfirmDialog from "@/components/shared/ConfirmDialog";
import StatusBadge from "@/components/feed/StatusBadge";

export default function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { showToast } = useToast();
  const { data, loading, error, refetch, updateDraftLocal } = useConversation(
    params.id
  );

  const runAction = useCallback(
    async (
      draft: ResponseDraft | undefined,
      optimisticPatch: Partial<ResponseDraft>,
      apiCall: () => Promise<ResponseDraft>,
      successMsg: string
    ) => {
      if (!draft) return;
      const previous = { ...draft };
      updateDraftLocal(draft.id, optimisticPatch);
      try {
        const updated = await apiCall();
        updateDraftLocal(draft.id, updated);
        showToast("success", successMsg);
      } catch (err) {
        updateDraftLocal(draft.id, previous);
        showToast("error", err instanceof Error ? err.message : "Action failed");
      }
    },
    [updateDraftLocal, showToast]
  );

  const findDraft = (id: string) => data?.drafts.find((d) => d.id === id);

  const actions = {
    onApprove: (id: string) =>
      runAction(
        findDraft(id),
        { status: "approved" },
        () => draftsApi.approveDraft(id),
        "Draft approved."
      ),
    onEditAndApprove: (id: string, content: string) =>
      runAction(
        findDraft(id),
        { status: "edited", edited_content: content },
        () => draftsApi.editAndApproveDraft(id, content),
        "Draft edited and approved."
      ),
    onReject: (id: string, reason?: string) =>
      runAction(
        findDraft(id),
        { status: "rejected", rejection_reason: reason ?? null },
        () => draftsApi.rejectDraft(id, reason),
        "Draft rejected."
      ),
    onSave: (id: string) =>
      runAction(
        findDraft(id),
        { status: "saved" },
        () => draftsApi.saveDraft(id),
        "Draft saved for later."
      ),
    onApproveAndPost: (id: string) =>
      runAction(
        findDraft(id),
        { status: "posted" },
        () => draftsApi.approveAndPostDraft(id),
        "Draft approved and posted to the platform."
      ),
    onPost: (id: string) =>
      runAction(
        findDraft(id),
        { status: "posted" },
        () => draftsApi.postDraft(id),
        "Reply posted to the platform."
      ),
    onUnapprove: (id: string) =>
      runAction(
        findDraft(id),
        { status: "pending" },
        () => draftsApi.unapproveDraft(id),
        "Approval removed — draft is pending again."
      ),
  };

  const canPost =
    data?.platform === "bluesky" || data?.platform === "mastodon";

  // Freshness check: is the original source post still live on the platform?
  const [sourceExists, setSourceExists] = useState<boolean | null | undefined>(undefined);
  const [checkingSource, setCheckingSource] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [removing, setRemoving] = useState(false);

  const checkSource = useCallback(
    async (announce = false) => {
      if (!canPost) return;
      setCheckingSource(true);
      try {
        const res = await conversationsApi.sourceStatus(params.id);
        setSourceExists(res.exists);
        if (announce) {
          if (res.exists === true) showToast("success", "The original post is still live.");
          else if (res.exists === false) showToast("warning", "The original post was removed.");
          else showToast("info", "Couldn't determine — check the connection.");
        }
      } catch {
        setSourceExists(undefined);
      } finally {
        setCheckingSource(false);
      }
    },
    [canPost, params.id, showToast]
  );

  // Auto-check once when the conversation loads (fresh data from the platform).
  useEffect(() => {
    if (data && canPost) checkSource(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.id, canPost]);

  const removeConversation = async () => {
    setRemoving(true);
    try {
      await conversationsApi.deleteConversation(params.id);
      showToast("success", "Removed from your portal.");
      router.push("/feed");
    } catch (err) {
      showToast("error", err instanceof Error ? err.message : "Failed to remove");
      setRemoving(false);
      setRemoveOpen(false);
    }
  };

  // Keyboard shortcuts: A approve, R reject first pending draft.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const firstPending = data?.drafts.find((d) => d.status === "pending");
      if (!firstPending) return;
      if (e.key === "a" || e.key === "A") actions.onApprove(firstPending.id);
      if (e.key === "r" || e.key === "R") actions.onReject(firstPending.id);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Could not load conversation"
        description={error ?? undefined}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          iconLeft={<ArrowLeft className="h-4 w-4" />}
          onClick={() => router.push("/feed")}
        >
          Back to Feed
        </Button>
        {canPost && (
          <Button
            variant="ghost"
            size="sm"
            iconLeft={<RefreshCw className={checkingSource ? "h-4 w-4 animate-spin" : "h-4 w-4"} />}
            onClick={() => checkSource(true)}
            disabled={checkingSource}
          >
            Check if post is live
          </Button>
        )}
      </div>

      {sourceExists === false && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-danger/40 bg-danger/10 p-4">
          <AlertTriangle className="h-5 w-5 shrink-0 text-danger" />
          <p className="text-sm text-text-primary">
            The original post appears to have been <strong>deleted</strong> on the
            platform. Replying is no longer possible.
          </p>
          <Button
            variant="danger"
            size="sm"
            className="ml-auto"
            onClick={() => setRemoveOpen(true)}
          >
            Remove from portal
          </Button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Left column — independently scrollable on desktop */}
        <div className="space-y-6 lg:col-span-2 lg:max-h-[calc(100vh-160px)] lg:overflow-y-auto lg:pr-2">
          <ConversationThread conversation={data} />
          {data.analysis ? (
            <AnalysisPanel analysis={data.analysis} />
          ) : (
            <div className="rounded-xl border border-border bg-surface p-6 text-sm text-text-secondary">
              {data.analysis_status === "pending"
                ? "Analysis is still running. This usually takes 15 to 30 seconds."
                : "No analysis available for this conversation."}
              <div className="mt-3">
                <Button size="sm" variant="secondary" onClick={() => refetch()}>
                  Refresh
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Right column — drafts */}
        <div className="lg:col-span-3">
          {data.drafts.length > 0 ? (
            <DraftGrid drafts={data.drafts} actions={actions} canPost={canPost} />
          ) : (
            <div className="rounded-xl border border-border bg-surface p-6 text-center text-sm text-text-secondary">
              {data.analysis_status === "skipped" ? (
                <div className="space-y-2">
                  <StatusBadge status="skipped" />
                  <p>
                    The system recommended not commenting on this conversation, so
                    no drafts were generated.
                  </p>
                </div>
              ) : data.analysis_status === "pending" ? (
                "Drafts are being generated…"
              ) : (
                "No drafts available."
              )}
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={removeOpen}
        title="Remove this conversation?"
        description="The original post was deleted on the platform. This removes the conversation and its drafts from your portal. This cannot be undone."
        confirmLabel="Remove"
        destructive
        loading={removing}
        onConfirm={removeConversation}
        onCancel={() => setRemoveOpen(false)}
      />
    </div>
  );
}
