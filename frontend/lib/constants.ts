export const PLATFORMS = [
  "reddit",
  "bluesky",
  "mastodon",
  "discord",
  "telegram",
  "threads",
  "youtube",
  "facebook",
  "linkedin",
  "instagram",
  "twitter",
] as const;

export const PLATFORM_LABELS: Record<string, string> = {
  reddit: "Reddit",
  bluesky: "Bluesky",
  mastodon: "Mastodon",
  discord: "Discord",
  telegram: "Telegram",
  threads: "Threads",
  youtube: "YouTube",
  facebook: "Facebook",
  linkedin: "LinkedIn",
  instagram: "Instagram",
  twitter: "X (Twitter)",
};

export const PLATFORM_BADGE_CLASSES: Record<string, string> = {
  reddit: "bg-orange-500/20 text-orange-400",
  bluesky: "bg-sky-500/20 text-sky-400",
  mastodon: "bg-purple-500/20 text-purple-400",
  discord: "bg-indigo-500/20 text-indigo-400",
  telegram: "bg-blue-400/20 text-blue-300",
  threads: "bg-gray-500/20 text-gray-300",
  youtube: "bg-red-500/20 text-red-400",
  facebook: "bg-blue-600/20 text-blue-400",
  linkedin: "bg-blue-700/20 text-blue-300",
  instagram: "bg-pink-500/20 text-pink-400",
  twitter: "bg-sky-400/20 text-sky-300",
};

export const STATUS_BADGE_CLASSES: Record<string, string> = {
  pending: "bg-warning/20 text-warning",
  approved: "bg-success/20 text-success",
  edited: "bg-success/20 text-success",
  rejected: "bg-danger/20 text-danger",
  saved: "bg-accent/20 text-accent-light",
  posted: "bg-success/20 text-success border border-success/40",
  skipped: "bg-info/20 text-info",
  error: "bg-danger/20 text-danger",
  analysed: "bg-success/20 text-success",
  processing: "bg-warning/20 text-warning",
  ready: "bg-success/20 text-success",
};

export const STYLE_LABELS: Record<string, string> = {
  insightful_contribution: "Insightful Contribution",
  facilitative_question: "Facilitative Question",
  synthesis_of_viewpoints: "Synthesis of Viewpoints",
  constructive_challenge: "Constructive Challenge",
};

export const SOURCE_TYPES = [
  "blog",
  "article",
  "book",
  "newsletter",
  "talk",
  "workshop",
  "other",
] as const;

export const REJECTION_REASONS = [
  "Too generic",
  "Off topic",
  "Wrong tone",
  "Too promotional",
  "Nothing to add",
] as const;

export const ACCEPTED_FILE_TYPES = [".pdf", ".docx", ".doc", ".html", ".txt", ".md"];
