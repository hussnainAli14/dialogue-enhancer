"use client";

import { useRouter } from "next/navigation";
import { CheckCircle2, FileText, XCircle } from "lucide-react";
import type { Conversation } from "@/lib/types";
import { timeAgo, truncate } from "@/lib/utils";
import PlatformBadge from "./PlatformBadge";
import RelevanceScore from "./RelevanceScore";
import Button from "@/components/shared/Button";

interface ConversationCardProps {
  conversation: Conversation;
  centralTopic?: string | null;
  onDismiss: (id: string) => void;
  dismissing?: boolean;
}

export default function ConversationCard({
  conversation,
  centralTopic,
  onDismiss,
  dismissing,
}: ConversationCardProps) {
  const router = useRouter();

  return (
    <div className="rounded-xl border border-border bg-surface p-6 transition-colors hover:border-border-bright">
      <div className="flex items-center gap-3">
        <PlatformBadge platform={conversation.platform} />
        {conversation.post_author && (
          <span className="text-sm text-text-secondary">
            {conversation.post_author}
          </span>
        )}
        {conversation.has_posted_reply && (
          <span className="inline-flex items-center gap-1 rounded-full bg-success/20 px-2 py-0.5 text-xs text-success">
            <CheckCircle2 className="h-3 w-3" />
            Commented
          </span>
        )}
        <span className="ml-auto text-xs text-text-muted">
          {timeAgo(conversation.submitted_at)}
        </span>
      </div>

      <p className="mt-3 text-sm text-text-primary leading-relaxed">
        {truncate(conversation.original_post, 200)}
      </p>

      {centralTopic && (
        <p className="mt-2 text-sm text-text-secondary">{centralTopic}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <RelevanceScore score={conversation.relevance_score} />
        <span className="flex items-center gap-1 text-xs text-text-muted">
          <FileText className="h-3.5 w-3.5" />
          {conversation.draft_count} draft{conversation.draft_count === 1 ? "" : "s"} ready
        </span>

        <div className="ml-auto flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            iconLeft={<XCircle className="h-4 w-4" />}
            onClick={() => onDismiss(conversation.id)}
            loading={dismissing}
          >
            Dismiss
          </Button>
          <Button
            size="sm"
            onClick={() => router.push(`/conversations/${conversation.id}`)}
          >
            Review
          </Button>
        </div>
      </div>
    </div>
  );
}
