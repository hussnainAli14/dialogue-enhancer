"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import type { ConversationDetail } from "@/lib/types";
import PlatformBadge from "@/components/feed/PlatformBadge";

export default function ConversationThread({
  conversation,
}: {
  conversation: ConversationDetail;
}) {
  const longThread = (conversation.full_thread?.length ?? 0) > 500;
  const [expanded, setExpanded] = useState(!longThread);

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center gap-3">
        <PlatformBadge platform={conversation.platform} />
        {conversation.post_author && (
          <span className="text-sm text-text-secondary">
            {conversation.post_author}
          </span>
        )}
        {conversation.post_url && (
          <a
            href={conversation.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1 text-xs text-text-muted hover:text-accent-light transition-colors"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View original
          </a>
        )}
      </div>

      <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
        {conversation.original_post}
      </p>

      {conversation.full_thread && (
        <div className="mt-4 rounded-lg bg-surface-raised p-4">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex w-full items-center justify-between text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
          >
            Full Thread
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
          {expanded && (
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
              {conversation.full_thread}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
