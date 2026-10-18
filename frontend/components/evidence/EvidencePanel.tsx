"use client";

import { useEffect, useMemo, useState } from "react";
import { X, FileSearch, AlertTriangle, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { DocumentPage } from "@/types";

export interface EvidenceTarget {
  documentId: string;
  pageNumber?: number | null;
  /** Exact quote to highlight, when known. */
  quote?: string | null;
  chunkId?: string | null;
  /** Label shown in the panel header (e.g. "Citation", "Evidence quote"). */
  label?: string;
}

/**
 * Slide-over evidence viewer: shows the real stored page text and highlights
 * the cited passage. If the quote cannot be located in the page text, the
 * panel says so explicitly rather than pretending the citation resolves.
 */
export function EvidencePanel({
  target,
  onClose,
}: {
  target: EvidenceTarget | null;
  onClose: () => void;
}) {
  const [page, setPage] = useState<DocumentPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const key = target
    ? `${target.documentId}:${target.pageNumber ?? "?"}:${target.chunkId ?? ""}`
    : null;

  useEffect(() => {
    if (!target || !target.pageNumber) {
      setPage(null);
      setError(
        target
          ? "This finding does not include a page reference, so there is no page text to show."
          : null
      );
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setPage(null);
    api
      .getPage(target.documentId, target.pageNumber)
      .then((p) => {
        if (active) setPage(p);
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof ApiError ? e.message : "Could not load the page text."
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [key, target]);

  const segments = useMemo(() => {
    if (!page || !target?.quote) return null;
    const idx = page.text.indexOf(target.quote);
    if (idx === -1) return null;
    return {
      before: page.text.slice(0, idx),
      hit: page.text.slice(idx, idx + target.quote.length),
      after: page.text.slice(idx + target.quote.length),
    };
  }, [page, target?.quote]);

  if (!target) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-ink/30"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="relative w-full max-w-xl h-full bg-white border-l border-line shadow-card flex flex-col">
        <header className="flex items-start justify-between gap-4 px-6 py-4 border-b border-line">
          <div>
            <div className="section-label mb-1">{target.label || "Evidence"}</div>
            <p className="text-sm text-ink-soft">
              {target.pageNumber ? `Page ${target.pageNumber}` : "No page reference"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-ink-faint hover:text-ink hover:bg-paper transition-colors"
            aria-label="Close evidence panel"
          >
            <X size={16} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-ink-faint">
              <Loader2 size={14} className="animate-spin" /> Loading page text…
            </div>
          )}

          {error && (
            <div className="rounded-md border border-line bg-paper px-4 py-3 text-sm text-ink-soft">
              {error}
            </div>
          )}

          {page && (
            <>
              {page.ocr_used && (
                <p className="mb-3 flex items-start gap-2 rounded-md border border-brass/30 bg-brass-soft px-3 py-2 text-xs text-brass">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                  This page text came from OCR (image-based PDF). Quotes may be
                  imperfect — read the original before relying on it.
                </p>
              )}

              {target.quote && (
                <div className="mb-4 rounded-md border border-line bg-paper px-4 py-3">
                  <div className="flex items-center gap-1.5 mb-1.5">
                    <FileSearch size={12} className="text-brass" />
                    <span className="font-mono text-[11px] uppercase tracking-wide text-brass">
                      Cited passage
                    </span>
                  </div>
                  <p className="text-sm text-ink-soft leading-relaxed">
                    “{target.quote}”
                  </p>
                  {segments === null && (
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-risk-high">
                      <AlertTriangle size={12} /> This exact quote was not found
                      in the stored page text — treat the citation as unverified.
                    </p>
                  )}
                </div>
              )}

              <div className="section-label mb-2">Page text</div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">
                {segments ? (
                  <>
                    {segments.before}
                    <mark className="bg-brass-soft text-ink rounded-sm px-0.5">
                      {segments.hit}
                    </mark>
                    {segments.after}
                  </>
                ) : (
                  page.text
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
