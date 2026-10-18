"use client";

import { useCallback, useEffect, useState } from "react";
import {
  GitCompareArrows,
  Loader2,
  AlertTriangle,
  Plus,
  ChevronDown,
} from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { Badge, riskVariant } from "@/components/ui/Badge";
import { api, ApiError } from "@/lib/api";
import type { Comparison, DocumentSummaryCard, ClauseDiffEntry } from "@/types";

const CHANGE_STYLE: Record<string, string> = {
  added: "bg-risk-lowBg text-risk-low",
  removed: "bg-risk-highBg text-risk-high",
  modified: "bg-brass-soft text-brass",
  similar: "bg-line/60 text-ink-soft",
};

/**
 * Contract comparison: pick two documents and get a clause-by-clause diff plus
 * a risk-profile delta. The summary describes textual differences only — it
 * explicitly does not assert legal significance.
 */
export function ComparisonTab({ documents }: { documents: DocumentSummaryCard[] }) {
  const [docA, setDocA] = useState("");
  const [docB, setDocB] = useState("");
  const [comparisons, setComparisons] = useState<Comparison[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openCategory, setOpenCategory] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await api.listComparisons();
      setComparisons(list);
      if (list.length > 0) setActiveId((id) => id || list[0].id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load comparisons.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runCompare(e: React.FormEvent) {
    e.preventDefault();
    if (!docA || !docB || docA === docB || busy) return;
    setBusy(true);
    setError(null);
    try {
      const c = await api.compare(docA, docB);
      setComparisons((prev) => [c, ...(prev || [])]);
      setActiveId(c.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  const ready = documents.filter((d) => d.status === "ready");
  const active = comparisons?.find((c) => c.id === activeId) || null;
  const summary = active?.summary || null;

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <GitCompareArrows size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Compare two contracts</h3>
        </div>
        <p className="text-sm text-ink-faint mb-4">
          Clause-by-clause diff of two analyzed documents, with material term changes
          (amounts, notice periods) called out even when the wording barely changed.
        </p>

        {ready.length < 2 ? (
          <p className="text-sm text-brass">
            You need at least two analyzed documents to run a comparison.
          </p>
        ) : (
          <form onSubmit={runCompare} className="flex flex-wrap items-end gap-3">
            <label className="flex-1 min-w-[200px]">
              <span className="section-label block mb-1.5">First document</span>
              <select
                value={docA}
                onChange={(e) => setDocA(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-navy"
              >
                <option value="">Choose…</option>
                {ready.map((d) => (
                  <option key={d.id} value={d.id} disabled={d.id === docB}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex-1 min-w-[200px]">
              <span className="section-label block mb-1.5">Second document</span>
              <select
                value={docB}
                onChange={(e) => setDocB(e.target.value)}
                className="w-full rounded-md border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-navy"
              >
                <option value="">Choose…</option>
                {ready.map((d) => (
                  <option key={d.id} value={d.id} disabled={d.id === docA}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={!docA || !docB || docA === docB || busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              Compare
            </Button>
          </form>
        )}
      </Card>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {active && (
        <Card className="p-6 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-serif text-lg font-semibold">
              {summary?.document_a.filename || active.document_a_id}{" "}
              <span className="text-ink-faint">vs</span>{" "}
              {summary?.document_b.filename || active.document_b_id}
            </h3>
            {comparisons && comparisons.length > 1 && (
              <select
                value={activeId || ""}
                onChange={(e) => setActiveId(e.target.value)}
                className="rounded-md border border-line bg-white px-3 py-1.5 text-sm outline-none focus:border-navy"
              >
                {comparisons.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.summary?.document_a.filename || c.document_a_id} vs{" "}
                    {c.summary?.document_b.filename || c.document_b_id}
                  </option>
                ))}
              </select>
            )}
          </div>

          {summary?.summary && (
            <div className="rounded-md bg-paper border border-line p-4">
              <div className="section-label mb-1 text-navy">Summary of changes</div>
              <p className="text-sm text-ink-soft leading-relaxed">{summary.summary}</p>
            </div>
          )}

          {summary?.summary_disclaimer && (
            <p className="flex items-start gap-1.5 text-xs text-ink-faint">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              {summary.summary_disclaimer}
            </p>
          )}

          {summary && (
            <>
              <div>
                <div className="section-label mb-2">Risk profile</div>
                <div className="flex flex-wrap gap-3">
                  <Badge variant={riskVariant(summary.risk_delta.overall_level_a)}>
                    Doc 1: {summary.risk_delta.overall_level_a} ({summary.risk_delta.high_count_a}{" "}
                    high)
                  </Badge>
                  <Badge variant={riskVariant(summary.risk_delta.overall_level_b)}>
                    Doc 2: {summary.risk_delta.overall_level_b} ({summary.risk_delta.high_count_b}{" "}
                    high)
                  </Badge>
                </div>
                {summary.risk_delta.new_findings.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {summary.risk_delta.new_findings.map((f, i) => (
                      <li key={i} className="text-sm text-ink-soft flex gap-2">
                        <span className="text-brass">·</span> {f.title}{" "}
                        <span className="font-mono text-xs text-ink-faint">({f.level})</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <div className="section-label mb-2">
                  Clause changes ({summary.clause_changes.length})
                </div>
                <div className="space-y-2">
                  {summary.clause_changes.map((c, i) => (
                    <ClauseChangeRow
                      key={`${c.category}-${i}`}
                      change={c}
                      open={openCategory === `${c.category}-${i}`}
                      onToggle={() =>
                        setOpenCategory(openCategory === `${c.category}-${i}` ? null : `${c.category}-${i}`)
                      }
                    />
                  ))}
                  {summary.clause_changes.length === 0 && (
                    <p className="text-sm text-ink-faint">
                      No clause-level differences were detected.
                    </p>
                  )}
                </div>
              </div>
            </>
          )}
        </Card>
      )}

      {active && active.status !== "completed" && (
        <p className="text-sm text-brass flex items-center gap-2">
          <Loader2 size={13} className="animate-spin" /> Comparison is still processing…
        </p>
      )}

      {comparisons && comparisons.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-faint">No comparisons yet — run one above.</p>
        </Card>
      )}
    </div>
  );
}

function ClauseChangeRow({
  change,
  open,
  onToggle,
}: {
  change: ClauseDiffEntry;
  open: boolean;
  onToggle: () => void;
}) {
  if (change.change === "unchanged") return null;
  const textA = change.clause_a?.original_text || "";
  const textB = change.clause_b?.original_text || "";

  return (
    <div className="rounded-md border border-line overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-paper transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <span
            className={clsx(
              "rounded-sm px-2 py-0.5 text-[11px] font-mono uppercase tracking-wide",
              CHANGE_STYLE[change.change] || "bg-line/60 text-ink-soft"
            )}
          >
            {change.change}
          </span>
          <span className="text-sm font-medium text-ink capitalize">{change.category}</span>
        </div>
        <ChevronDown
          size={16}
          className={clsx("text-ink-faint transition-transform shrink-0", open && "rotate-180")}
        />
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 space-y-3 border-t border-line">
          <div className="grid md:grid-cols-2 gap-3">
            <div className="rounded-md bg-paper px-3.5 py-3">
              <div className="section-label mb-1">Doc 1</div>
              <p className="text-sm text-ink-soft leading-relaxed">
                {textA || <span className="italic text-ink-faint">Not present</span>}
              </p>
            </div>
            <div className="rounded-md bg-navy/5 px-3.5 py-3">
              <div className="section-label mb-1 text-navy">Doc 2</div>
              <p className="text-sm text-ink-soft leading-relaxed">
                {textB || <span className="italic text-ink-faint">Not present</span>}
              </p>
            </div>
          </div>

          {change.similarity != null && (
            <p className="text-xs text-ink-faint">
              Word-level similarity: {(change.similarity * 100).toFixed(0)}%
            </p>
          )}
        </div>
      )}
    </div>
  );
}
