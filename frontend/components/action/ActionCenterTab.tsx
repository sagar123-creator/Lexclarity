"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ListTodo,
  Loader2,
  RefreshCw,
  CheckCircle2,
  Circle,
  Clock,
  PenLine,
} from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { api, ApiError } from "@/lib/api";
import type { ActionItem } from "@/types";

const STATUS_ICON = {
  pending: Circle,
  in_progress: Clock,
  completed: CheckCircle2,
};

const DECISIONS = ["accepted", "rejected", "deferred"] as const;

export function ActionCenterTab({
  documentId,
  onGenerateDraft,
}: {
  documentId: string;
  /** Called when the user picks "Draft a response" for an action. */
  onGenerateDraft?: (action: ActionItem) => void;
}) {
  const [actions, setActions] = useState<ActionItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setActions(await api.getActions(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load actions.");
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      setActions(await api.generateActions(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not generate actions.");
    } finally {
      setGenerating(false);
    }
  }

  async function update(action: ActionItem, patch: { status?: string; decision?: string }) {
    setBusyId(action.id);
    setError(null);
    try {
      const updated = await api.updateAction(action.id, patch);
      setActions((prev) =>
        (prev || []).map((a) => (a.id === updated.id ? updated : a))
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update the action.");
    } finally {
      setBusyId(null);
    }
  }

  if (!actions) {
    return error ? (
      <Card className="p-8 text-center">
        <p className="text-sm text-risk-high">{error}</p>
      </Card>
    ) : (
      <div className="flex items-center gap-2 text-sm text-ink-faint">
        <Loader2 size={14} className="animate-spin" /> Loading actions…
      </div>
    );
  }

  const ordered = [...actions].sort((a, b) => {
    const rank = { High: 0, Medium: 1, Low: 2 } as Record<string, number>;
    return (rank[a.priority] ?? 3) - (rank[b.priority] ?? 3);
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-faint max-w-2xl">
          Concrete next steps derived from this document&rsquo;s findings. Priority combines
          severity with evidence strength and deadline proximity — every item explains its
          reasoning. Nothing here is sent or filed automatically; you stay in control.
        </p>
        <Button variant="secondary" size="sm" onClick={generate} disabled={generating}>
          {generating ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RefreshCw size={13} />
          )}
          Regenerate
        </Button>
      </div>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {ordered.length === 0 && (
        <Card className="p-8 text-center">
          <ListTodo size={22} className="mx-auto text-ink-faint mb-2" />
          <p className="text-sm text-ink-faint">
            No action items yet. Click &ldquo;Regenerate&rdquo; to derive them from the analysis.
          </p>
        </Card>
      )}

      {ordered.map((action) => {
        const StatusIcon = STATUS_ICON[action.status as keyof typeof STATUS_ICON] || Circle;
        return (
          <Card key={action.id} className="p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <Badge variant={riskVariant(action.priority)}>{action.priority}</Badge>
                  <Badge>{action.source_type.replace(/_/g, " ")}</Badge>
                </div>
                <h3 className="font-medium text-ink">{action.title}</h3>
                {action.description && (
                  <p className="mt-1 text-sm text-ink-soft">{action.description}</p>
                )}
                {action.priority_reason && (
                  <p className="mt-1.5 text-xs text-ink-faint">
                    Why this priority: {action.priority_reason}
                  </p>
                )}
                {action.suggested_action && (
                  <div className="mt-2 rounded-md border border-navy/20 bg-navy/5 px-3 py-2">
                    <span className="section-label text-navy">Suggested step</span>
                    <p className="text-sm text-ink-soft mt-0.5">{action.suggested_action}</p>
                  </div>
                )}
                {action.required_input && (
                  <p className="mt-2 text-xs text-brass">
                    Needs your input: {action.required_input}
                  </p>
                )}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-line pt-3">
              <div className="flex items-center gap-1.5">
                <StatusIcon size={13} className="text-ink-faint" />
                {(["pending", "in_progress", "completed"] as const).map((s) => (
                  <button
                    key={s}
                    disabled={busyId === action.id}
                    onClick={() => update(action, { status: s })}
                    className={clsx(
                      "rounded-sm border px-2 py-1 text-[11px] font-mono uppercase tracking-wide transition-colors disabled:opacity-50",
                      action.status === s
                        ? "border-navy bg-navy text-white"
                        : "border-line text-ink-faint hover:border-navy hover:text-navy"
                    )}
                  >
                    {s.replace("_", " ")}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-mono uppercase tracking-wide text-ink-faint">
                  Decision:
                </span>
                <span className="text-[11px] font-mono uppercase text-ink-soft">
                  {action.decision}
                </span>
                {DECISIONS.map((d) => (
                  <button
                    key={d}
                    disabled={busyId === action.id}
                    onClick={() => update(action, { decision: d })}
                    className={clsx(
                      "rounded-sm border px-2 py-1 text-[11px] font-mono uppercase tracking-wide transition-colors disabled:opacity-50",
                      action.decision === d
                        ? "border-brass bg-brass text-white"
                        : "border-line text-ink-faint hover:border-brass hover:text-brass"
                    )}
                  >
                    {d}
                  </button>
                ))}
              </div>

              {onGenerateDraft && (
                <Button variant="ghost" size="sm" onClick={() => onGenerateDraft(action)}>
                  <PenLine size={13} /> Draft a response
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
