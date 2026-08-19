"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { conversationsApi } from "@/lib/api";
import type { ConversationFilters, ConversationListResponse } from "@/lib/types";

export function useConversations(
  filters: ConversationFilters = {},
  pollIntervalMs?: number
) {
  const [data, setData] = useState<ConversationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const filtersKey = JSON.stringify(filters);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const result = await conversationsApi.getConversations(filtersRef.current);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    if (!pollIntervalMs) return;
    const interval = setInterval(() => fetchData(true), pollIntervalMs);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersKey, pollIntervalMs]);

  return { data, loading, error, refetch: fetchData };
}
