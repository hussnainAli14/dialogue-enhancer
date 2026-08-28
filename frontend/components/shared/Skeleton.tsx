"use client";

import { cn } from "@/lib/utils";

/** A single shimmering placeholder block. Give it a width/height via className. */
export default function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse rounded bg-surface-raised", className)}
    />
  );
}
