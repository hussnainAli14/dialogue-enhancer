"use client";

import { Menu } from "lucide-react";
import { usePathname } from "next/navigation";

const TITLES: Record<string, string> = {
  "/feed": "Today's Feed",
  "/conversations": "Conversations",
  "/submit": "Submit Conversation",
  "/knowledge": "Knowledge Base",
  "/history": "Feedback History",
  "/community": "Community Manager",
  "/settings": "Settings",
};

export default function TopBar({ onOpenMobile }: { onOpenMobile: () => void }) {
  const pathname = usePathname();
  const title =
    Object.entries(TITLES).find(([path]) => pathname.startsWith(path))?.[1] ??
    "AI Dialogue Enhancer";

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-border bg-background/90 px-6 py-4 backdrop-blur">
      <button
        onClick={onOpenMobile}
        className="md:hidden text-text-secondary hover:text-text-primary"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>
      <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
    </header>
  );
}
