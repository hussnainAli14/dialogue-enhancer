"use client";

import { PLATFORMS, PLATFORM_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export default function PlatformFilter({
  active,
  onChange,
}: {
  active: string;
  onChange: (platform: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onChange("")}
        className={cn(
          "rounded-full px-3 py-1 text-xs transition-colors",
          active === ""
            ? "bg-accent text-text-primary"
            : "bg-surface-raised text-text-secondary hover:text-text-primary"
        )}
      >
        All
      </button>
      {PLATFORMS.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={cn(
            "rounded-full px-3 py-1 text-xs transition-colors",
            active === p
              ? "bg-accent text-text-primary"
              : "bg-surface-raised text-text-secondary hover:text-text-primary"
          )}
        >
          {PLATFORM_LABELS[p]}
        </button>
      ))}
    </div>
  );
}
