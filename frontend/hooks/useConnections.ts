"use client";

import { useCallback, useEffect, useState } from "react";
import { connectionsApi } from "@/lib/api";
import type { PlatformConnectionStatus } from "@/lib/types";

export function useConnections() {
  const [connections, setConnections] = useState<PlatformConnectionStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await connectionsApi.getStatus();
      setConnections(res.connections);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load connections");
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return { connections, loading, error, refetch: fetchStatus };
}
