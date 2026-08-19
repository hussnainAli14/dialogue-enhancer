import { STATUS_BADGE_CLASSES } from "@/lib/constants";
import { cn } from "@/lib/utils";

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        STATUS_BADGE_CLASSES[status] ?? "bg-gray-500/20 text-gray-300"
      )}
    >
      {status}
    </span>
  );
}
