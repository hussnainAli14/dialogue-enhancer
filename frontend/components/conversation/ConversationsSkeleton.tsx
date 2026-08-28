"use client";

import Skeleton from "@/components/shared/Skeleton";

/** Placeholder matching the conversations table/card layout, so switching a
 *  filter keeps the page height stable instead of collapsing to a spinner. */
export default function ConversationsSkeleton({ rows = 8 }: { rows?: number }) {
  const items = Array.from({ length: rows });

  return (
    <div role="status" aria-label="Loading conversations">
      {/* Desktop table */}
      <div className="mt-4 hidden overflow-x-auto rounded-xl border border-border bg-surface md:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-text-muted">
              <th className="p-4 font-medium">Platform</th>
              <th className="p-4 font-medium">Author</th>
              <th className="p-4 font-medium">Topic</th>
              <th className="p-4 font-medium">Status</th>
              <th className="p-4 font-medium">Relevance</th>
              <th className="p-4 font-medium">Drafts</th>
              <th className="p-4 font-medium">Submitted</th>
              <th className="p-4 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((_, i) => (
              <tr key={i} className="border-b border-border/50">
                <td className="p-4"><Skeleton className="h-5 w-16 rounded-md" /></td>
                <td className="p-4"><Skeleton className="h-4 w-28" /></td>
                <td className="p-4"><Skeleton className="h-4 w-48" /></td>
                <td className="p-4"><Skeleton className="h-5 w-20 rounded-full" /></td>
                <td className="p-4"><Skeleton className="h-4 w-12" /></td>
                <td className="p-4"><Skeleton className="h-4 w-8" /></td>
                <td className="p-4"><Skeleton className="h-3 w-24" /></td>
                <td className="p-4"><Skeleton className="h-7 w-14 rounded-lg" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="mt-4 space-y-3 md:hidden">
        {items.slice(0, 5).map((_, i) => (
          <div key={i} className="rounded-xl border border-border bg-surface p-4">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-16 rounded-md" />
              <Skeleton className="h-5 w-20 rounded-full" />
              <Skeleton className="ml-auto h-3 w-20" />
            </div>
            <Skeleton className="mt-3 h-4 w-full" />
            <Skeleton className="mt-1.5 h-4 w-2/3" />
            <div className="mt-3 flex items-center justify-between">
              <Skeleton className="h-4 w-12" />
              <Skeleton className="h-7 w-14 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
