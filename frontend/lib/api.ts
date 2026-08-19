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
  DiscoveredPost,
  DiscoveryRun,
  DiscoverySettings,
  DiscoveryStatus,
  Document,
  DocumentDetail,
  FeedbackSummary,
  KnowledgeListResponse,
  MonitoredCommunity,
  PlatformConnectionStatus,
  ResponseDraft,
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

  deleteConversation: (id: string) =>
    unwrap<{ deleted: boolean; conversation_id: string }>(
      client.delete(`/conversations/${id}`)
    ),

  cleanupDeleted: (dryRun: boolean) =>
    unwrap<{
      checked: number;
      deleted: { id: string; platform: string; post_url: string | null }[];
      deleted_count: number;
      removed?: boolean;
      dry_run: boolean;
    }>(client.post(`/conversations/cleanup-deleted`, null, { params: { dry_run: dryRun } })),
};

export const draftsApi = {
  approveDraft: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/approve`)),

  editAndApproveDraft: (id: string, editedContent: string) =>
    unwrap<ResponseDraft>(
      client.post(`/drafts/${id}/edit-and-approve`, { edited_content: editedContent })
    ),

  rejectDraft: (id: string, reason?: string) =>
    unwrap<ResponseDraft>(
      client.post(`/drafts/${id}/reject`, { rejection_reason: reason ?? null })
    ),

  saveDraft: (id: string) => unwrap<ResponseDraft>(client.post(`/drafts/${id}/save`)),

  markPosted: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/mark-posted`)),

  postDraft: (id: string) =>
    unwrap<{ draft: ResponseDraft; platform_result: unknown }>(
      client.post(`/drafts/${id}/post`)
    ).then((r) => r.draft),

  approveAndPostDraft: (id: string) =>
    unwrap<{ draft: ResponseDraft; platform_result: unknown }>(
      client.post(`/drafts/${id}/approve-and-post`)
    ).then((r) => r.draft),

  unapproveDraft: (id: string) =>
    unwrap<ResponseDraft>(client.post(`/drafts/${id}/unapprove`)),

  getFeedbackSummary: () =>
    unwrap<FeedbackSummary>(client.get("/drafts/feedback-summary")),
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
