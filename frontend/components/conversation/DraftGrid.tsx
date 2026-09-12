"use client";

import { useState } from "react";
import type { ResponseDraft } from "@/lib/types";
import DraftCard, { DraftActions, DraftActionName } from "./DraftCard";

export default function DraftGrid({
  drafts,
  actions,
  canPost = false,
  manualPost = false,
  busy = null,
}: {
  drafts: ResponseDraft[];
  actions: DraftActions;
  canPost?: boolean;
  manualPost?: boolean;
  busy?: { id: string; action: DraftActionName } | null;
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
          manualPost={manualPost}
          editOpen={editingId === draft.id}
          onOpenEdit={setEditingId}
          busyAction={busy?.id === draft.id ? busy.action : null}
        />
      ))}
    </div>
  );
}
