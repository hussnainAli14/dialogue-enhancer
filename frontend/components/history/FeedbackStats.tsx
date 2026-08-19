import { TrendingUp } from "lucide-react";
import type { FeedbackSummary } from "@/lib/types";
import { percent } from "@/lib/utils";

export default function FeedbackStats({ summary }: { summary: FeedbackSummary }) {
  const items = [
    {
      label: "Total Drafts Generated",
      value: String(summary.total_drafts_generated),
      accent: false,
    },
    {
      label: "Approval Rate",
      value: percent(summary.approval_rate),
      accent: true,
    },
    { label: "Edit Rate", value: percent(summary.edit_rate), accent: false },
    {
      label: "Rejection Rate",
      value: percent(summary.rejection_rate),
      accent: false,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-border bg-surface p-6"
        >
          <div className="flex items-center gap-2">
            <p className="text-2xl font-semibold text-text-primary">{item.value}</p>
            {item.accent && <TrendingUp className="h-4 w-4 text-success" />}
          </div>
          <p className="mt-1 text-xs text-text-muted">{item.label}</p>
        </div>
      ))}
    </div>
  );
}
