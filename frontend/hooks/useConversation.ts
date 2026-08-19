"use client";

import { useCallback, useEffect, useState } from "react";
import { conversationsApi } from "@/lib/api";
import type { ConversationDetail, ResponseDraft } from "@/lib/types";

export function useConversation(id: string) {
  const [data, setData] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await conversationsApi.getConversation(id);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Optimistic local update of a single draft; used before API confirms.
  const updateDraftLocal = useCallback((draftId: string, patch: Partial<ResponseDraft>) => {
    setData((prev) =>
      prev
        ? {
            ...prev,
            drafts: prev.drafts.map((d) =>
              d.id === draftId ? { ...d, ...patch } : d
            ),
          }
        : prev
    );
  }, []);

  return { data, loading, error, refetch: fetchData, updateDraftLocal };
}
