"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ClipboardCheck,
  Loader2,
  CheckCircle2,
  XCircle,
  HelpCircle,
  MinusCircle,
  RefreshCw,
} from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { ChecklistItem } from "@/types";

const STATE_META: Record<string, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  detected: { label: "Detected", className: "bg-risk-lowBg text-risk-low", Icon: CheckCircle2 },
  not_detected: { label: "Missing", className: "bg-risk-highBg text-risk-high", Icon: XCircle },
  unclear: { label: "Unclear", className: "bg-brass-soft text-brass", Icon: HelpCircle },
  not_applicable: {
    label: "N/A",
    className: "bg-line/60 text-ink-soft",
    Icon: MinusCircle,
  },
};

/**
 * Missing-clause detector: checks which clauses a contract of this type
 * normally contains. "Missing" means the clause was not found in the text —
 * it is not a legal opinion that the clause is required.
 */
export function ComplianceTab({
  documentId,
  refreshToken,
}: {
  documentId: string;
  refreshToken?: number;
}) {
  const [items, setItems] = useState<ChecklistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api.getChecklist(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the checklist.");
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load, refreshToken]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setItems(await api.runChecklist(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not run the checklist.");
    } finally {
      setRunning(false);
    }
  }

  const missing = (items || []).filter((i) => i.state === "not_detected").length;

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ClipboardCheck size={16} className="text-navy" />
              <h3 className="font-serif text-lg font-semibold">Missing-clause checklist</h3>
            </div>
            <p className="text-sm text-ink-faint max-w-2xl">
              Checks for clauses typically found in this kind of document. A &ldquo;missing&rdquo;
              result means the clause text was not found — not that it is legally required.
              Always confirm with a professional.
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={run} disabled={running}>
            {running ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            {items && items.length > 0 ? "Re-run" : "Run checklist"}
          </Button>
        </div>

        {items && items.length > 0 && (
          <p className="mt-3 text-sm text-ink-soft">
            <span className="font-semibold">{missing}</span> typically-important clause
            {missing === 1 ? "" : "s"} not found in this document.
          </p>
        )}
      </Card>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {!items && !error && (
        <div className="flex items-center gap-2 text-sm text-ink-faint">
          <Loader2 size={14} className="animate-spin" /> Loading checklist…
        </div>
      )}

      {items && items.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-faint">
            No checklist has been run for this document yet. Click &ldquo;Run checklist&rdquo;.
          </p>
        </Card>
      )}

      {items && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => {
            const meta = STATE_META[item.state] || STATE_META.unclear;
            const Icon = meta.Icon;
            return (
              <Card key={item.id} className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <Icon size={16} className={clsx("mt-0.5 shrink-0", meta.className.split(" ")[1])} />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink">{item.item_label}</span>
                        <span
                          className={clsx(
                            "rounded-sm px-2 py-0.5 text-[11px] font-mono uppercase tracking-wide",
                            meta.className
                          )}
                        >
                          {meta.label}
                        </span>
                      </div>
                      {item.explanation && (
                        <p className="mt-1 text-sm text-ink-soft">{item.explanation}</p>
                      )}
                      {item.evidence_quote && (
                        <p className="mt-1.5 text-xs text-ink-faint italic border-l-2 border-line pl-2.5">
                          &ldquo;{item.evidence_quote}&rdquo;
                          {item.page_number != null && (
                            <span className="font-mono ml-1.5">p.{item.page_number}</span>
                          )}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
