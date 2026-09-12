"use client";

import { useRouter } from "next/navigation";
import { CheckCircle2, ExternalLink, FileText, Star, XCircle } from "lucide-react";
import type { Conversation } from "@/lib/types";
import { cn, timeAgo, truncate } from "@/lib/utils";
import PlatformBadge from "./PlatformBadge";
import RelevanceScore from "./RelevanceScore";
import Button from "@/components/shared/Button";

interface ConversationCardProps {
  conversation: Conversation;
  centralTopic?: string | null;
  onDismiss: (id: string) => void;
  dismissing?: boolean;
  onDraftRequested?: (id: string) => void;
  drafting?: boolean;
}

export default function ConversationCard({
  conversation,
  centralTopic,
  onDismiss,
  dismissing,
  onDraftRequested,
  drafting,
}: ConversationCardProps) {
  const router = useRouter();
  const isReply = !!conversation.is_reply_to_me;
  const noDrafts = conversation.draft_count === 0;
  // A reply-to-you that hasn't been drafted yet: offer on-demand drafting.
  const awaitingDraft = isReply && noDrafts && conversation.analysis_status !== "pending";

  return (
    <div
      className={cn(
        "rounded-xl border bg-surface p-6 transition-colors",
        isReply
          ? "border-amber-400/60 hover:border-amber-400 ring-1 ring-amber-400/20"
          : "border-border hover:border-border-bright"
      )}
    >
      <div className="flex items-center gap-3">
        {isReply && (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/20 px-2 py-0.5 text-xs font-medium text-amber-400">
            <Star className="h-3 w-3 fill-amber-400" />
            Reply to you
          </span>
        )}
        <PlatformBadge platform={conversation.platform} />
        {(conversation.source === "linkedin_clipper" ||
          conversation.source === "reddit_clipper") && (
          <span className="rounded-full bg-blue-700/20 px-2 py-0.5 text-xs text-blue-300">
            Clipped
          </span>
        )}
        {conversation.post_author && (
          <span className="text-sm text-text-secondary">{conversation.post_author}</span>
        )}
        {conversation.has_posted_reply && (
          <span className="inline-flex items-center gap-1 rounded-full bg-success/20 px-2 py-0.5 text-xs text-success">
            <CheckCircle2 className="h-3 w-3" />
            Replied
          </span>
        )}
        <span className="ml-auto text-xs text-text-muted">
          {timeAgo(conversation.submitted_at)}
        </span>
      </div>

      <p className="mt-3 text-sm text-text-primary leading-relaxed">
        {truncate(conversation.original_post, 200)}
      </p>

      {isReply && conversation.parent_post_url && (
        <a
          href={conversation.parent_post_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs text-accent-light hover:underline"
        >
          In reply to your post <ExternalLink className="h-3 w-3" />
        </a>
      )}

      {centralTopic && <p className="mt-2 text-sm text-text-secondary">{centralTopic}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-4">
        {!isReply && <RelevanceScore score={conversation.relevance_score} />}
        {!noDrafts && (
          <span className="flex items-center gap-1 text-xs text-text-muted">
            <FileText className="h-3.5 w-3.5" />
            {conversation.draft_count} draft{conversation.draft_count === 1 ? "" : "s"} ready
          </span>
        )}

        <div className="ml-auto flex gap-2">
          <Button
            size="sm"
            className="border border-danger/40 bg-danger/15 text-danger hover:bg-danger/25"
            iconLeft={<XCircle className="h-4 w-4" />}
            onClick={() => onDismiss(conversation.id)}
            loading={dismissing}
          >
            Dismiss
          </Button>
          {awaitingDraft ? (
            <Button
              size="sm"
              loading={drafting}
              onClick={() => onDraftRequested?.(conversation.id)}
            >
              Draft response
            </Button>
          ) : (
            <Button size="sm" onClick={() => router.push(`/conversations/${conversation.id}`)}>
              {noDrafts ? "View" : "Review"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
