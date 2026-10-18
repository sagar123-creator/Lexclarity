import type {
  DocumentSummaryCard,
  SummaryResponse,
  RiskItem,
  ClauseItem,
  ChatResponse,
  ConversationOut,
  DocumentPage,
  Chunk,
  VerifyClaimResponse,
  ActionItem,
  ActionItemUpdate,
  TemplateInfo,
  Draft,
  ClauseSuggestion,
  Reminder,
  ChecklistItem,
  Comparison,
  ComparisonSummary,
  Workspace,
  WorkspaceDetail,
  WorkspaceChatResponse,
  TimelineEntry,
  WorkspaceObligation,
  ActionPlan,
  EvaluationRun,
  EvaluationStatus,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse failure
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // --- Core analysis ---
  uploadDocument: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ document: DocumentSummaryCard; message: string }>(
      "/api/documents/upload",
      { method: "POST", body: formData }
    );
  },

  listDocuments: () => request<DocumentSummaryCard[]>("/api/documents"),

  getDocument: (id: string) => request<DocumentSummaryCard>(`/api/documents/${id}`),

  getSummary: (id: string) => request<SummaryResponse>(`/api/documents/${id}/summary`),

  getRisks: (id: string) => request<RiskItem[]>(`/api/documents/${id}/risks`),

  getClauses: (id: string) => request<ClauseItem[]>(`/api/documents/${id}/clauses`),

  retryAnalysis: (id: string) =>
    request<{ document_id: string; status: string; error_message?: string }>(
      `/api/documents/${id}/analyze`,
      { method: "POST" }
    ),

  sendChatMessage: (id: string, message: string, conversationId?: string) =>
    request<ChatResponse>(`/api/documents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({
        document_id: id,
        message,
        conversation_id: conversationId,
      }),
    }),

  getConversation: (id: string, conversationId: string) =>
    request<ConversationOut>(`/api/documents/${id}/conversations/${conversationId}`),

  // --- Evidence viewer ---
  getPages: (id: string) => request<DocumentPage[]>(`/api/documents/${id}/pages`),

  getPage: (id: string, pageNumber: number) =>
    request<DocumentPage>(`/api/documents/${id}/pages/${pageNumber}`),

  getChunk: (id: string, chunkId: string) =>
    request<Chunk>(`/api/documents/${id}/chunks/${chunkId}`),

  // --- Trust & verification ---
  verifyClaim: (id: string, claim: string, chunkId?: string) =>
    request<VerifyClaimResponse>(`/api/documents/${id}/verify-claim`, {
      method: "POST",
      body: JSON.stringify({ claim, chunk_id: chunkId }),
    }),

  // --- Action center ---
  getActions: (id: string) => request<ActionItem[]>(`/api/documents/${id}/actions`),

  generateActions: (id: string) =>
    request<ActionItem[]>(`/api/documents/${id}/actions/generate`, { method: "POST" }),

  getAction: (actionId: string) => request<ActionItem>(`/api/actions/${actionId}`),

  updateAction: (actionId: string, update: ActionItemUpdate) =>
    request<ActionItem>(`/api/actions/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),

  // --- Action plan ---
  getPlan: (id: string) => request<ActionPlan>(`/api/documents/${id}/plan`),

  // --- Document generator ---
  listTemplates: () => request<TemplateInfo[]>("/api/templates"),

  createDraft: (
    id: string,
    body: { kind: string; source_ids?: string[]; action_item_id?: string; user_instructions?: string }
  ) => request<Draft>(`/api/documents/${id}/drafts`, {
    method: "POST",
    body: JSON.stringify(body),
  }),

  listDrafts: (id: string) => request<Draft[]>(`/api/documents/${id}/drafts`),

  getDraft: (draftId: string) => request<Draft>(`/api/drafts/${draftId}`),

  updateDraft: (draftId: string, update: { title?: string; content?: string }) =>
    request<Draft>(`/api/drafts/${draftId}`, {
      method: "PUT",
      body: JSON.stringify(update),
    }),

  exportDraftUrl: (draftId: string) => `${API_BASE}/api/drafts/${draftId}/export`,

  // --- Negotiation assistant ---
  negotiate: (id: string, clauseId: string) =>
    request<ClauseSuggestion>(`/api/documents/${id}/negotiate`, {
      method: "POST",
      body: JSON.stringify({ clause_id: clauseId }),
    }),

  listSuggestions: (id: string) =>
    request<ClauseSuggestion[]>(`/api/documents/${id}/negotiate`),

  // --- Deadline tracker ---
  getReminders: (id: string) => request<Reminder[]>(`/api/documents/${id}/reminders`),

  createReminder: (
    id: string,
    body: { date_id?: string; title?: string; due_date?: string; note?: string }
  ) => request<Reminder>(`/api/documents/${id}/reminders`, {
    method: "POST",
    body: JSON.stringify(body),
  }),

  updateReminder: (
    reminderId: string,
    update: { title?: string; due_date?: string; note?: string; status?: string }
  ) =>
    request<Reminder>(`/api/reminders/${reminderId}`, {
      method: "PATCH",
      body: JSON.stringify(update),
    }),

  deleteReminder: (reminderId: string) =>
    request<void>(`/api/reminders/${reminderId}`, { method: "DELETE" }),

  updateObligation: (obligationId: string, taskStatus: string) =>
    request<import("@/types").ObligationItem>(`/api/obligations/${obligationId}`, {
      method: "PATCH",
      body: JSON.stringify({ task_status: taskStatus }),
    }),

  // --- Missing-clause checklist ---
  getChecklist: (id: string) => request<ChecklistItem[]>(`/api/documents/${id}/checklist`),

  runChecklist: (id: string) =>
    request<ChecklistItem[]>(`/api/documents/${id}/checklist/run`, { method: "POST" }),

  // --- Contract comparison ---
  compare: (documentAId: string, documentBId: string) =>
    request<Comparison>("/api/compare", {
      method: "POST",
      body: JSON.stringify({ document_a_id: documentAId, document_b_id: documentBId }),
    }),

  listComparisons: () => request<Comparison[]>("/api/compare"),

  getComparison: (comparisonId: string) =>
    request<Comparison>(`/api/compare/${comparisonId}`),

  // --- Workspaces ---
  listWorkspaces: () => request<Workspace[]>("/api/workspaces"),

  createWorkspace: (name: string, description?: string) =>
    request<Workspace>("/api/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),

  getWorkspace: (workspaceId: string) =>
    request<WorkspaceDetail>(`/api/workspaces/${workspaceId}`),

  addDocumentToWorkspace: (workspaceId: string, documentId: string) =>
    request<WorkspaceDetail>(`/api/workspaces/${workspaceId}/documents`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId }),
    }),

  removeDocumentFromWorkspace: (workspaceId: string, documentId: string) =>
    request<WorkspaceDetail>(`/api/workspaces/${workspaceId}/documents/${documentId}`, {
      method: "DELETE",
    }),

  searchWorkspace: (workspaceId: string, message: string) =>
    request<WorkspaceChatResponse>(`/api/workspaces/${workspaceId}/search`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  getWorkspaceTimeline: (workspaceId: string) =>
    request<{ timeline: TimelineEntry[] }>(`/api/workspaces/${workspaceId}/timeline`),

  getWorkspaceObligations: (workspaceId: string) =>
    request<{ obligations: WorkspaceObligation[] }>(
      `/api/workspaces/${workspaceId}/obligations`
    ),

  // --- Evaluation ---
  getEvaluationStatus: () => request<EvaluationStatus>("/api/evaluation/status"),

  listEvaluationRuns: () => request<EvaluationRun[]>("/api/evaluation/runs"),

  runEvaluation: () => request<EvaluationRun>("/api/evaluation/run", { method: "POST" }),
};

export { ApiError, API_BASE };
export type { ComparisonSummary };
