"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle, RotateCcw } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { Button } from "@/components/ui/primitives";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/primitives";
import { OverviewTab } from "@/components/analysis/OverviewTab";
import { RisksTab } from "@/components/analysis/RisksTab";
import { ClausesTab } from "@/components/analysis/ClausesTab";
import { ChatPanel } from "@/components/chatbot/ChatPanel";
import { api, ApiError } from "@/lib/api";
import type { DocumentSummaryCard, SummaryResponse, RiskItem, ClauseItem } from "@/types";
import Link from "next/link";

export default function DocumentAnalysisPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const documentId = params.id;

  const [doc, setDoc] = useState<DocumentSummaryCard | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [risks, setRisks] = useState<RiskItem[] | null>(null);
  const [clauses, setClauses] = useState<ClauseItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const document = await api.getDocument(documentId);
        if (!active) return;
        setDoc(document);

        if (document.status === "ready") {
          const [s, r, c] = await Promise.all([
            api.getSummary(documentId),
            api.getRisks(documentId),
            api.getClauses(documentId),
          ]);
          if (!active) return;
          setSummary(s);
          setRisks(r);
          setClauses(c);
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
  }, [documentId, router]);

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
                <p className="font-medium text-risk-high mb-1">Couldn't load this document</p>
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
            <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
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

            <Tabs defaultValue="overview">
              <TabsList>
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="risks">Risks ({risks.length})</TabsTrigger>
                <TabsTrigger value="clauses">Clauses ({clauses.length})</TabsTrigger>
                <TabsTrigger value="chat">Ask LexClarity</TabsTrigger>
              </TabsList>

              <TabsContent value="overview">
                <OverviewTab summary={summary} />
              </TabsContent>
              <TabsContent value="risks">
                <RisksTab risks={risks} />
              </TabsContent>
              <TabsContent value="clauses">
                <ClausesTab clauses={clauses} />
              </TabsContent>
              <TabsContent value="chat">
                <ChatPanel documentId={documentId} />
              </TabsContent>
            </Tabs>

            <div className="mt-10">
              <Disclaimer />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
