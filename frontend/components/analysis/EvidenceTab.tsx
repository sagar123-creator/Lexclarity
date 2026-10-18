"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, Loader2, FileText, Search } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { VerificationBadge } from "@/components/evidence/VerificationBadge";
import { api, ApiError } from "@/lib/api";
import type { DocumentPage, ClaimVerification } from "@/types";

const METHOD_LABEL: Record<string, string> = {
  deterministic: "Deterministic text match",
  nli: "Local NLI model",
  llm: "LLM judge (not proof)",
  combined: "Deterministic + NLI",
  unavailable: "No verifier available",
};

/**
 * Evidence tab: browse the real stored page text, and verify any claim against
 * it. Verification never invents evidence — unsupported claims are reported as
 * insufficient or needs_review.
 */
export function EvidenceTab({ documentId }: { documentId: string }) {
  const [pages, setPages] = useState<DocumentPage[] | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<number | null>(null);

  const [claim, setClaim] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState<ClaimVerification | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .getPages(documentId)
      .then((p) => {
        if (!active) return;
        setPages(p);
        if (p.length > 0) setActivePage(p[0].page_number);
      })
      .catch((e) => {
        if (active)
          setPageError(
            e instanceof ApiError ? e.message : "Could not load the stored page text."
          );
      });
    return () => {
      active = false;
    };
  }, [documentId]);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!claim.trim() || verifying) return;
    setVerifying(true);
    setVerifyError(null);
    setResult(null);
    try {
      const res = await api.verifyClaim(documentId, claim.trim());
      setResult(res.result);
    } catch (err) {
      setVerifyError(
        err instanceof ApiError ? err.message : "Verification failed. Please try again."
      );
    } finally {
      setVerifying(false);
    }
  }

  const active = pages?.find((p) => p.page_number === activePage) || null;

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Verify a claim</h3>
        </div>
        <p className="text-sm text-ink-faint mb-4">
          Enter any statement about this document. LexClarity checks it against the document text
          and reports whether it is supported, contradicted, or unverifiable — it never fabricates
          evidence to make a claim pass.
        </p>

        <form onSubmit={verify} className="flex items-start gap-2">
          <textarea
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
            rows={2}
            placeholder='e.g. "The agreement renews automatically for one year unless either party gives 60 days notice."'
            className="flex-1 rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy resize-none"
          />
          <Button type="submit" size="md" disabled={verifying || !claim.trim()}>
            {verifying ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            Verify
          </Button>
        </form>

        {verifyError && (
          <p className="mt-3 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">
            {verifyError}
          </p>
        )}

        {result && (
          <div className="mt-4 rounded-md border border-line bg-paper p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <VerificationBadge status={result.status} />
              <span className="text-xs text-ink-faint">
                Method: {METHOD_LABEL[result.method] || result.method}
                {result.score != null && ` · score ${result.score.toFixed(2)}`}
              </span>
            </div>
            <p className="text-sm text-ink-soft">{result.explanation}</p>
            {result.evidence_excerpt && (
              <div className="rounded-md border border-line bg-white px-3.5 py-3">
                <div className="section-label mb-1 text-brass">
                  Evidence{result.evidence_page != null ? ` — page ${result.evidence_page}` : ""}
                </div>
                <p className="text-sm text-ink-soft italic">
                  &ldquo;{result.evidence_excerpt}&rdquo;
                </p>
              </div>
            )}
            {result.notes.length > 0 && (
              <ul className="space-y-1">
                {result.notes.map((n, i) => (
                  <li key={i} className="text-xs text-ink-faint flex gap-1.5">
                    <span className="text-brass">·</span> {n}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <FileText size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Source document</h3>
        </div>
        <p className="text-sm text-ink-faint mb-4">
          The exact text used for retrieval and verification. Highlights on citations point here.
        </p>

        {pageError && (
          <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{pageError}</p>
        )}

        {!pages && !pageError && (
          <div className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" /> Loading page text…
          </div>
        )}

        {pages && pages.length === 0 && (
          <p className="text-sm text-ink-faint">
            No stored page text for this document — it was analyzed before page-level evidence
            was retained. Re-run analysis to capture it.
          </p>
        )}

        {pages && pages.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {pages.map((p) => (
              <button
                key={p.page_number}
                onClick={() => setActivePage(p.page_number)}
                className={
                  "rounded-sm border px-2.5 py-1 text-xs font-mono transition-colors " +
                  (activePage === p.page_number
                    ? "border-navy bg-navy text-white"
                    : "border-line text-ink-faint hover:border-navy hover:text-navy")
                }
              >
                p.{p.page_number}
                {p.ocr_used && <span className="ml-1 text-brass">OCR</span>}
              </button>
            ))}
          </div>
        )}

        {active && (
          <div>
            {active.ocr_used && (
              <p className="mb-2 text-xs text-brass">
                This page was produced by OCR — quotes may be imperfect.
              </p>
            )}
            <div className="rounded-md border border-line bg-paper px-4 py-4 whitespace-pre-wrap text-sm leading-relaxed text-ink-soft max-h-[480px] overflow-y-auto">
              {active.text}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
