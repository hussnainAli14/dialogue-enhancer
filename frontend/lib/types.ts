export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  timestamp: string;
}

export type DocumentStatus = "processing" | "ready" | "error";

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  source_type: string | null;
  title: string | null;
  author: string | null;
  published_date: string | null;
  word_count: number | null;
  status: DocumentStatus;
  error_message: string | null;
  chunk_count: number;
  created_at: string;
}

export interface DocumentChunk {
  id: string;
  document_id?: string;
  chunk_index: number;
  content: string;
  token_count: number | null;
}

export interface DocumentDetail extends Document {
  chunks: DocumentChunk[];
}

export interface KnowledgeStats {
  total_documents: number;
  total_chunks: number;
  total_tokens: number;
}

export interface KnowledgeListResponse extends KnowledgeStats {
  documents: Document[];
}

export type AnalysisStatus =
  | "pending"
  | "analysed"
  | "skipped"
  | "error"
  | "reply_pending";

export interface Conversation {
  id: string;
  platform: string;
  post_url: string | null;
  post_author: string | null;
  original_post: string;
  central_topic?: string | null;
  full_thread: string | null;
  submitted_at: string;
  analysis_status: AnalysisStatus;
  draft_count: number;
  relevance_score: number | null;
  has_posted_reply?: boolean;
  source?: string;
  is_reply_to_me?: boolean;
  parent_post_url?: string | null;
}

export interface ConversationAnalysis {
  id: string;
  conversation_id: string;
  central_topic: string;
  key_tensions: string[];
  viewpoints_represented: string[];
  emotional_sensitivities: string;
  can_add_value: boolean;
  value_reasoning: string;
  participation_recommendation: "COMMENT" | "DO_NOT_COMMENT";
  recommendation_reason: string;
  relevance_score: number;
  created_at: string;
}

export type DraftStyle =
  | "insightful_contribution"
  | "facilitative_question"
  | "synthesis_of_viewpoints"
  | "constructive_challenge";

export type DraftStatus =
  | "pending"
  | "approved"
  | "edited"
  | "rejected"
  | "saved"
  | "posted";

export interface ResponseDraft {
  id: string;
  conversation_id: string;
  style: DraftStyle;
  content: string;
  value_explanation: string | null;
  source_document_titles: string[];
  include_link: boolean;
  suggested_link: string | null;
  status: DraftStatus;
  edited_content: string | null;
  rejection_reason: string | null;
  approved_at: string | null;
  posted_at: string | null;
  created_at: string;
}

export interface CleanupScan {
  scan_id: string;
  status: "running" | "completed" | "failed";
  checked: number;
  total: number;
  deleted: { id: string; platform: string; post_url: string | null }[];
  deleted_count: number;
  error: string | null;
  applied?: boolean;
}

export interface DraftWithConversation extends ResponseDraft {
  conversation: {
    id: string;
    platform: string;
    post_url: string;
    post_author: string;
    original_post: string;
    submitted_at: string;
  } | null;
}

export interface DraftListResponse {
  page: number;
  page_size: number;
  total: number;
  drafts: DraftWithConversation[];
}

export interface ConversationDetail extends Conversation {
  analysis: ConversationAnalysis | null;
  drafts: ResponseDraft[];
}

export interface ConversationListResponse {
  page: number;
  page_size: number;
  total: number;
  conversations: Conversation[];
}

export interface FeedbackSummary {
  total_drafts_generated: number;
  approval_rate: number;
  edit_rate: number;
  rejection_rate: number;
  most_common_rejection_reasons: Array<{ reason: string; count: number }>;
  best_performing_styles: Array<{
    style: string;
    total?: number;
    approval_rate: number;
  }>;
  average_edit_length_vs_original: number;
}

export interface ConversationSubmitData {
  platform: string;
  post_url?: string | null;
  post_author?: string | null;
  original_post: string;
  full_thread?: string | null;
}

export interface ConversationFilters {
  status?: string;
  platform?: string;
  page?: number;
  page_size?: number;
}

// ── Module 2 — platform connections ──────────────────
export type ConnectionStatus =
  | "connected"
  | "disconnected"
  | "error"
  | "expired";

export interface PlatformConnectionStatus {
  platform: string;
  status: ConnectionStatus;
  account_name: string | null;
  connected_at: string | null;
  last_used_at: string | null;
  last_error: string | null;
  method: "oauth" | "direct";
}

export interface AuthUrlResponse {
  platform: string;
  method: "oauth" | "credentials" | "bot_token";
  auth_url: string | null;
  instructions?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ConnectionLog {
  id: string;
  platform: string;
  event: string;
  message: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

// ── Module 4 — discovery ──────────────────────────────
export interface DiscoveryRun {
  id: string;
  trigger_type: "scheduled" | "manual" | "api";
  status: "running" | "completed" | "failed" | "partial";
  platforms_checked: string[] | null;
  posts_fetched: number;
  posts_scored: number;
  posts_submitted: number;
  posts_filtered: number;
  posts_duplicated: number;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface DiscoveryStatus {
  scheduler_running: boolean;
  is_enabled: boolean;
  next_run_at: string | null;
  schedule_interval_minutes: number;
  last_run: DiscoveryRun | null;
  today_submitted: number;
  today_limit: number;
  connected_platforms: string[];
  monitored_communities: number;
}

export interface DiscoveredPost {
  id: string;
  platform: string;
  post_id: string;
  post_url: string | null;
  author_name: string | null;
  title: string | null;
  content: string;
  thread_content: string | null;
  community_name: string | null;
  community_id: string | null;
  posted_at: string | null;
  fetched_at: string;
  engagement_score: number | null;
  relevance_score: number | null;
  analysis_score?: number | null;
  relevance_reasoning: string | null;
  status:
    | "fetched"
    | "scoring"
    | "scored"
    | "submitted"
    | "filtered_out"
    | "duplicate"
    | "error";
  conversation_id: string | null;
}

export interface MonitoredCommunity {
  id: string;
  platform: string;
  community_id: string;
  community_name: string;
  keywords: string[];
  is_active: boolean;
  priority: number;
  last_fetched_at: string | null;
  fetch_count: number;
  post_count: number;
}

export interface DiscoverySettings {
  is_enabled: boolean;
  schedule_interval_minutes: number;
  max_posts_per_run: number;
  max_conversations_per_day: number;
  min_relevance_score: number;
  scoring_batch_size: number;
  // Module 3 — community discovery
  community_discovery_enabled?: boolean;
  community_schedule_hours?: number;
  max_communities_per_platform?: number;
  min_community_relevance_score?: number;
  max_community_suggestions?: number;
}

// ── Module 3 — community discovery ────────────────────
export interface DiscoveryTopic {
  id: string;
  topic: string;
  keywords: string[];
  description: string | null;
  is_active: boolean;
}

export interface MonitoredPerson {
  id: string;
  name: string;
  description: string | null;
  platform_handles: Record<string, string>;
  is_active: boolean;
  last_checked_at: string | null;
}

export interface CommunitySuggestion {
  id: string;
  platform: string;
  community_id: string;
  community_name: string;
  community_url: string | null;
  description: string | null;
  member_count: number | null;
  activity_level: "high" | "medium" | "low" | "unknown" | null;
  discovery_method: "keyword" | "people_based" | "both";
  discovered_via_keywords: string[];
  discovered_via_people: string[];
  relevance_score: number | null;
  relevance_reasoning: string | null;
  suggested_keywords: string[];
  status: "pending" | "approved" | "rejected" | "already_monitoring";
}

export interface RunCommunity {
  platform: string;
  name: string;
  relevance_score: number | null;
  status: string;
}

export interface CommunityDiscoveryRun {
  id: string;
  trigger_type: string;
  discovery_modes: string[] | null;
  platforms_searched: string[] | null;
  communities_found: number;
  communities_new: number;
  communities_already_known: number;
  status: "running" | "completed" | "failed" | "partial";
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  communities?: RunCommunity[];
}
