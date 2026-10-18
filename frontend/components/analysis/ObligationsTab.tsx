"use client";

import { useState } from "react";
import { ListChecks, Loader2 } from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { VerificationBadge } from "@/components/evidence/VerificationBadge";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import { api, ApiError } from "@/lib/api";
import type { ObligationItem } from "@/types";

const TASK_STATUSES = ["pending", "in_progress", "completed"] as const;
const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
};

export function ObligationsTab({
  obligations,
  documentId,
  onChanged,
}: {
  obligations: ObligationItem[];
  documentId: string;
  onChanged?: (updated: ObligationItem) => void;
}) {
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(obligation: ObligationItem, status: string) {
    setUpdatingId(obligation.id);
    setError(null);
    try {
      const updated = await api.updateObligation(obligation.id, status);
      onChanged?.(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update the obligation.");
    } finally {
      setUpdatingId(null);
    }
  }

  if (obligations.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">No obligations were identified in this document.</p>
      </Card>
    );
  }

  const groups = new Map<string, ObligationItem[]>();
  for (const o of obligations) {
    const list = groups.get(o.party_name) || [];
    list.push(o);
    groups.set(o.party_name, list);
  }

  return (
    <div className="space-y-6">
      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {Array.from(groups.entries()).map(([party, items]) => (
        <div key={party}>
          <h3 className="font-serif text-lg font-semibold mb-3">{party}</h3>
          <div className="space-y-3">
            {items.map((o) => (
              <Card key={o.id} className="p-5">
                <div className="flex items-start gap-3">
                  <ListChecks size={16} className="text-navy mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-ink-soft leading-relaxed">{o.obligation_text}</p>

                    {(o.deadline_text || o.trigger_event || o.conditions) && (
                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-faint">
                        {o.deadline_text && (
                          <span>
                            Deadline: <span className="text-ink-soft">{o.deadline_text}</span>
                          </span>
                        )}
                        {o.trigger_event && (
                          <span>
                            Trigger: <span className="text-ink-soft">{o.trigger_event}</span>
                          </span>
                        )}
                        {o.conditions && (
                          <span>
                            Conditions: <span className="text-ink-soft">{o.conditions}</span>
                          </span>
                        )}
                      </div>
                    )}

                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <VerificationBadge status={o.verification_status} />
                      {o.evidence_quote && documentId && (
                        <button
                          type="button"
                          onClick={() =>
                            setEvidenceTarget({
                              documentId,
                              pageNumber: o.page_number,
                              quote: o.evidence_quote,
                              label: "Obligation evidence",
                            })
                          }
                          className="text-xs text-brass hover:underline"
                        >
                          View evidence
                        </button>
                      )}
                    </div>

                    <div className="mt-3 flex items-center gap-1.5">
                      {TASK_STATUSES.map((s) => {
                        const active = (o.task_status || "pending") === s;
                        return (
                          <button
                            key={s}
                            disabled={updatingId === o.id}
                            onClick={() => setStatus(o, s)}
                            className={clsx(
                              "rounded-sm border px-2 py-1 text-[11px] font-mono uppercase tracking-wide transition-colors disabled:opacity-50",
                              active
                                ? "border-navy bg-navy text-white"
                                : "border-line text-ink-faint hover:border-navy hover:text-navy"
                            )}
                          >
                            {updatingId === o.id && active ? (
                              <Loader2 size={11} className="animate-spin inline" />
                            ) : (
                              STATUS_LABEL[s]
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  {o.page_number != null && (
                    <span className="font-mono text-xs text-ink-faint shrink-0">
                      p.{o.page_number}
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      ))}

      <EvidencePanel target={evidenceTarget} onClose={() => setEvidenceTarget(null)} />
    </div>
  );
}
