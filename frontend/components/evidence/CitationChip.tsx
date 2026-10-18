"use client";

import clsx from "clsx";
import { FileSearch, AlertTriangle, CheckCircle2 } from "lucide-react";
import type { Citation } from "@/types";

/**
 * Clickable citation chip. `verified: false` means the referenced chunk was
 * not actually retrieved for the answer — shown as an explicit warning, never
 * hidden.
 */
export function CitationChip({
  citation,
  onOpen,
  className,
}: {
  citation: Citation;
  onOpen?: (citation: Citation) => void;
  className?: string;
}) {
  if (!citation.page_number && !citation.section_reference && !citation.snippet && !citation.quote)
    return null;

  const unverified = citation.verified === false;
  const quoteVerified = citation.quote_verified === false;

  const label =
    citation.page_number != null ? `Page ${citation.page_number}` : "";
  const section = citation.section_reference || "";

  const body = (
    <>
      <FileSearch size={12} className="text-brass mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-mono text-[11px] text-brass">
          Source: {label}
          {section ? ` — ${section}` : ""}
          {!label && !section ? "Cited passage" : ""}
        </p>
        {(citation.quote || citation.snippet) && (
          <p className="text-xs text-ink-faint mt-0.5 line-clamp-2">
            “{(citation.quote || citation.snippet || "").slice(0, 200)}”
          </p>
        )}
        {unverified && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-risk-high">
            <AlertTriangle size={11} /> Not found in retrieved sources — this
            citation could not be verified.
          </p>
        )}
        {quoteVerified && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-risk-high">
            <AlertTriangle size={11} /> Quote text did not match the source
            exactly.
          </p>
        )}
        {!unverified && !quoteVerified && citation.verified === true && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-risk-low">
            <CheckCircle2 size={11} /> Matched to source passage.
          </p>
        )}
      </div>
    </>
  );

  const base =
    "flex items-start gap-1.5 rounded-md border bg-white px-2.5 py-1.5 text-left w-full";
  if (!onOpen) {
    return (
      <div className={clsx(base, unverified ? "border-risk-high/30" : "border-line", className)}>
        {body}
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      className={clsx(
        base,
        "transition-colors hover:border-navy",
        unverified ? "border-risk-high/30" : "border-line",
        className
      )}
    >
      {body}
    </button>
  );
}
