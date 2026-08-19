import { formatDistanceToNow, format, parseISO } from "date-fns";

export function timeAgo(iso: string): string {
  try {
    return formatDistanceToNow(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function formatDate(iso: string): string {
  try {
    return format(parseISO(iso), "d MMM yyyy, HH:mm");
  } catch {
    return iso;
  }
}

export function truncate(text: string | null | undefined, max: number): string {
  if (!text) return "";
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + "…";
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function isWithinLast24Hours(iso: string): boolean {
  try {
    return Date.now() - parseISO(iso).getTime() < 24 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}
