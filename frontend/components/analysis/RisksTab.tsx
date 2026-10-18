"use client";

import { useState } from "react";
import { AlertOctagon, AlertTriangle, Info, FileSearch } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { VerificationBadge } from "@/components/evidence/VerificationBadge";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import type { RiskItem } from "@/types";

const LEVEL_ICON = { High: AlertOctagon, Medium: AlertTriangle, Low: Info };
const LEVEL_ORDER = { High: 0, Medium: 1, Low: 2 };

export function RisksTab({
  risks,
  documentId,
}: {
  risks: RiskItem[];
  documentId?: string;
}) {
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);

  function openEvidence(risk: RiskItem) {
    setEvidenceTarget({
      documentId: documentId || "",
      pageNumber: risk.page_number,
      quote: risk.evidence_quote,
      chunkId: risk.source_chunk_id,
      label: "Evidence quote",
    });
  }

  if (risks.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">
          No specific risks were flagged in this document. This does not guarantee the
          document is risk-free — consider a professional review for important decisions.
        </p>
      </Card>
    );
  }

  const sorted = [...risks].sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);

  return (
    <div className="space-y-4">
      {sorted.map((risk) => {
        const Icon = LEVEL_ICON[risk.level];
        return (
          <Card key={risk.id} className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
              <div className="flex items-center gap-2.5">
                <Icon size={17} className={riskIconColor(risk.level)} />
                <h3 className="font-medium text-ink">{risk.title}</h3>
              </div>
              <div className="flex items-center gap-2">
                {risk.category && <Badge>{risk.category}</Badge>}
                <Badge variant={riskVariant(risk.level)}>{risk.level} Risk</Badge>
              </div>
            </div>
            <p className="text-sm text-ink-soft leading-relaxed mb-3">{risk.description}</p>
            <div className="rounded-md bg-paper border border-line p-3.5 mb-3">
              <div className="section-label mb-1 text-navy">Why it matters</div>
              <p className="text-sm text-ink-soft">{risk.why_it_matters}</p>
            </div>
            {risk.plain_explanation && (
              <p className="text-sm text-ink-faint italic mb-3">{risk.plain_explanation}</p>
            )}

            {risk.severity_rationale && (
              <div className="mb-3 rounded-md border border-line px-3.5 py-3">
                <div className="section-label mb-1">How this severity was determined</div>
                <p className="text-sm text-ink-soft">{risk.severity_rationale}</p>
              </div>
            )}

            {risk.suggested_action && (
              <div className="mb-3 rounded-md border border-navy/20 bg-navy/5 px-3.5 py-3">
                <div className="section-label mb-1 text-navy">Suggested next step</div>
                <p className="text-sm text-ink-soft">{risk.suggested_action}</p>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <VerificationBadge status={risk.verification_status} />
              {risk.affected_party && (
                <span className="text-xs text-ink-faint">
                  Affects: <span className="text-ink-soft">{risk.affected_party}</span>
                </span>
              )}
            </div>

            {(risk.evidence_quote || risk.page_number) && documentId && (
              <button
                type="button"
                onClick={() => openEvidence(risk)}
                className="mt-3 flex items-center gap-1.5 text-xs text-brass hover:underline"
              >
                <FileSearch size={12} />
                {risk.evidence_quote ? "View evidence quote in source" : "View source page"}
              </button>
            )}

            {risk.page_number && (
              <p className="mt-2 font-mono text-xs text-ink-faint">
                Source: Page {risk.page_number}
                {risk.section_reference ? ` — ${risk.section_reference}` : ""}
              </p>
            )}
          </Card>
        );
      })}

      <EvidencePanel target={evidenceTarget} onClose={() => setEvidenceTarget(null)} />
    </div>
  );
}

function riskIconColor(level: string) {
  if (level === "High") return "text-risk-high";
  if (level === "Medium") return "text-risk-medium";
  return "text-risk-low";
}
