"use client";

import { useEffect, useState } from "react";
import { Route, Loader2, AlertTriangle } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/primitives";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { api, ApiError } from "@/lib/api";
import type { ActionPlan, PlanItem } from "@/types";

/**
 * Legal action plan: an ordered view of the action items, grouped by priority,
 * with the disclaimer attached by the backend.
 */
export function PlanTab({ documentId }: { documentId: string }) {
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .getPlan(documentId)
      .then((p) => {
        if (active) setPlan(p);
      })
      .catch((e) => {
        if (active)
          setError(e instanceof ApiError ? e.message : "Could not load the action plan.");
      });
    return () => {
      active = false;
    };
  }, [documentId]);

  if (error) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-risk-high">{error}</p>
      </Card>
    );
  }

  if (!plan) {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-faint">
        <Loader2 size={14} className="animate-spin" /> Building your action plan…
      </div>
    );
  }

  const groups: [string, PlanItem[]][] = ["High", "Medium", "Low"]
    .map((p) => [p, plan.items.filter((i) => i.priority === p)] as [string, PlanItem[]])
    .filter(([, items]) => items.length > 0);

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <Route size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Legal action plan</h3>
        </div>
        <p className="text-sm text-ink-faint">
          An ordered view of what to do next, grouped by priority.{" "}
          {plan.items.length} item{plan.items.length === 1 ? "" : "s"} generated from this
          document&rsquo;s findings.
        </p>
      </Card>

      {groups.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-faint">
            No action items yet. Generate them from the Action Center first.
          </p>
        </Card>
      )}

      {groups.map(([priority, items]) => (
        <div key={priority}>
          <div className="flex items-center gap-2 mb-3">
            <Badge variant={riskVariant(priority)}>{priority} priority</Badge>
            <span className="text-xs text-ink-faint">{items.length} item{items.length === 1 ? "" : "s"}</span>
          </div>
          <div className="space-y-3">
            {items.map((item) => (
              <Card key={item.action_id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-2 mb-1">
                  <h4 className="font-medium text-ink">{item.title}</h4>
                  <div className="flex items-center gap-2">
                    <Badge>{item.related_finding_type.replace(/_/g, " ")}</Badge>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint">
                      {item.status.replace(/_/g, " ")} · {item.decision}
                    </span>
                  </div>
                </div>
                {item.suggested_action && (
                  <p className="mt-1 text-sm text-ink-soft">{item.suggested_action}</p>
                )}
                {item.priority_reason && (
                  <p className="mt-1.5 text-xs text-ink-faint">
                    Why this priority: {item.priority_reason}
                  </p>
                )}
                {item.required_input && (
                  <p className="mt-1.5 text-xs text-brass">Needs your input: {item.required_input}</p>
                )}
              </Card>
            ))}
          </div>
        </div>
      ))}

      {plan.disclaimer && (
        <p
          className={clsx(
            "flex items-start gap-2 rounded-md border border-brass/30 bg-brass-soft px-4 py-3 text-xs text-brass"
          )}
        >
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          {plan.disclaimer}
        </p>
      )}
    </div>
  );
}
