import type { FeedbackSummary } from "@/lib/types";
import { STYLE_LABELS } from "@/lib/constants";
import { percent } from "@/lib/utils";

const OPACITIES = ["opacity-100", "opacity-80", "opacity-60", "opacity-40"];

export default function StylePerformance({ summary }: { summary: FeedbackSummary }) {
  const styles = summary.best_performing_styles;

  return (
    <div className="rounded-xl border border-border bg-surface p-6">
      <h2 className="text-lg font-medium text-text-primary">Style Performance</h2>
      {styles.length === 0 ? (
        <p className="mt-4 text-sm text-text-secondary">
          No draft decisions recorded yet.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {styles.map((s, i) => (
            <div key={s.style}>
              <div className="mb-1 flex justify-between text-sm">
                <span className="text-text-primary">
                  {STYLE_LABELS[s.style] ?? s.style}
                </span>
                <span className="text-text-secondary">{percent(s.approval_rate)}</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-surface-raised">
                <div
                  className={`h-full rounded-full bg-accent-light transition-all ${OPACITIES[i] ?? "opacity-40"}`}
                  style={{ width: `${Math.max(2, s.approval_rate * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
