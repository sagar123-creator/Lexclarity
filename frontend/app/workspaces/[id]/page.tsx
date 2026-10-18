"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  Send,
  FolderKanban,
  AlertTriangle,
  CalendarClock,
  ListChecks,
  Plus,
  X,
} from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { Card, Button, Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/Badge";
import { CitationChip } from "@/components/evidence/CitationChip";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import { api, ApiError } from "@/lib/api";
import type {
  WorkspaceDetail,
  DocumentSummaryCard,
  WorkspaceChatResponse,
  TimelineEntry,
  WorkspaceObligation,
  Citation,
} from "@/types";

export default function WorkspaceDetailPage() {
  const params = useParams<{ id: string }>();
  const workspaceId = params.id;

  const [workspace, setWorkspace] = useState<WorkspaceDetail | null>(null);
  const [allDocuments, setAllDocuments] = useState<DocumentSummaryCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [addDocId, setAddDocId] = useState("");

  // Search
  const [question, setQuestion] = useState("");
  const [searching, setSearching] = useState(false);
  const [chat, setChat] = useState<WorkspaceChatResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);

  // Timeline & obligations
  const [timeline, setTimeline] = useState<TimelineEntry[] | null>(null);
  const [obligations, setObligations] = useState<WorkspaceObligation[] | null>(null);

  const load = useCallback(async () => {
    try {
      const ws = await api.getWorkspace(workspaceId);
      setWorkspace(ws);
      setAllDocuments(await api.listDocuments());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the workspace.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    load();
  }, [load]);

  const loadTimeline = useCallback(async () => {
    try {
      setTimeline((await api.getWorkspaceTimeline(workspaceId)).timeline);
    } catch {
      setTimeline([]);
    }
  }, [workspaceId]);

  const loadObligations = useCallback(async () => {
    try {
      setObligations((await api.getWorkspaceObligations(workspaceId)).obligations);
    } catch {
      setObligations([]);
    }
  }, [workspaceId]);

  async function addDocument(e: React.FormEvent) {
    e.preventDefault();
    if (!addDocId) return;
    try {
      const ws = await api.addDocumentToWorkspace(workspaceId, addDocId);
      setWorkspace(ws);
      setAddDocId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add the document.");
    }
  }

  async function removeDocument(documentId: string) {
    try {
      const ws = await api.removeDocumentFromWorkspace(workspaceId, documentId);
      setWorkspace(ws);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the document.");
    }
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || searching) return;
    setSearching(true);
    setSearchError(null);
    try {
      setChat(await api.searchWorkspace(workspaceId, question.trim()));
    } catch (err) {
      setSearchError(
        err instanceof ApiError ? err.message : "Search failed. Please try again."
      );
    } finally {
      setSearching(false);
    }
  }

  function openEvidence(citation: Citation) {
    setEvidenceTarget({
      documentId: citation.document_id || "",
      pageNumber: citation.page_number,
      quote: citation.quote || citation.snippet,
      chunkId: citation.chunk_id,
      label: "Cited passage",
    });
  }

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col">
        <SiteHeader />
        <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
          <div className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" /> Loading workspace…
          </div>
        </main>
      </div>
    );
  }

  if (error && !workspace) {
    return (
      <div className="min-h-screen flex flex-col">
        <SiteHeader />
        <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
          <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
          <Link href="/workspaces" className="inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink mt-4">
            <ArrowLeft size={14} /> Back to workspaces
          </Link>
        </main>
      </div>
    );
  }

  const readyDocs = allDocuments.filter((d) => d.status === "ready");
  const wsDocIds = new Set((workspace?.documents || []).map((d) => d.id));
  const addable = readyDocs.filter((d) => !wsDocIds.has(d.id));

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
        <Link
          href="/workspaces"
          className="inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink mb-6"
        >
          <ArrowLeft size={14} /> All workspaces
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4 mb-2">
          <div>
            <div className="section-label mb-2">Workspace</div>
            <h1 className="font-serif text-2xl font-semibold">{workspace?.name}</h1>
            {workspace?.description && (
              <p className="mt-1 text-sm text-ink-faint">{workspace.description}</p>
            )}
          </div>
          <Badge>
            {(workspace?.documents || []).length} document
            {(workspace?.documents || []).length === 1 ? "" : "s"}
          </Badge>
        </div>

        {error && (
          <p className="my-4 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
        )}

        {/* Documents in this workspace */}
        <Card className="p-6 mt-4">
          <div className="flex items-center gap-2 mb-3">
            <FolderKanban size={15} className="text-navy" />
            <div className="section-label">Documents</div>
          </div>

          {(workspace?.documents || []).length === 0 && (
            <p className="text-sm text-ink-faint mb-3">
              No documents yet. Add analyzed documents below.
            </p>
          )}

          <div className="space-y-2">
            {(workspace?.documents || []).map((d) => (
              <div
                key={d.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line px-4 py-2.5"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <Link
                    href={`/documents/${d.id}`}
                    className="text-sm font-medium text-ink hover:text-navy truncate"
                  >
                    {d.filename}
                  </Link>
                  {d.document_type && <Badge>{d.document_type}</Badge>}
                  {d.overall_risk_level && (
                    <Badge
                      variant={
                        d.overall_risk_level === "High"
                          ? "high"
                          : d.overall_risk_level === "Medium"
                          ? "medium"
                          : d.overall_risk_level === "Low"
                          ? "low"
                          : "default"
                      }
                    >
                      {d.overall_risk_level}
                    </Badge>
                  )}
                </div>
                <button
                  onClick={() => removeDocument(d.id)}
                  className="rounded-sm border border-line p-1.5 text-ink-faint hover:border-risk-high hover:text-risk-high transition-colors"
                  aria-label={`Remove ${d.filename} from workspace`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>

          {addable.length > 0 && (
            <form onSubmit={addDocument} className="mt-4 flex flex-wrap items-center gap-2">
              <select
                value={addDocId}
                onChange={(e) => setAddDocId(e.target.value)}
                className="rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-navy flex-1 min-w-[200px]"
              >
                <option value="">Add an analyzed document…</option>
                {addable.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
              <Button type="submit" size="sm" disabled={!addDocId}>
                <Plus size={13} /> Add
              </Button>
            </form>
          )}
        </Card>

        <div className="mt-6">
          <Tabs defaultValue="search">
            <TabsList>
              <TabsTrigger value="search">Ask across documents</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="obligations">Obligations</TabsTrigger>
            </TabsList>

            <TabsContent value="search">
              <Card className="p-6">
                <form onSubmit={search} className="flex items-start gap-2">
                  <textarea
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    rows={2}
                    placeholder="Ask something across every document in this workspace…"
                    className="flex-1 rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy resize-none"
                  />
                  <Button type="submit" disabled={searching || !question.trim()}>
                    {searching ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                    Search
                  </Button>
                </form>

                {searchError && (
                  <p className="mt-3 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">
                    {searchError}
                  </p>
                )}

                {chat && (
                  <div className="mt-5 space-y-4">
                    <div className="rounded-lg bg-paper border border-line px-4 py-3 text-sm text-ink-soft leading-relaxed">
                      {chat.answer}
                    </div>

                    {chat.confidence === "low_confidence" && (
                      <p className="text-xs text-brass italic">
                        Low confidence — parts of this answer could not be fully verified.
                      </p>
                    )}
                    {chat.confidence === "not_found" && (
                      <p className="text-xs text-ink-faint italic">
                        Not found in these documents.
                      </p>
                    )}

                    {chat.conflicts.length > 0 && (
                      <div className="rounded-md border border-brass/30 bg-brass-soft px-4 py-3">
                        <div className="flex items-center gap-1.5 mb-2">
                          <AlertTriangle size={13} className="text-brass" />
                          <span className="section-label text-brass">
                            Conflicting statements ({chat.conflicts.length})
                          </span>
                        </div>
                        <div className="space-y-2">
                          {chat.conflicts.map((c, i) => (
                            <div key={i} className="text-sm">
                              <p className="font-medium text-ink">{c.topic}</p>
                              <p className="text-ink-soft">
                                <span className="font-mono text-xs text-ink-faint">{c.document_a}</span>{" "}
                                — {c.statement_a}
                              </p>
                              <p className="text-ink-soft">
                                <span className="font-mono text-xs text-ink-faint">{c.document_b}</span>{" "}
                                — {c.statement_b}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {chat.citations.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="section-label">Citations</div>
                        {chat.citations.map((c, i) => (
                          <CitationChip key={i} citation={c} onOpen={openEvidence} />
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {!chat && !searchError && !searching && (
                  <p className="mt-4 text-sm text-ink-faint">
                    Answers cite the specific document, page, and passage they come from. When two
                    documents disagree, the conflict is flagged rather than averaged away.
                  </p>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="timeline">
              <Card className="p-6">
                <div className="flex items-center gap-2 mb-3">
                  <CalendarClock size={15} className="text-navy" />
                  <div className="section-label">Cross-document timeline</div>
                </div>
                {!timeline && (
                  <div className="flex items-center gap-2 text-sm text-ink-faint">
                    <Loader2 size={14} className="animate-spin" /> Loading timeline…
                  </div>
                )}
                {timeline && timeline.length === 0 && (
                  <p className="text-sm text-ink-faint">No dates found across these documents.</p>
                )}
                {timeline && timeline.length > 0 && (
                  <div className="space-y-2">
                    {timeline.map((t, i) => (
                      <div
                        key={i}
                        className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-line px-4 py-2.5"
                      >
                        <span className="text-sm text-ink">{t.label}</span>
                        <div className="flex items-center gap-2">
                          {t.document_name && (
                            <span className="font-mono text-[11px] text-ink-faint">
                              {t.document_name}
                            </span>
                          )}
                          <span className="font-mono text-xs text-brass">
                            {String(t.date_value || t.date || "—")}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="obligations">
              <Card className="p-6">
                <div className="flex items-center gap-2 mb-3">
                  <ListChecks size={15} className="text-navy" />
                  <div className="section-label">Obligations across documents</div>
                </div>
                {!obligations && (
                  <div className="flex items-center gap-2 text-sm text-ink-faint">
                    <Loader2 size={14} className="animate-spin" /> Loading obligations…
                  </div>
                )}
                {obligations && obligations.length === 0 && (
                  <p className="text-sm text-ink-faint">No obligations found across these documents.</p>
                )}
                {obligations && obligations.length > 0 && (
                  <div className="space-y-2">
                    {obligations.map((o, i) => (
                      <div key={i} className="rounded-md border border-line px-4 py-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-sm font-medium text-ink">{o.party_name}</span>
                          {o.document_name && (
                            <span className="font-mono text-[11px] text-ink-faint">
                              {o.document_name}
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-ink-soft">{o.obligation_text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        <div className="mt-10">
          <Disclaimer />
        </div>
      </main>

      <EvidencePanel target={evidenceTarget} onClose={() => setEvidenceTarget(null)} />
    </div>
  );
}
