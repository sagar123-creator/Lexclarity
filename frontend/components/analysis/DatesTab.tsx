"use client";

import { useState } from "react";
import { CalendarClock, BellPlus, Loader2 } from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/Badge";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import { api, ApiError } from "@/lib/api";
import type { ImportantDateItem } from "@/types";

export function DatesTab({
  dates,
  documentId,
  onReminderCreated,
}: {
  dates: ImportantDateItem[];
  documentId: string;
  onReminderCreated?: () => void;
}) {
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);
  const [creatingId, setCreatingId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "ok" | "error">>({});

  async function createReminder(date: ImportantDateItem) {
    setCreatingId(date.id);
    setFeedback((f) => ({ ...f, [date.id]: "ok" }));
    try {
      await api.createReminder(documentId, {
        date_id: date.id,
        title: date.label,
        due_date: date.normalized_date || date.date_value || undefined,
      });
      setFeedback((f) => ({ ...f, [date.id]: "ok" }));
      onReminderCreated?.();
    } catch {
      setFeedback((f) => ({ ...f, [date.id]: "error" }));
    } finally {
      setCreatingId(null);
    }
  }

  if (dates.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">No important dates were identified in this document.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-ink-faint">
        Dates marked <span className="font-mono uppercase">inferred</span> were derived from
        surrounding language rather than stated outright — confirm them against the source before
        relying on them.
      </p>

      {dates.map((d) => {
        const uncertain = d.extraction_status === "uncertain" || d.date_kind === "inferred";
        return (
          <Card key={d.id} className="p-5">
            <div className="flex items-start gap-3">
              <CalendarClock size={16} className="text-navy mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium text-ink">{d.label}</h3>
                  {d.date_kind && <Badge>{d.date_kind}</Badge>}
                  {d.extraction_status === "uncertain" && (
                    <Badge variant="medium">Uncertain</Badge>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
                  {d.normalized_date && (
                    <span className="font-mono text-sm text-brass">{d.normalized_date}</span>
                  )}
                  {d.date_value && d.date_value !== d.normalized_date && (
                    <span className="font-mono text-xs text-ink-faint">as written: {d.date_value}</span>
                  )}
                </div>
                {d.description && (
                  <p className="mt-1 text-sm text-ink-faint">{d.description}</p>
                )}
                {uncertain && (
                  <p className="mt-1 text-xs text-brass">
                    This date was inferred from context — verify before treating it as a hard deadline.
                  </p>
                )}

                <div className="mt-3 flex flex-wrap items-center gap-3">
                  {d.evidence_quote && (
                    <button
                      type="button"
                      onClick={() =>
                        setEvidenceTarget({
                          documentId,
                          pageNumber: d.page_number,
                          quote: d.evidence_quote,
                          label: "Date evidence",
                        })
                      }
                      className={clsx("text-xs hover:underline", uncertain ? "text-brass" : "text-brass")}
                    >
                      View evidence
                    </button>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={creatingId === d.id}
                    onClick={() => createReminder(d)}
                  >
                    {creatingId === d.id ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <BellPlus size={13} />
                    )}
                    Add reminder
                  </Button>
                  {feedback[d.id] === "error" && (
                    <span className="text-xs text-risk-high">Could not create reminder.</span>
                  )}
                </div>
              </div>
              {d.page_number != null && (
                <span className="font-mono text-xs text-ink-faint shrink-0">p.{d.page_number}</span>
              )}
            </div>
          </Card>
        );
      })}

      <EvidencePanel target={evidenceTarget} onClose={() => setEvidenceTarget(null)} />
    </div>
  );
}
