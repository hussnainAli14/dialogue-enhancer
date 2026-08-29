import axios from "axios";
import type {
  ApiResponse,
  AuthUrlResponse,
  ConnectionLog,
  Conversation,
  ConversationDetail,
  ConversationFilters,
  ConversationListResponse,
  ConversationSubmitData,
  CommunityDiscoveryRun,
  CommunitySuggestion,
  DiscoveredPost,
  DiscoveryRun,
  DiscoverySettings,
  DiscoveryStatus,
  DiscoveryTopic,
  MonitoredPerson,
  Document,
  DocumentDetail,
  FeedbackSummary,
  KnowledgeListResponse,
  MonitoredCommunity,
  PlatformConnectionStatus,
  DraftListResponse,
  ResponseDraft,
  CleanupScan,
} from "./types";

const client = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  let response;
  try {
    response = await promise;
  } catch (err: unknown) {
    if (axios.isAxiosError(err)) {
      const envelope = err.response?.data as ApiResponse<T> | undefined;
      throw new Error(envelope?.error || err.message || "Network request failed");
    }
    throw new Error("Network request failed");
  }
  const envelope = response.data;
  if (!envelope.success) {
    throw new Error(envelope.error || "Request failed");
  }
  return envelope.data as T;
}

export const knowledgeApi = {
  getDocuments: () => unwrap<KnowledgeListResponse>(client.get("/knowledge/documents")),

  getDocument: (id: string) =>
    unwrap<DocumentDetail>(client.get(`/knowledge/documents/${id}`)),

  uploadDocument: (
    file: File,
    metadata: {
      title?: string;
      source_type?: string;
      author?: string;
      published_date?: string;
    }
  ) => {
    const form = new FormData();
    form.append("file", file);
    if (metadata.title) form.append("title", metadata.title);
    if (metadata.source_type) form.append("source_type", metadata.source_type);
    if (metadata.author) form.append("author", metadata.author);
    if (metadata.published_date) form.append("published_date", metadata.published_date);
    return unwrap<{
      document_id: string;
      status: string;
      duplicate?: boolean;
      existing_title?: string | null;
    }>(
      client.post("/knowledge/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    );
  },

  deleteDocument: (id: string) =>
    unwrap<{ deleted: boolean }>(client.delete(`/knowledge/documents/${id}`)),

  reindexDocument: (id: string) =>
    unwrap<{ status: string }>(client.post(`/knowledge/documents/${id}/reindex`)),
};

export const conversationsApi = {
  getConversations: (filters: ConversationFilters = {}) =>
    unwrap<ConversationListResponse>(
      client.get("/conversations", { params: filters })
    ),

  getConversation: (id: string) =>
    unwrap<ConversationDetail>(client.get(`/conversations/${id}`)),

  submitConversation: (data: ConversationSubmitData) =>
    unwrap<{ conversation_id: string; status: string }>(
      client.post("/conversations/submit", data)
    ),

  sourceStatus: (id: string) =>
    unwrap<{
      supported: boolean;
      connected?: boolean;
      exists: boolean | null;
      platform?: string;
      post_url?: string | null;
      error?: string;
      reason?: string;
    }>(client.get(`/conversations/${id}/source-status`)),

  generateDrafts: (id: string) =>
    unwrap<{ conversation_id: string; status: string }>(
      client.post(`/conversations/${id}/generate-drafts`)
    ),

  deleteConversation: (id: string) =>
    unwrap<{ deleted: boolean; conversation_id: string }>(
      client.delete(`/conversations/${id}`)
    ),

  // The cleanup scan makes one platform call per conversation, so it runs as a
  // background job: start it, poll for progress, then apply what it found.
  startCleanupScan: () =>
    unwrap<{ scan_id: string; status: string }>(
      client.post(`/conversations/cleanup-deleted`)
    ),

  getCleanupScan: (scanId: string) =>
    unwrap<CleanupScan>(client.get(`/conversations/cleanup-scans/${scanId}`)),

  applyCleanupScan: (scanId: string) =>
    unwrap<{ removed: boolean; deleted_count: number }>(
      client.post(`/conversations/cleanup-scans/${scanId}/apply`)
    ),
};

/** Broadcast so long-lived UI (the sidebar counters) can refresh immediately
 *  instead of waiting for its next poll. Fired from every draft mutation. */
export const DRAFTS_CHANGED_EVENT = "drafts:changed";

function notifyDraftsChanged<T>(result: T): T {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(DRAFTS_CHANGED_EVENT));
  }
  return result;
}

export const draftsApi = {
  approveDraft: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/approve`)).then(notifyDraftsChanged),

  editAndApproveDraft: (id: string, editedContent: string) =>
    unwrap<ResponseDraft>(
      client.post(`/drafts/${id}/edit-and-approve`, { edited_content: editedContent })
    ).then(notifyDraftsChanged),

  rejectDraft: (id: string, reason?: string) =>
    unwrap<ResponseDraft>(
      client.post(`/drafts/${id}/reject`, { rejection_reason: reason ?? null })
    ).then(notifyDraftsChanged),

  saveDraft: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/save`)).then(notifyDraftsChanged),

  markPosted: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/mark-posted`)).then(notifyDraftsChanged),

  postDraft: (id: string) =>
    unwrap<{ draft: ResponseDraft; platform_result: unknown }>(
      client.post(`/drafts/${id}/post`)
    ).then((r) => notifyDraftsChanged(r.draft)),

  approveAndPostDraft: (id: string) =>
    unwrap<{ draft: ResponseDraft; platform_result: unknown }>(
      client.post(`/drafts/${id}/approve-and-post`)
    ).then((r) => notifyDraftsChanged(r.draft)),

  unapproveDraft: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/unapprove`)).then(notifyDraftsChanged),

  getFeedbackSummary: () =>
    unwrap<FeedbackSummary>(client.get("/drafts/feedback-summary")),

  getDrafts: (params: {
    status?: string;
    platform?: string;
    page?: number;
    page_size?: number;
  } = {}) => unwrap<DraftListResponse>(client.get("/drafts", { params })),
};

export interface PostTarget {
  platform: string;
  connected: boolean;
  char_limit: number | null;
}

export interface PostResult {
  platform: string;
  success: boolean;
  result?: { url?: string; id?: string };
  error?: string;
}

export const postsApi = {
  getTargets: () =>
    unwrap<{ targets: PostTarget[] }>(client.get("/posts/targets")),

  pollReplies: () =>
    unwrap<{ checked: number; new_replies: number; skipped?: string }>(
      client.post("/posts/poll-replies")
    ),

  createPost: (
    platforms: string[],
    text: string,
    images: { file: File; alt: string }[] = []
  ) => {
    const form = new FormData();
    for (const p of platforms) form.append("platforms", p);
    form.append("text", text);
    for (const img of images) {
      form.append("images", img.file);
      form.append("alts", img.alt);
    }
    return unwrap<{ results: PostResult[]; posted: number; total: number }>(
      client.post("/posts", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    );
  },
};

export const connectionsApi = {
  getStatus: () =>
    unwrap<{ connections: PlatformConnectionStatus[] }>(
      client.get("/connections/status")
    ),

  getAuthUrl: (platform: string) =>
    unwrap<AuthUrlResponse>(client.get(`/connections/${platform}/auth-url`)),

  connectBluesky: (handle: string, appPassword: string) =>
    unwrap<{ platform: string; status: string; account_name: string | null }>(
      client.post("/connections/bluesky/connect", {
        handle,
        app_password: appPassword,
      })
    ),

  connectTelegram: () =>
    unwrap<{ platform: string; status: string; account_name: string | null }>(
      client.post("/connections/telegram/connect")
    ),

  validate: (platform: string) =>
    unwrap<{ platform: string; valid: boolean; account_name?: string | null; reason?: string }>(
      client.post(`/connections/${platform}/validate`)
    ),

  refresh: (platform: string) =>
    unwrap<{ platform: string; status: string }>(
      client.post(`/connections/${platform}/refresh`)
    ),

  disconnect: (platform: string) =>
    unwrap<{ platform: string; status: string }>(
      client.delete(`/connections/${platform}`)
    ),

  getLogs: (platform?: string) =>
    unwrap<{ logs: ConnectionLog[] }>(
      client.get("/connections/logs", { params: platform ? { platform } : {} })
    ),
};

export const discoveryApi = {
  getStatus: () => unwrap<DiscoveryStatus>(client.get("/discovery/status")),

  trigger: () =>
    unwrap<{ run_id: string; status: string }>(client.post("/discovery/trigger")),

  getRuns: (params: { status?: string; trigger_type?: string; page?: number } = {}) =>
    unwrap<{ page: number; page_size: number; total: number; runs: DiscoveryRun[] }>(
      client.get("/discovery/runs", { params })
    ),

  getRun: (id: string) =>
    unwrap<{ run: DiscoveryRun; posts: unknown[] }>(client.get(`/discovery/runs/${id}`)),

  getPosts: (
    params: {
      platform?: string;
      status?: string;
      min_relevance_score?: number;
      date_from?: string;
      date_to?: string;
      page?: number;
    } = {}
  ) =>
    unwrap<{ page: number; page_size: number; total: number; posts: DiscoveredPost[] }>(
      client.get("/discovery/posts", { params })
    ),

  submitPost: (id: string) =>
    unwrap<{ conversation_id: string; status: string }>(
      client.post(`/discovery/posts/${id}/submit`)
    ),

  getCommunities: () =>
    unwrap<{ communities: Record<string, MonitoredCommunity[]>; total: number }>(
      client.get("/discovery/communities")
    ),

  addCommunity: (data: {
    platform: string;
    community_id: string;
    community_name: string;
    keywords: string[];
    priority: number;
  }) => unwrap<{ community: MonitoredCommunity }>(client.post("/discovery/communities", data)),

  updateCommunity: (
    id: string,
    data: Partial<{ community_name: string; keywords: string[]; priority: number; is_active: boolean }>
  ) => unwrap<{ community: MonitoredCommunity }>(client.patch(`/discovery/communities/${id}`, data)),

  deleteCommunity: (id: string) =>
    unwrap<{ deleted: boolean }>(client.delete(`/discovery/communities/${id}`)),

  getSettings: () => unwrap<DiscoverySettings>(client.get("/discovery/settings")),

  updateSettings: (data: Partial<DiscoverySettings>) =>
    unwrap<DiscoverySettings>(client.post("/discovery/settings", data)),
};

export const communityApi = {
  // Topics
  getTopics: () => unwrap<{ topics: DiscoveryTopic[] }>(client.get("/community/topics")),
  addTopic: (data: { topic: string; keywords: string[]; description?: string }) =>
    unwrap<{ topic: DiscoveryTopic }>(client.post("/community/topics", data)),
  updateTopic: (id: string, data: Partial<DiscoveryTopic>) =>
    unwrap<{ topic: DiscoveryTopic }>(client.patch(`/community/topics/${id}`, data)),
  deleteTopic: (id: string) =>
    unwrap<{ deleted: boolean }>(client.delete(`/community/topics/${id}`)),

  // People
  getPeople: () => unwrap<{ people: MonitoredPerson[] }>(client.get("/community/people")),
  addPerson: (data: { name: string; description?: string; platform_handles: Record<string, string> }) =>
    unwrap<{ person: MonitoredPerson }>(client.post("/community/people", data)),
  updatePerson: (id: string, data: Partial<MonitoredPerson>) =>
    unwrap<{ person: MonitoredPerson }>(client.patch(`/community/people/${id}`, data)),
  deletePerson: (id: string) =>
    unwrap<{ deleted: boolean }>(client.delete(`/community/people/${id}`)),

  // Discovery
  discover: (body: { modes?: string[]; platforms?: string[] } = {}) =>
    unwrap<{ run_id: string; status: string }>(client.post("/community/discover", body)),
  getRuns: (page = 1) =>
    unwrap<{ page: number; total: number; runs: CommunityDiscoveryRun[] }>(
      client.get("/community/discover/runs", { params: { page } })
    ),

  // Suggestions
  getSuggestions: (params: { platform?: string; status?: string; min_score?: number } = {}) =>
    unwrap<{
      suggestions: CommunitySuggestion[];
      counts: { pending: number; approved: number; rejected: number };
    }>(client.get("/community/suggestions", { params })),
  approveSuggestion: (id: string, keywords?: string[]) =>
    unwrap<{ community: MonitoredCommunity | null }>(
      client.post(`/community/suggestions/${id}/approve`, keywords ? { keywords } : {})
    ),
  rejectSuggestion: (id: string, reason?: string) =>
    unwrap<{ suggestion: CommunitySuggestion }>(
      client.post(`/community/suggestions/${id}/reject`, { rejection_reason: reason ?? null })
    ),
  approveAll: (minScore: number) =>
    unwrap<{ approved: number }>(client.post("/community/suggestions/approve-all", { min_score: minScore })),
  rejectAll: (maxScore: number, reason?: string) =>
    unwrap<{ rejected: number }>(
      client.post("/community/suggestions/reject-all", { max_score: maxScore, rejection_reason: reason ?? null })
    ),

  // Monitored communities
  getMonitored: () =>
    unwrap<{ communities: Record<string, MonitoredCommunity[]>; total: number }>(
      client.get("/community/monitored")
    ),
  addMonitored: (data: {
    platform: string;
    community_id: string;
    community_name: string;
    keywords: string[];
    priority: number;
  }) => unwrap<{ community: MonitoredCommunity }>(client.post("/community/monitored", data)),
  updateMonitored: (
    id: string,
    data: Partial<{ keywords: string[]; priority: number; is_active: boolean }>
  ) => unwrap<{ community: MonitoredCommunity }>(client.patch(`/community/monitored/${id}`, data)),
  deleteMonitored: (id: string) =>
    unwrap<{ deleted: boolean }>(client.delete(`/community/monitored/${id}`)),
};
