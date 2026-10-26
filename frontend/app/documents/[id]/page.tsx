"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle, RotateCcw, Loader2, XCircle } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { SectionNav, SectionKey } from "@/components/layout/SectionNav";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/primitives";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/primitives";
import { OverviewTab } from "@/components/analysis/OverviewTab";
import { RisksTab } from "@/components/analysis/RisksTab";
import { ClausesTab } from "@/components/analysis/ClausesTab";
import { ObligationsTab } from "@/components/analysis/ObligationsTab";
import { DatesTab } from "@/components/analysis/DatesTab";
import { EvidenceTab } from "@/components/analysis/EvidenceTab";
import { ChatPanel } from "@/components/chatbot/ChatPanel";
import { ActionCenterTab } from "@/components/action/ActionCenterTab";
import { NegotiationTab } from "@/components/action/NegotiationTab";
import { GeneratorTab } from "@/components/action/GeneratorTab";
import { ComparisonTab } from "@/components/action/ComparisonTab";
import { DeadlinesTab } from "@/components/action/DeadlinesTab";
import { ComplianceTab } from "@/components/action/ComplianceTab";
import { PlanTab } from "@/components/action/PlanTab";
import { api, ApiError } from "@/lib/api";
import type {
  DocumentSummaryCard,
  SummaryResponse,
  RiskItem,
  ClauseItem,
  ObligationItem,
  ActionItem,
} from "@/types";
import Link from "next/link";

export default function DocumentAnalysisPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const documentId = params.id;

  const [doc, setDoc] = useState<DocumentSummaryCard | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [risks, setRisks] = useState<RiskItem[] | null>(null);
  const [clauses, setClauses] = useState<ClauseItem[] | null>(null);
  const [documents, setDocuments] = useState<DocumentSummaryCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Bumped after a resumed analysis to re-run the loader in place.
  const [reloadToken, setReloadToken] = useState(0);
  const [resuming, setResuming] = useState(false);

  const [section, setSection] = useState<SectionKey>("analyze");
  const [analyzeTab, setAnalyzeTab] = useState("summary");
  const [actTab, setActTab] = useState("actions");

  // Cross-tab handoffs
  const [focusClauseId, setFocusClauseId] = useState<string | null>(null);
  const [draftActionId, setDraftActionId] = useState<string | null>(null);
  const [draftInstructions, setDraftInstructions] = useState<string | null>(null);
  const [checklistToken, setChecklistToken] = useState(0);
  const [deadlineToken, setDeadlineToken] = useState(0);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const document = await api.getDocument(documentId);
        if (!active) return;
        setDoc(document);

        // A stopped document stays readable: it keeps whatever sections the
        // completed stages produced (the page shows a banner offering to
        // resume the rest).
        if (document.status === "ready" || document.status === "stopped") {
          const [s, r, c] = await Promise.all([
            api.getSummary(documentId),
            api.getRisks(documentId),
            api.getClauses(documentId),
          ]);
          if (!active) return;
          setSummary(s);
          setRisks(r);
          setClauses(c);
          api
            .listDocuments()
            .then((list) => active && setDocuments(list))
            .catch(() => {});
        } else if (document.status === "failed") {
          setError(document.error_message || "Document processing failed.");
        } else {
          router.push("/upload");
          return;
        }
      } catch (e) {
        if (active) setError(e instanceof ApiError ? e.message : "Failed to load document.");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [documentId, router, reloadToken]);

  async function handleRetry() {
    setError(null);
    setLoading(true);
    try {
      await api.retryAnalysis(documentId);
      router.push("/upload");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Retry failed.");
      setLoading(false);
    }
  }

  /**
   * Resume a stopped analysis. `POST /analyze` runs the pipeline to completion
   * before it returns, so when it resolves the document is either finished or
   * failed — either way the loader above re-reads the authoritative state.
   */
  async function handleResume() {
    setResuming(true);
    setError(null);
    try {
      await api.retryAnalysis(documentId);
      setReloadToken((token) => token + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Resume failed.");
    } finally {
      setResuming(false);
    }
  }

  function handleObligationChanged(updated: ObligationItem) {
    setSummary((prev) =>
      prev
        ? {
            ...prev,
            obligations: prev.obligations.map((o) => (o.id === updated.id ? updated : o)),
          }
        : prev
    );
  }

  function negotiateClause(clause: ClauseItem) {
    setFocusClauseId(clause.id);
    setActTab("negotiation");
    setSection("act");
  }

  function draftFromAction(action: ActionItem) {
    setDraftActionId(action.id);
    setDraftInstructions(
      action.suggested_action
        ? `Address this action: ${action.title}. Suggested step: ${action.suggested_action}`
        : `Address this action: ${action.title}`
    );
    setActTab("generator");
  }

  function draftFromSuggestion() {
    setActTab("generator");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
        <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink mb-6">
          <ArrowLeft size={14} /> Back to dashboard
        </Link>

        {loading && (
          <div className="space-y-4">
            <div className="h-8 w-1/3 rounded bg-line/50 animate-pulse" />
            <div className="h-40 rounded-lg bg-line/30 animate-pulse" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-lg border border-risk-high/20 bg-risk-highBg p-6">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="text-risk-high mt-0.5 shrink-0" />
              <div className="flex-1">
                <p className="font-medium text-risk-high mb-1">Couldn&apos;t load this document</p>
                <p className="text-sm text-ink-soft">{error}</p>
                <Button variant="secondary" size="sm" className="mt-4" onClick={handleRetry}>
                  <RotateCcw size={14} /> Retry analysis
                </Button>
              </div>
            </div>
          </div>
        )}

        {!loading && !error && doc && summary && risks && clauses && (
          <>
            <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
              <div>
                <div className="section-label mb-2">Document</div>
                <h1 className="font-serif text-2xl font-semibold">{doc.filename}</h1>
              </div>
              <div className="flex items-center gap-2">
                {doc.document_type && <Badge>{doc.document_type}</Badge>}
                {doc.overall_risk_level && (
                  <Badge variant={riskVariant(doc.overall_risk_level)}>
                    {doc.overall_risk_level} Risk
                  </Badge>
                )}
              </div>
            </div>

            {doc.status === "stopped" && (
              <div className="mb-6 rounded-lg border border-line bg-paper p-4">
                <div className="flex flex-wrap items-start gap-3">
                  <XCircle size={18} className="text-ink-soft mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-[220px]">
                    <p className="text-sm font-medium text-ink mb-1">
                      Processing was stopped
                    </p>
                    <p className="text-sm text-ink-soft">
                      {doc.error_message ||
                        "Analysis was stopped before it finished."}{" "}
                      Sections shown here are complete; the rest can be finished with
                      a resume.
                    </p>
                  </div>
                  <Button size="sm" onClick={handleResume} disabled={resuming}>
                    {resuming ? (
                      <>
                        <Loader2 size={14} className="animate-spin" /> Re-running…
                      </>
                    ) : (
                      <>
                        <RotateCcw size={14} /> Resume analysis
                      </>
                    )}
                  </Button>
                </div>
                {resuming && (
                  <p className="mt-2 pl-[30px] text-xs text-ink-faint">
                    Only the missing sections are being re-run — the ones above stay
                    as they are. This page refreshes when it finishes.
                  </p>
                )}
              </div>
            )}

            <div className="mb-6">
              <SectionNav
                value={section}
                onChange={setSection}
                analyzeCount={undefined}
                actCount={undefined}
              />
            </div>

            {section === "analyze" && (
              <Tabs defaultValue="summary" value={analyzeTab} onChange={setAnalyzeTab}>
                <TabsList>
                  <TabsTrigger value="summary">Summary</TabsTrigger>
                  <TabsTrigger value="clauses">Clauses ({clauses.length})</TabsTrigger>
                  <TabsTrigger value="risks">Risks ({risks.length})</TabsTrigger>
                  <TabsTrigger value="obligations">
                    Obligations ({summary.obligations.length})
                  </TabsTrigger>
                  <TabsTrigger value="dates">Dates ({summary.important_dates.length})</TabsTrigger>
                  <TabsTrigger value="chat">Ask LexClarity</TabsTrigger>
                  <TabsTrigger value="evidence">Evidence</TabsTrigger>
                </TabsList>

                <TabsContent value="summary">
                  <OverviewTab summary={summary} />
                </TabsContent>
                <TabsContent value="clauses">
                  <ClausesTab
                    clauses={clauses}
                    documentId={documentId}
                    onNegotiate={negotiateClause}
                  />
                </TabsContent>
                <TabsContent value="risks">
                  <RisksTab risks={risks} documentId={documentId} />
                </TabsContent>
                <TabsContent value="obligations">
                  <ObligationsTab
                    obligations={summary.obligations}
                    documentId={documentId}
                    onChanged={handleObligationChanged}
                  />
                </TabsContent>
                <TabsContent value="dates">
                  <DatesTab
                    dates={summary.important_dates}
                    documentId={documentId}
                    onReminderCreated={() => setDeadlineToken((t) => t + 1)}
                  />
                </TabsContent>
                <TabsContent value="chat">
                  <ChatPanel documentId={documentId} />
                </TabsContent>
                <TabsContent value="evidence">
                  <EvidenceTab documentId={documentId} />
                </TabsContent>
              </Tabs>
            )}

            {section === "act" && (
              <Tabs defaultValue="actions" value={actTab} onChange={setActTab}>
                <TabsList>
                  <TabsTrigger value="actions">Action Center</TabsTrigger>
                  <TabsTrigger value="plan">Plan</TabsTrigger>
                  <TabsTrigger value="negotiation">Negotiation</TabsTrigger>
                  <TabsTrigger value="generator">Generator</TabsTrigger>
                  <TabsTrigger value="deadlines">Deadlines</TabsTrigger>
                  <TabsTrigger value="compliance">Missing clauses</TabsTrigger>
                  <TabsTrigger value="comparison">Comparison</TabsTrigger>
                </TabsList>

                <TabsContent value="actions">
                  <ActionCenterTab
                    documentId={documentId}
                    onGenerateDraft={draftFromAction}
                  />
                </TabsContent>
                <TabsContent value="plan">
                  <PlanTab documentId={documentId} />
                </TabsContent>
                <TabsContent value="negotiation">
                  <NegotiationTab
                    documentId={documentId}
                    clauses={clauses}
                    focusClauseId={focusClauseId}
                    onDraftFromSuggestion={draftFromSuggestion}
                  />
                </TabsContent>
                <TabsContent value="generator">
                  <GeneratorTab
                    documentId={documentId}
                    prefillActionId={draftActionId}
                    prefillInstructions={draftInstructions}
                  />
                </TabsContent>
                <TabsContent value="deadlines">
                  <DeadlinesTab
                    documentId={documentId}
                    dates={summary.important_dates}
                    refreshToken={deadlineToken}
                  />
                </TabsContent>
                <TabsContent value="compliance">
                  <ComplianceTab documentId={documentId} refreshToken={checklistToken} />
                </TabsContent>
                <TabsContent value="comparison">
                  <ComparisonTab documents={documents} />
                </TabsContent>
              </Tabs>
            )}

            <div className="mt-10">
              <Disclaimer />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
