import { FileText } from "lucide-react";
import { truncate } from "@/lib/utils";

export default function SourceBadge({ title }: { title: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-text-secondary">
      <FileText className="h-3 w-3" />
      {truncate(title, 30)}
    </span>
  );
}
