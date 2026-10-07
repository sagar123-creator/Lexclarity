export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "chunking"
  | "embedding"
  | "analyzing"
  | "ready"
  | "failed";

export interface DocumentSummaryCard {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  page_count: number | null;
  document_type: string | null;
  overall_risk_level: "High" | "Medium" | "Low" | "Unknown" | null;
  created_at: string;
  updated_at: string;
}

export interface EntityItem {
  id: string;
  name: string;
  role: string | null;
  entity_type: string | null;
}

export interface ObligationItem {
  id: string;
  party_name: string;
  obligation_text: string;
  page_number: number | null;
  section_reference: string | null;
}

export interface ImportantDateItem {
  id: string;
  label: string;
  date_value: string | null;
  description: string | null;
  page_number: number | null;
}

export interface ClauseItem {
  id: string;
  category: string;
  title: string;
  original_text: string | null;
  plain_explanation: string | null;
  page_number: number | null;
  section_reference: string | null;
}

export interface RiskItem {
  id: string;
  level: "High" | "Medium" | "Low";
  title: string;
  description: string;
  why_it_matters: string;
  plain_explanation: string | null;
  page_number: number | null;
  section_reference: string | null;
}

export interface SummaryResponse {
  executive_summary: string | null;
  document_type: string | null;
  plain_english_overview: string | null;
  entities: EntityItem[];
  obligations: ObligationItem[];
  important_dates: ImportantDateItem[];
}

export interface Citation {
  chunk_id: string | null;
  page_number: number | null;
  section_reference: string | null;
  snippet: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[] | null;
  confidence?: string | null;
  created_at?: string;
}

export interface ChatResponse {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  confidence: "answered" | "not_found" | "low_confidence";
}
