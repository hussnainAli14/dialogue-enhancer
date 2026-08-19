"use client";

import { useEffect, useMemo, useState } from "react";
import { conversationsApi } from "@/lib/api";
import type { ConversationDetail, ResponseDraft } from "@/lib/types";
import { STYLE_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import Select from "@/components/shared/Select";
import Button from "@/components/shared/Button";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import StatusBadge from "@/components/feed/StatusBadge";

interface Row {
  date: string;
  platform: string;
  style: string;
  action: string;
  originalLength: number;
  finalLength: number;
}

const PAGE_SIZE = 20;

export default function FeedbackTable() {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        // The backend has no dedicated feedback-log list endpoint yet, so we
        // reconstruct decision history from decided drafts across conversations.
        const list = await conversationsApi.getConversations({ page_size: 100 });
        const details = await Promise.all(
          list.conversations
            .filter((c) => c.draft_count > 0)
            .slice(0, 30)
            .map((c) => conversationsApi.getConversation(c.id).catch(() => null))
        );
        if (!mounted) return;
        const collected: Row[] = [];
        details.forEach((detail: ConversationDetail | null) => {
          detail?.drafts
            .filter((d: ResponseDraft) => d.status !== "pending")
            .forEach((d) => {
              collected.push({
                date: d.approved_at || d.created_at,
                platform: detail.platform,
                style: d.style,
                action: d.status,
                originalLength: d.content.length,
                finalLength: (d.edited_content ?? d.content).length,
              });
            });
        });
        collected.sort((a, b) => (a.date < b.date ? 1 : -1));
        setRows(collected);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const filtered = useMemo(
    () => (actionFilter ? rows.filter((r) => r.action === actionFilter) : rows),
    [rows, actionFilter]
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium text-text-primary">Decision History</h2>
        <div className="w-40">
          <Select
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
              setPage(1);
            }}
            placeholder="All actions"
            options={["approved", "edited", "rejected", "saved", "posted"].map((a) => ({
              value: a,
              label: a,
            }))}
          />
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <LoadingSpinner size="lg" />
        </div>
      ) : pageRows.length === 0 ? (
        <p className="py-10 text-center text-sm text-text-secondary">
          No decisions recorded yet.
        </p>
      ) : (
        <>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-text-muted">
                  <th className="pb-2 pr-4 font-medium">Date</th>
                  <th className="pb-2 pr-4 font-medium">Platform</th>
                  <th className="pb-2 pr-4 font-medium">Style</th>
                  <th className="pb-2 pr-4 font-medium">Action</th>
                  <th className="pb-2 pr-4 font-medium">Original Length</th>
                  <th className="pb-2 font-medium">Final Length</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r, i) => (
                  <tr key={i} className="border-b border-border/50">
                    <td className="py-2.5 pr-4 text-text-secondary">
                      {formatDate(r.date)}
                    </td>
                    <td className="py-2.5 pr-4 capitalize text-text-primary">
                      {r.platform}
                    </td>
                    <td className="py-2.5 pr-4 text-text-primary">
                      {STYLE_LABELS[r.style] ?? r.style}
                    </td>
                    <td className="py-2.5 pr-4">
                      <StatusBadge status={r.action} />
                    </td>
                    <td className="py-2.5 pr-4 text-text-secondary">
                      {r.originalLength}
                    </td>
                    <td className="py-2.5 text-text-secondary">{r.finalLength}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-end gap-3">
            <Button
              size="sm"
              variant="ghost"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <span className="text-xs text-text-muted">
              Page {page} of {totalPages}
            </span>
            <Button
              size="sm"
              variant="ghost"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
