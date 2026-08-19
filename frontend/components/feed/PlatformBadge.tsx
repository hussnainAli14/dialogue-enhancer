import { PLATFORM_BADGE_CLASSES, PLATFORM_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export default function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-0.5 text-xs font-medium",
        PLATFORM_BADGE_CLASSES[platform] ?? "bg-gray-500/20 text-gray-300"
      )}
    >
      {PLATFORM_LABELS[platform] ?? platform}
    </span>
  );
}
