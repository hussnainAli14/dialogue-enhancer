"use client";

import { useFeedback } from "@/hooks/useFeedback";
import FeedbackStats from "@/components/history/FeedbackStats";
import StylePerformance from "@/components/history/StylePerformance";
import FeedbackTable from "@/components/history/FeedbackTable";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import ErrorState from "@/components/shared/ErrorState";

export default function HistoryPage() {
  const { data, loading, error, refetch } = useFeedback();

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Could not load feedback history"
        description={error ?? undefined}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="space-y-6">
      <FeedbackStats summary={data} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <StylePerformance summary={data} />

        <div className="rounded-xl border border-border bg-surface p-6">
          <h2 className="text-lg font-medium text-text-primary">
            Top Rejection Reasons
          </h2>
          {data.most_common_rejection_reasons.length === 0 ? (
            <p className="mt-4 text-sm text-text-secondary">No rejections yet.</p>
          ) : (
            <div className="mt-4 space-y-3">
              {data.most_common_rejection_reasons.map((r, i) => {
                const max = data.most_common_rejection_reasons[0].count;
                return (
                  <div key={i}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className="text-text-primary">{r.reason}</span>
                      <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">
                        {r.count}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-raised">
                      <div
                        className="h-full rounded-full bg-danger/60"
                        style={{ width: `${(r.count / max) * 100}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <FeedbackTable />
    </div>
  );
}
