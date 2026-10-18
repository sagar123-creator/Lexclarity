"use client";

import { useState } from "react";
import { ChevronDown, FileSearch, Handshake } from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { VerificationBadge } from "@/components/evidence/VerificationBadge";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import type { ClauseItem } from "@/types";

export function ClausesTab({
  clauses,
  documentId,
  onNegotiate,
}: {
  clauses: ClauseItem[];
  documentId?: string;
  /** When provided, each clause gets a "Suggest edits" action. */
  onNegotiate?: (clause: ClauseItem) => void;
}) {
  const [openId, setOpenId] = useState<string | null>(clauses[0]?.id ?? null);
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);

  if (clauses.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">No key clauses were identified in this document.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {clauses.map((clause) => {
        const isOpen = openId === clause.id;
        return (
          <Card key={clause.id} className="overflow-hidden">
            <button
              onClick={() => setOpenId(isOpen ? null : clause.id)}
              className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-paper transition-colors"
            >
              <div>
                <span className="section-label text-brass">{clause.category}</span>
                <h3 className="font-medium text-ink mt-0.5">{clause.title}</h3>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-4">
                <VerificationBadge status={clause.verification_status} />
                <ChevronDown
                  size={18}
                  className={clsx("text-ink-faint transition-transform", isOpen && "rotate-180")}
                />
              </div>
            </button>
            {isOpen && (
              <div className="px-6 pb-6 pt-1 space-y-4 border-t border-line">
                {clause.original_text && (
                  <div className="pt-4">
                    <div className="section-label mb-1.5">Original Text</div>
                    <p className="text-sm text-ink-soft italic border-l-2 border-line pl-3 leading-relaxed">
                      &ldquo;{clause.original_text}&rdquo;
                    </p>
                  </div>
                )}
                {clause.plain_explanation && (
                  <div className="rounded-md bg-paper border border-line p-3.5">
                    <div className="section-label mb-1 text-navy">Plain English</div>
                    <p className="text-sm text-ink-soft">{clause.plain_explanation}</p>
                  </div>
                )}
                {clause.rights_obligations && (
                  <div className="rounded-md border border-line p-3.5">
                    <div className="section-label mb-1">Rights & obligations</div>
                    <p className="text-sm text-ink-soft">{clause.rights_obligations}</p>
                  </div>
                )}
                {clause.concerns && (
                  <div className="rounded-md border border-brass/30 bg-brass-soft p-3.5">
                    <div className="section-label mb-1 text-brass">Potential concerns</div>
                    <p className="text-sm text-ink-soft">{clause.concerns}</p>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-3">
                  {(clause.evidence_quote || clause.page_number) && documentId && (
                    <button
                      type="button"
                      onClick={() =>
                        setEvidenceTarget({
                          documentId,
                          pageNumber: clause.page_number,
                          quote: clause.evidence_quote || clause.original_text,
                          chunkId: clause.source_chunk_id,
                          label: "Clause source",
                        })
                      }
                      className="flex items-center gap-1.5 text-xs text-brass hover:underline"
                    >
                      <FileSearch size={12} /> View in source document
                    </button>
                  )}
                  {onNegotiate && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => onNegotiate(clause)}
                    >
                      <Handshake size={13} /> Suggest edits
                    </Button>
                  )}
                </div>

                {clause.page_number && (
                  <p className="font-mono text-xs text-ink-faint">
                    Source: Page {clause.page_number}
                    {clause.section_reference ? ` — ${clause.section_reference}` : ""}
                  </p>
                )}
              </div>
            )}
          </Card>
        );
      })}

      <EvidencePanel target={evidenceTarget} onClose={() => setEvidenceTarget(null)} />
    </div>
  );
}
