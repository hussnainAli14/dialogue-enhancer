import { Cpu, FileText, Layers } from "lucide-react";
import type { KnowledgeStats } from "@/lib/types";

export default function StatsBar({ stats }: { stats: KnowledgeStats }) {
  const items = [
    { icon: FileText, label: "Total Documents", value: stats.total_documents },
    { icon: Layers, label: "Total Chunks", value: stats.total_chunks },
    { icon: Cpu, label: "Estimated Total Tokens", value: stats.total_tokens.toLocaleString() },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {items.map(({ icon: Icon, label, value }) => (
        <div
          key={label}
          className="flex items-center gap-4 rounded-xl border border-border bg-surface p-6"
        >
          <Icon className="h-6 w-6 text-accent-light" />
          <div>
            <p className="text-xl font-semibold text-text-primary">{value}</p>
            <p className="text-xs text-text-muted">{label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
