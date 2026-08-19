"use client";

import { useState } from "react";
import {
  AlertTriangle,
  GitMerge,
  HelpCircle,
  Info,
  Lightbulb,
  Link2,
} from "lucide-react";
import type { DraftStyle, ResponseDraft } from "@/lib/types";
import { REJECTION_REASONS, STYLE_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import Button from "@/components/shared/Button";
import StatusBadge from "@/components/feed/StatusBadge";
import SourceBadge from "./SourceBadge";

const STYLE_ICONS: Record<DraftStyle, React.ReactNode> = {
  insightful_contribution: <Lightbulb className="h-4 w-4" />,
  facilitative_question: <HelpCircle className="h-4 w-4" />,
  synthesis_of_viewpoints: <GitMerge className="h-4 w-4" />,
  constructive_challenge: <AlertTriangle className="h-4 w-4" />,
};

export interface DraftActions {
  onApprove: (id: string) => void;
  onApproveAndPost: (id: string) => void;
  onPost: (id: string) => void;
  onUnapprove: (id: string) => void;
  onEditAndApprove: (id: string, content: string) => void;
  onReject: (id: string, reason?: string) => void;
  onSave: (id: string) => void;
}

interface DraftCardProps {
  draft: ResponseDraft;
  actions: DraftActions;
  canPost?: boolean;
  editOpen?: boolean;
  onOpenEdit?: (id: string | null) => void;
}

export default function DraftCard({ draft, actions, canPost, editOpen, onOpenEdit }: DraftCardProps) {
  const [editText, setEditText] = useState(draft.content);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const pending = draft.status === "pending";
  const editing = !!editOpen;
  // Approved or edited but not yet posted — can still be published or reverted.
  const approvedNotPosted = draft.status === "approved" || draft.status === "edited";
  const revertable = approvedNotPosted || draft.status === "saved" || draft.status === "rejected";

  return (
    <div
      className={cn(
        "flex flex-col rounded-xl border border-border bg-surface p-6 transition-opacity",
        !pending && "opacity-70"
      )}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-accent-light">
        {STYLE_ICONS[draft.style]}
        {STYLE_LABELS[draft.style]}
        {!pending && (
          <span className="ml-auto">
            <StatusBadge status={draft.status} />
          </span>
        )}
      </div>

      {editing ? (
        <div className="mt-4 flex flex-1 flex-col gap-2">
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            className="min-h-[160px] flex-1 resize-y rounded-lg border border-border-bright bg-background p-3 text-sm text-text-primary focus:outline-none"
            autoFocus
          />
          <span className="text-xs text-text-muted">{editText.length} characters</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                actions.onEditAndApprove(draft.id, editText);
                onOpenEdit?.(null);
              }}
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onOpenEdit?.(null)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="mt-4 flex-1 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
            {draft.edited_content ?? draft.content}
          </p>

          {draft.value_explanation && (
            <p className="mt-3 flex items-start gap-1.5 text-sm italic text-text-secondary">
              <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {draft.value_explanation}
            </p>
          )}

          {draft.source_document_titles?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {draft.source_document_titles.map((t, i) => (
                <SourceBadge key={i} title={t} />
              ))}
            </div>
          )}

          {draft.include_link && draft.suggested_link && (
            <span className="mt-2 inline-flex items-center gap-1 text-xs text-accent-light">
              <Link2 className="h-3 w-3" />
              {draft.suggested_link}
            </span>
          )}

          {pending && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  className="bg-success hover:bg-success/80"
                  onClick={() => actions.onApprove(draft.id)}
                >
                  Approve
                </Button>
                {canPost && (
                  <Button
                    size="sm"
                    className="bg-accent hover:bg-accent-hover"
                    onClick={() => actions.onApproveAndPost(draft.id)}
                  >
                    Approve & Post
                  </Button>
                )}
                <Button size="sm" onClick={() => onOpenEdit?.(draft.id)}>
                  Edit & Approve
                </Button>
                <Button size="sm" variant="ghost" onClick={() => actions.onSave(draft.id)}>
                  Save for Later
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => setRejectOpen((v) => !v)}
                >
                  Reject
                </Button>
              </div>

              {rejectOpen && (
                <div className="mt-3 rounded-lg bg-surface-raised p-3">
                  <p className="text-xs text-text-secondary mb-2">
                    Why is this draft not right? (optional)
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {REJECTION_REASONS.map((r) => (
                      <button
                        key={r}
                        onClick={() => setRejectReason(r)}
                        className={cn(
                          "rounded-full px-2.5 py-1 text-xs transition-colors",
                          rejectReason === r
                            ? "bg-danger/30 text-danger"
                            : "bg-surface text-text-secondary hover:text-text-primary"
                        )}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                  <input
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Or type a custom reason"
                    className="mt-2 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-border-bright"
                  />
                  <Button
                    size="sm"
                    variant="danger"
                    className="mt-2"
                    onClick={() => {
                      actions.onReject(draft.id, rejectReason || undefined);
                      setRejectOpen(false);
                    }}
                  >
                    Confirm Reject
                  </Button>
                </div>
              )}
            </div>
          )}

          {!pending && revertable && (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
              {canPost && approvedNotPosted && (
                <Button
                  size="sm"
                  className="bg-accent hover:bg-accent-hover"
                  onClick={() => actions.onPost(draft.id)}
                >
                  Post Now
                </Button>
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={() => actions.onUnapprove(draft.id)}
              >
                Remove Approval
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
