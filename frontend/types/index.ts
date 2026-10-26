export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "chunking"
  | "embedding"
  | "analyzing"
  | "ready"
  | "failed"
  | "stopped";

/** Statuses in which a pipeline run currently owns the document. */
export const ACTIVE_STATUSES: readonly DocumentStatus[] = [
  "uploaded",
  "extracting",
  "chunking",
  "embedding",
  "analyzing",
];

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

export type VerificationStatus =
  | "supported"
  | "contradicted"
  | "insufficient"
  | "needs_review";

export interface ObligationItem {
  id: string;
  party_name: string;
  obligation_text: string;
  page_number: number | null;
  section_reference: string | null;
  deadline_text?: string | null;
  trigger_event?: string | null;
  conditions?: string | null;
  verification_status?: VerificationStatus | string | null;
  evidence_quote?: string | null;
  task_status?: "pending" | "in_progress" | "completed";
}

export interface ImportantDateItem {
  id: string;
  label: string;
  date_value: string | null;
  description: string | null;
  page_number: number | null;
  normalized_date?: string | null;
  date_kind?: "explicit" | "inferred" | string | null;
  extraction_status?: "normalized" | "raw_only" | "uncertain" | string | null;
  evidence_quote?: string | null;
  verification_status?: VerificationStatus | string | null;
}

export interface ClauseItem {
  id: string;
  category: string;
  title: string;
  original_text: string | null;
  plain_explanation: string | null;
  page_number: number | null;
  section_reference: string | null;
  parties?: unknown;
  rights_obligations?: string | null;
  concerns?: string | null;
  verification_status?: VerificationStatus | string | null;
  evidence_quote?: string | null;
  source_chunk_id?: string | null;
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
  category?: string | null;
  affected_party?: string | null;
  evidence_quote?: string | null;
  suggested_action?: string | null;
  severity_rationale?: string | null;
  verification_status?: VerificationStatus | string | null;
  source_chunk_id?: string | null;
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
  chunk_id?: string | null;
  page_number?: number | null;
  section_reference?: string | null;
  snippet?: string | null;
  verified?: boolean | null;
  warning?: string | null;
  document_id?: string | null;
  quote?: string | null;
  quote_verified?: boolean | null;
  char_start?: number | null;
  char_end?: number | null;
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
  verification?: { overall?: string; claims?: unknown[] } | null;
}

export interface ConversationOut {
  id: string;
  document_id: string;
  messages: ChatMessage[];
}

// --- Evidence viewer ---

export interface DocumentPage {
  page_number: number;
  text: string;
  ocr_used: boolean;
}

export interface Chunk {
  id: string;
  document_id: string;
  chunk_index: number;
  page_number: number | null;
  section_heading: string | null;
  text: string;
}

// --- Trust & verification ---

export interface ClaimVerification {
  claim: string;
  status: VerificationStatus | string;
  method: "deterministic" | "nli" | "llm" | "combined" | "unavailable" | string;
  explanation: string;
  score?: number | null;
  evidence_chunk_id?: string | null;
  evidence_page?: number | null;
  evidence_excerpt?: string | null;
  notes: string[];
}

export interface VerifyClaimResponse {
  document_id: string;
  result: ClaimVerification;
}

// --- Action center ---

export interface ActionItem {
  id: string;
  document_id: string;
  source_type: string;
  source_id?: string | null;
  title: string;
  description?: string | null;
  evidence?: unknown;
  suggested_action?: string | null;
  priority: "High" | "Medium" | "Low" | string;
  priority_reason?: string | null;
  required_input?: string | null;
  status: "pending" | "in_progress" | "completed" | string;
  decision: "undecided" | "accepted" | "rejected" | "deferred" | string;
  created_at: string;
  updated_at: string;
}

export interface ActionItemUpdate {
  status?: string;
  decision?: string;
  note?: string;
}

// --- Document generator ---

export interface TemplateInfo {
  kind: string;
  title: string;
  description: string;
}

export interface Draft {
  id: string;
  document_id: string;
  action_item_id?: string | null;
  kind: string;
  title: string;
  content: string;
  placeholders?: string[] | null;
  source_refs?: unknown;
  is_ai_generated: boolean;
  edited_by_user: boolean;
  created_at: string;
  updated_at: string;
}

// --- Negotiation ---

export interface ClauseSuggestion {
  id: string;
  document_id: string;
  clause_id: string;
  original_text?: string | null;
  plain_explanation?: string | null;
  concern?: string | null;
  proposed_text?: string | null;
  rationale?: string | null;
  negotiation_points?: string[] | null;
  diff?: unknown;
  created_at: string;
}

// --- Deadline tracker ---

export interface Reminder {
  id: string;
  document_id: string;
  date_id?: string | null;
  title: string;
  due_date?: string | null;
  due_date_kind?: "explicit" | "inferred" | string | null;
  note?: string | null;
  status: "pending" | "completed" | "dismissed" | string;
  created_at: string;
  updated_at: string;
}

// --- Missing-clause checklist ---

export interface ChecklistItem {
  id: string;
  document_id: string;
  checklist_type: string;
  item_key: string;
  item_label: string;
  state: "detected" | "not_detected" | "unclear" | "not_applicable" | string;
  explanation?: string | null;
  evidence_quote?: string | null;
  page_number?: number | null;
  created_at: string;
}

// --- Contract comparison ---

export interface WordDiffToken {
  text: string;
  type?: "same" | "added" | "removed" | string;
}

export interface ClauseDiffEntry {
  category: string;
  change: "added" | "removed" | "modified" | "unchanged" | "similar" | string;
  clause_a?: ClauseRef | null;
  clause_b?: ClauseRef | null;
  similarity?: number;
  diff?: { tokens?: WordDiffToken[]; similarity?: number } | null;
  key_values_a?: Record<string, unknown>;
  key_values_b?: Record<string, unknown>;
}

export interface ClauseRef {
  id: string;
  category: string;
  title: string;
  original_text?: string | null;
  page_number?: number | null;
  section_reference?: string | null;
  verification_status?: string | null;
}

export interface RiskDelta {
  categories_added: string[];
  categories_removed: string[];
  overall_level_a: string;
  overall_level_b: string;
  high_count_a: number;
  high_count_b: number;
  new_findings: { title: string; category: string; level: string; page_number?: number | null }[];
}

export interface ComparisonSummary {
  document_a: { id: string; filename: string; document_type?: string | null };
  document_b: { id: string; filename: string; document_type?: string | null };
  clause_changes: ClauseDiffEntry[];
  risk_delta: RiskDelta;
  summary?: string | null;
  summary_disclaimer?: string | null;
}

export interface Comparison {
  id: string;
  document_a_id: string;
  document_b_id: string;
  status: string;
  summary?: ComparisonSummary | null;
  created_at: string;
}

// --- Action plan ---

export interface PlanItem {
  action_id: string;
  title: string;
  priority: string;
  priority_reason?: string | null;
  related_finding_type: string;
  suggested_action?: string | null;
  required_input?: string | null;
  status: string;
  decision: string;
  evidence?: unknown;
}

export interface ActionPlan {
  document_id: string;
  generated_at: string;
  items: PlanItem[];
  disclaimer: string;
}

