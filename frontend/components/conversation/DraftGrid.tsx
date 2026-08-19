"use client";

import { useState } from "react";
import type { ResponseDraft } from "@/lib/types";
import DraftCard, { DraftActions } from "./DraftCard";

export default function DraftGrid({
  drafts,
  actions,
  canPost = false,
}: {
  drafts: ResponseDraft[];
  actions: DraftActions;
  canPost?: boolean;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {drafts.map((draft) => (
        <DraftCard
          key={draft.id}
          draft={draft}
          actions={actions}
          canPost={canPost}
          editOpen={editingId === draft.id}
          onOpenEdit={setEditingId}
        />
      ))}
    </div>
  );
}
