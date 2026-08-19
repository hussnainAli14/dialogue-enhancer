import { cn } from "@/lib/utils";

export default function RelevanceScore({ score }: { score: number | null }) {
  if (score === null || score === undefined) {
    return <span className="text-xs text-text-muted">No score</span>;
  }
  const pct = Math.round(score * 100);
  const barColor =
    score >= 0.75 ? "bg-success" : score >= 0.5 ? "bg-warning" : "bg-danger";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-raised">
        <div
          className={cn("h-full rounded-full transition-all", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-text-secondary">{pct}%</span>
    </div>
  );
}
