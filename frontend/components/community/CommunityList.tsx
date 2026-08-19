"use client";

import { Trash2 } from "lucide-react";
import PlatformBadge from "@/components/feed/PlatformBadge";
import Button from "@/components/shared/Button";

export interface Community {
  id: string;
  platform: string;
  name: string;
  keywords: string;
}

export default function CommunityList({
  communities,
  onRemove,
}: {
  communities: Community[];
  onRemove: (id: string) => void;
}) {
  return (
    <div className="space-y-3">
      {communities.map((c) => (
        <div
          key={c.id}
          className="flex items-center gap-4 rounded-xl border border-border bg-surface p-4"
        >
          <PlatformBadge platform={c.platform} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-text-primary">{c.name}</p>
            {c.keywords && (
              <p className="truncate text-xs text-text-muted">Keywords: {c.keywords}</p>
            )}
          </div>
          <Button
            size="sm"
            variant="danger"
            iconLeft={<Trash2 className="h-3.5 w-3.5" />}
            onClick={() => onRemove(c.id)}
          >
            Remove
          </Button>
        </div>
      ))}
    </div>
  );
}
