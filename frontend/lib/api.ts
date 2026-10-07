import type {
  DocumentSummaryCard,
  SummaryResponse,
  RiskItem,
  ClauseItem,
  ChatResponse,
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
};

export { ApiError };
