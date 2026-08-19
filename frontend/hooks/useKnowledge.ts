"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/lib/api";
import type { KnowledgeListResponse } from "@/lib/types";

export function useKnowledge() {
  const [data, setData] = useState<KnowledgeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const result = await knowledgeApi.getDocuments();
      setData(result);
      setError(null);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load knowledge base");
      return null;
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Poll every 3s until no documents are processing.
  const pollUntilProcessed = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const result = await fetchData(true);
      if (result && !result.documents.some((d) => d.status === "processing")) {
        stopPolling();
      }
    }, 3000);
  }, [fetchData, stopPolling]);

  useEffect(() => {
    fetchData();
    return stopPolling;
  }, [fetchData, stopPolling]);

  return { data, loading, error, refetch: fetchData, pollUntilProcessed };
}
