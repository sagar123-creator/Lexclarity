"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FilePen,
  Loader2,
  Download,
  Save,
  Plus,
  Highlighter,
} from "lucide-react";
import { Card, Button } from "@/components/ui/primitives";
import { api, ApiError, API_BASE } from "@/lib/api";
import type { Draft, TemplateInfo } from "@/types";

/**
 * Document generator: AI drafts for common legal letters/notices, always
 * marked as AI-generated with [PLACEHOLDER: ...] markers for facts the model
 * must not invent. Drafts are editable and exportable as Markdown; nothing is
 * ever sent externally.
 */
export function GeneratorTab({
  documentId,
  prefillActionId,
  prefillInstructions,
}: {
  documentId: string;
  prefillActionId?: string | null;
  prefillInstructions?: string | null;
}) {
  const [templates, setTemplates] = useState<TemplateInfo[]>([]);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [kind, setKind] = useState("");
  const [instructions, setInstructions] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTemplates()
      .then((t) => {
        setTemplates(t);
        if (t.length > 0) setKind((k) => k || t[0].kind);
      })
      .catch(() => setTemplates([]));
  }, []);

  const loadDrafts = useCallback(async () => {
    try {
      setDrafts(await api.listDrafts(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load drafts.");
    }
  }, [documentId]);

  useEffect(() => {
    loadDrafts();
  }, [loadDrafts]);

  useEffect(() => {
    if (prefillInstructions) setInstructions(prefillInstructions);
  }, [prefillInstructions]);

  async function create() {
    if (!kind || creating) return;
    setCreating(true);
    setError(null);
    try {
      const draft = await api.createDraft(documentId, {
        kind,
        ...(prefillActionId ? { action_item_id: prefillActionId } : {}),
        ...(instructions ? { user_instructions: instructions } : {}),
      });
      await loadDrafts();
      setOpenId(draft.id);
      setEditContent(draft.content);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the draft.");
    } finally {
      setCreating(false);
    }
  }

  async function save(draft: Draft) {
    setSavingId(draft.id);
    setError(null);
    try {
      await api.updateDraft(draft.id, { content: editContent ?? draft.content });
      await loadDrafts();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the draft.");
    } finally {
      setSavingId(null);
    }
  }

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex items-center gap-2 mb-1">
          <FilePen size={16} className="text-navy" />
          <h3 className="font-serif text-lg font-semibold">Generate a draft</h3>
        </div>
        <p className="text-sm text-ink-faint mb-4">
          AI-drafted documents for common legal tasks. Facts the model cannot verify from your
          document are left as{" "}
          <span className="font-mono text-xs text-brass">[PLACEHOLDER: …]</span> markers rather
          than invented. Every draft is editable and clearly labelled as AI-generated.
        </p>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[220px]">
            <span className="section-label block mb-1.5">Template</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="w-full rounded-md border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-navy"
            >
              {templates.map((t) => (
                <option key={t.kind} value={t.kind}>
                  {t.title}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={create} disabled={!kind || creating}>
            {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Generate draft
          </Button>
        </div>

        {kind && templates.find((t) => t.kind === kind) && (
          <p className="mt-2 text-xs text-ink-faint">
            {templates.find((t) => t.kind === kind)?.description}
          </p>
        )}

        <label className="block mt-4">
          <span className="section-label block mb-1.5">Extra instructions (optional)</span>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            rows={2}
            placeholder="Anything specific this draft should say or avoid…"
            className="w-full rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy resize-none"
          />
        </label>
      </Card>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {!drafts && (
        <div className="flex items-center gap-2 text-sm text-ink-faint">
          <Loader2 size={14} className="animate-spin" /> Loading drafts…
        </div>
      )}

      {drafts && drafts.length === 0 && (
        <Card className="p-8 text-center">
          <p className="text-sm text-ink-faint">No drafts yet — generate one above.</p>
        </Card>
      )}

      {drafts?.map((d) => {
        const open = openId === d.id;
        const dPlaceholders = (d.content.match(/\[PLACEHOLDER:[^\]]*\]/g) || []).length;
        return (
          <Card key={d.id} className="overflow-hidden">
            <button
              onClick={() => {
                setOpenId(open ? null : d.id);
                setEditContent(open ? null : d.content);
              }}
              className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-paper transition-colors"
            >
              <div>
                <span className="section-label text-brass">{d.kind.replace(/_/g, " ")}</span>
                <h3 className="font-medium text-ink mt-0.5">{d.title}</h3>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                {d.is_ai_generated && <span className="font-mono text-[10px] uppercase tracking-wide text-brass border border-brass/30 rounded-sm px-1.5 py-0.5">AI draft</span>}
                {d.edited_by_user && <span className="font-mono text-[10px] uppercase tracking-wide text-ink-faint border border-line rounded-sm px-1.5 py-0.5">Edited</span>}
                {dPlaceholders > 0 && (
                  <span className="font-mono text-[10px] uppercase tracking-wide text-risk-medium border border-risk-medium/30 rounded-sm px-1.5 py-0.5">
                    {dPlaceholders} placeholder{dPlaceholders > 1 ? "s" : ""}
                  </span>
                )}
              </div>
            </button>

            {open && (
              <div className="px-6 pb-6 border-t border-line pt-4 space-y-3">
                <textarea
                  value={editContent ?? d.content}
                  onChange={(e) => setEditContent(e.target.value)}
                  rows={16}
                  className="w-full rounded-md border border-line bg-paper px-4 py-3 font-mono text-[13px] leading-relaxed text-ink-soft outline-none focus:border-navy resize-y"
                />
                <div className="flex flex-wrap items-center gap-3">
                  <Button size="sm" onClick={() => save(d)} disabled={savingId === d.id}>
                    {savingId === d.id ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <Save size={13} />
                    )}
                    Save changes
                  </Button>
                  <a
                    href={`${API_BASE}/api/drafts/${d.id}/export`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-navy hover:underline"
                  >
                    <Download size={13} /> Export Markdown
                  </a>
                  {dPlaceholders > 0 && openId === d.id && (
                    <span className="flex items-center gap-1.5 text-xs text-brass">
                      <Highlighter size={12} />
                      Fill in {dPlaceholders} highlighted placeholder
                      {dPlaceholders > 1 ? "s" : ""} before using this draft.
                    </span>
                  )}
                </div>
                <p className="text-xs text-ink-faint">
                  AI-generated draft — review carefully and fill every placeholder. LexClarity
                  never sends this document anywhere.
                </p>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
