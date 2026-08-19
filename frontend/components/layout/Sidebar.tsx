"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  Database,
  Home,
  MessageSquare,
  Plug,
  PlusCircle,
  Radar,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { conversationsApi, discoveryApi, knowledgeApi } from "@/lib/api";
import type { DiscoveryStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/feed", label: "Today's Feed", icon: Home, badge: true },
  { href: "/conversations", label: "Conversations", icon: MessageSquare },
  { href: "/discovery", label: "Discovery", icon: Radar },
  { href: "/submit", label: "Submit", icon: PlusCircle },
  { href: "/knowledge", label: "Knowledge Base", icon: Database },
  { href: "/history", label: "Feedback History", icon: BarChart3 },
  { href: "/community", label: "Community Manager", icon: Users },
  { href: "/settings#connections", label: "Connections", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];

interface SidebarProps {
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

function nextRunLabel(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "shortly";
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "in <1 min";
  if (mins < 60) return `in ${mins} min`;
  return `in ${Math.round(mins / 60)} h`;
}

export default function Sidebar({ mobileOpen, onCloseMobile }: SidebarProps) {
  const pathname = usePathname();
  const [awaitingCount, setAwaitingCount] = useState(0);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveryStatus | null>(null);

  useEffect(() => {
    let mounted = true;
    const check = async () => {
      try {
        const [convs] = await Promise.all([
          conversationsApi.getConversations({ status: "analysed", page_size: 100 }),
          knowledgeApi.getDocuments(),
        ]);
        if (!mounted) return;
        setApiOk(true);
        setAwaitingCount(
          convs.conversations.filter((c) => c.draft_count > 0).length
        );
      } catch {
        if (mounted) setApiOk(false);
      }
      try {
        const d = await discoveryApi.getStatus();
        if (mounted) setDiscovery(d);
      } catch {
        if (mounted) setDiscovery(null);
      }
    };
    check();
    const interval = setInterval(check, 60000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const content = (
    <div className="flex h-full flex-col">
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-accent-light shrink-0" />
            <span className="font-semibold text-accent-light text-sm md:hidden lg:inline">
              AI Dialogue Enhancer
            </span>
          </div>
          <button
            onClick={onCloseMobile}
            className="md:hidden text-text-secondary hover:text-text-primary"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mt-1 text-xs text-text-muted md:hidden lg:block">
          Quality over quantity.
        </p>
      </div>

      <nav className="flex-1 py-4">
        {NAV_ITEMS.map((item) => {
          const active = pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onCloseMobile}
              className={cn(
                "flex items-center gap-3 px-6 py-2.5 text-sm transition-colors border-l-4",
                active
                  ? "border-accent bg-surface-raised text-accent-light"
                  : "border-transparent text-text-secondary hover:bg-surface-raised hover:text-text-primary"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="md:hidden lg:inline">{item.label}</span>
              {item.badge && awaitingCount > 0 && (
                <span className="ml-auto rounded-full bg-accent px-2 py-0.5 text-xs text-text-primary md:hidden lg:inline">
                  {awaitingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-6 space-y-3">
        {/* Discovery status */}
        <div className="flex items-start gap-2 text-xs">
          <span
            className={cn(
              "mt-0.5 h-2 w-2 rounded-full shrink-0",
              !discovery
                ? "bg-danger"
                : discovery.is_enabled && discovery.scheduler_running
                  ? "bg-accent-light"
                  : "bg-warning"
            )}
          />
          <div className="md:hidden lg:block">
            <span
              className={cn(
                !discovery
                  ? "text-danger"
                  : discovery.is_enabled && discovery.scheduler_running
                    ? "text-accent-light"
                    : "text-warning"
              )}
            >
              {!discovery
                ? "Scheduler Stopped"
                : !discovery.is_enabled
                  ? "Discovery Paused"
                  : "Discovery Running"}
            </span>
            {discovery?.is_enabled && discovery.next_run_at && (
              <p className="text-text-muted">Next run {nextRunLabel(discovery.next_run_at)}</p>
            )}
          </div>
        </div>

        {/* API status */}
        <div className="flex items-center gap-2 text-xs">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              apiOk === null
                ? "bg-text-muted"
                : apiOk
                  ? "bg-success"
                  : "bg-danger"
            )}
          />
          <span
            className={cn(
              "md:hidden lg:inline",
              apiOk ? "text-success" : apiOk === false ? "text-danger" : "text-text-muted"
            )}
          >
            {apiOk === null
              ? "Checking API…"
              : apiOk
                ? "API Connected"
                : "API Unreachable"}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop / tablet sidebar */}
      <aside className="hidden md:block fixed inset-y-0 left-0 z-40 md:w-[60px] lg:w-[240px] border-r border-border bg-surface">
        {content}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={onCloseMobile} />
          <aside className="absolute inset-y-0 left-0 w-[260px] border-r border-border bg-surface">
            {content}
          </aside>
        </div>
      )}
    </>
  );
}
