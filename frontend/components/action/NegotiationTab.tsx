"use client";

import { useCallback, useEffect, useState } from "react";
import { Handshake, Loader2, AlertTriangle } from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { ClauseItem, ClauseSuggestion } from "@/types";

/**
 * Negotiation assistant: produces redline-style suggested edits for a chosen
 * clause. Every suggestion carries its rationale and negotiation points; the
 * original text is always preserved alongside the proposal, and nothing is
 * sent to the counterparty automatically.
 */
export function NegotiationTab({
  documentId,
  clauses,
  focusClauseId,
  onDraftFromSuggestion,
}: {
  documentId: string;
  clauses: ClauseItem[];
  focusClauseId?: string | null;
  onDraftFromSuggestion?: (s: ClauseSuggestion) => void;
}) {
  const [suggestions, setSuggestions] = useState<ClauseSuggestion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [selectedClause, setSelectedClause] = useState<string>(focusClauseId || "");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try {
      setSuggestions(await api.listSuggestions(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load suggestions.");
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (focusClauseId) setSelectedClause(focusClauseId);
  }, [focusClauseId]);

  async function negotiate(clauseId: string) {
    setBusy(clauseId);
    setError(null);
    try {
      const s = await api.negotiate(documentId, clauseId);
      setSuggestions((prev) => {
        const rest = (prev || []).filter((x) => x.clause_id !== s.clause_id);
        return [s, ...rest];
      });
      setExpanded((e) => ({ ...e, [s.id]: true }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a suggestion.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <Handshake size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Suggest edits to a clause</h3>
        </div>
        <p className="text-sm text-ink-faint mb-4">
          Pick a clause and LexClarity drafts friendlier or more balanced wording, with the
          reasoning behind each change. Drafts stay internal until you decide to use them.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[240px]">
            <span className="section-label block mb-1.5">Clause</span>
            <select
              value={selectedClause}
              onChange={(e) => setSelectedClause(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-navy"
            >
              <option value="">Choose a clause…</option>
              {clauses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.category}: {c.title}
                </option>
              ))}
            </select>
          </label>
          <Button
            onClick={() => negotiate(selectedClause)}
            disabled={!selectedClause || busy !== null}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Handshake size={14} />}
            Suggest edits
          </Button>
        </div>
      </Card>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {!suggestions && (
        <div className="flex items-center gap-2 text-sm text-ink-faint">
          <Loader2 size={14} className="animate-spin" /> Loading suggestions…
        </div>
      )}

      {suggestions && suggestions.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-faint">
            No suggestions yet. Choose a clause above to draft one.
          </p>
        </Card>
      )}

      {suggestions?.map((s) => {
        const open = expanded[s.id] !== false;
        return (
          <Card key={s.id} className="p-6">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <div>
                <span className="section-label text-brass">Suggested edit</span>
                <h3 className="font-medium text-ink mt-0.5">
                  {clauses.find((c) => c.id === s.clause_id)?.title || "Clause"}
                </h3>
              </div>
              {onDraftFromSuggestion && (
                <Button variant="secondary" size="sm" onClick={() => onDraftFromSuggestion(s)}>
                  Use in a draft
                </Button>
              )}
            </div>

            {s.concern && (
              <div className="mb-3 rounded-md border border-brass/30 bg-brass-soft px-3.5 py-3">
                <div className="section-label mb-1 text-brass">Concern</div>
                <p className="text-sm text-ink-soft">{s.concern}</p>
              </div>
            )}

            <div className="grid md:grid-cols-2 gap-3">
              <div className="rounded-md border border-line bg-paper px-4 py-3">
                <div className="section-label mb-1.5">Current wording</div>
                <p className="text-sm text-ink-soft italic leading-relaxed">
                  {s.original_text || "—"}
                </p>
              </div>
              <div className="rounded-md border border-navy/20 bg-navy/5 px-4 py-3">
                <div className="section-label mb-1.5 text-navy">Proposed wording</div>
                <p className="text-sm text-ink-soft leading-relaxed">
                  {s.proposed_text || "—"}
                </p>
              </div>
            </div>

            {s.rationale && (
              <p className="mt-3 text-sm text-ink-soft">
                <span className="section-label mr-1">Why:</span> {s.rationale}
              </p>
            )}

            {s.negotiation_points && s.negotiation_points.length > 0 && (
              <div className="mt-3">
                <div className="section-label mb-1.5">Talking points for the negotiation</div>
                <ul className="space-y-1">
                  {s.negotiation_points.map((p, i) => (
                    <li key={i} className="text-sm text-ink-soft flex gap-2">
                      <span className="text-brass mt-1 h-1 w-1 rounded-full bg-brass shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="mt-4 flex items-start gap-1.5 text-xs text-ink-faint">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              This is a drafting aid, not legal advice. Review any change with a qualified
              professional before sending it to a counterparty.
            </p>
          </Card>
        );
      })}
    </div>
  );
}
