"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CalendarClock,
  Loader2,
  CheckCircle2,
  XCircle,
  BellPlus,
  Trash2,
} from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/Badge";
import { api, ApiError } from "@/lib/api";
import type { Reminder, ImportantDateItem } from "@/types";

/**
 * Deadline tracker: reminders derived from document dates plus manual ones.
 * Inferred dates are labelled as such. Reminders are internal only — no
 * emails or external notifications are ever sent.
 */
export function DeadlinesTab({
  documentId,
  dates,
  refreshToken,
}: {
  documentId: string;
  dates: ImportantDateItem[];
  refreshToken?: number;
}) {
  const [reminders, setReminders] = useState<Reminder[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", due_date: "", note: "" });

  const load = useCallback(async () => {
    try {
      setReminders(await api.getReminders(documentId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load reminders.");
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load, refreshToken]);

  async function update(r: Reminder, patch: { status?: string }) {
    setBusyId(r.id);
    try {
      const updated = await api.updateReminder(r.id, patch);
      setReminders((prev) => (prev || []).map((x) => (x.id === updated.id ? updated : x)));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not update the reminder.");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(r: Reminder) {
    setBusyId(r.id);
    try {
      await api.deleteReminder(r.id);
      setReminders((prev) => (prev || []).filter((x) => x.id !== r.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not delete the reminder.");
    } finally {
      setBusyId(null);
    }
  }

  async function createFromForm(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) return;
    setBusyId("new");
    try {
      await api.createReminder(documentId, {
        title: form.title.trim(),
        due_date: form.due_date || undefined,
        note: form.note || undefined,
      });
      setForm({ title: "", due_date: "", note: "" });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the reminder.");
    } finally {
      setBusyId(null);
    }
  }

  async function createFromDate(date: ImportantDateItem) {
    setBusyId(date.id);
    try {
      await api.createReminder(documentId, {
        date_id: date.id,
        title: date.label,
        due_date: date.normalized_date || date.date_value || undefined,
      });
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the reminder.");
    } finally {
      setBusyId(null);
    }
  }

  const list = reminders || [];
  const pending = list.filter((r) => r.status === "pending");
  const done = list.filter((r) => r.status !== "pending");
  const dateIdsWithReminder = new Set(
    list.map((r) => r.date_id).filter(Boolean) as string[]
  );
  const availableDates = dates.filter((d) => !dateIdsWithReminder.has(d.id));

  return (
    <div className="space-y-5">
      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <CalendarClock size={16} className="text-navy" />
              <h3 className="font-serif text-lg font-semibold">Deadlines & reminders</h3>
            </div>
            <p className="text-sm text-ink-faint">
              Track key dates from this document. Reminders are internal — nothing is emailed or
              sent automatically.
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setShowForm((s) => !s)}>
            <BellPlus size={13} /> New reminder
          </Button>
        </div>

        {showForm && (
          <form onSubmit={createFromForm} className="mt-4 grid md:grid-cols-3 gap-3">
            <input
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Title"
              className="rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-navy"
            />
            <input
              type="date"
              value={form.due_date}
              onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))}
              className="rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-navy"
            />
            <input
              value={form.note}
              onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
              placeholder="Note (optional)"
              className="rounded-md border border-line bg-white px-3 py-2 text-sm outline-none focus:border-navy"
            />
            <div className="md:col-span-3">
              <Button type="submit" size="sm" disabled={busyId === "new" || !form.title.trim()}>
                {busyId === "new" ? <Loader2 size={13} className="animate-spin" /> : <BellPlus size={13} />}
                Create reminder
              </Button>
            </div>
          </form>
        )}
      </Card>

      {error && (
        <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
      )}

      {!reminders && (
        <div className="flex items-center gap-2 text-sm text-ink-faint">
          <Loader2 size={14} className="animate-spin" /> Loading reminders…
        </div>
      )}

      {reminders && (
        <>
          <div className="space-y-3">
            {pending.length === 0 && (
              <Card className="p-6 text-center">
                <p className="text-sm text-ink-faint">
                  No pending deadlines. Create one manually or add a reminder from a document date.
                </p>
              </Card>
            )}
            {pending.map((r) => (
              <ReminderRow key={r.id} reminder={r} busy={busyId === r.id} onUpdate={update} onRemove={remove} />
            ))}
          </div>

          {availableDates.length > 0 && (
            <div>
              <div className="section-label mb-2">Document dates not yet tracked</div>
              <div className="flex flex-wrap gap-2">
                {availableDates.map((d) => (
                  <button
                    key={d.id}
                    disabled={busyId === d.id}
                    onClick={() => createFromDate(d)}
                    className="flex items-center gap-1.5 rounded-md border border-line bg-white px-3 py-1.5 text-xs text-ink-soft hover:border-navy hover:text-navy transition-colors disabled:opacity-50"
                  >
                    <BellPlus size={12} className="text-brass" />
                    {d.label}
                    {(d.normalized_date || d.date_value) && (
                      <span className="font-mono text-ink-faint">
                        · {d.normalized_date || d.date_value}
                      </span>
                    )}
                    {d.date_kind === "inferred" && (
                      <span className="font-mono uppercase text-[10px] text-brass">inferred</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {done.length > 0 && (
            <div>
              <div className="section-label mb-2">Completed & dismissed</div>
              <div className="space-y-2">
                {done.map((r) => (
                  <ReminderRow key={r.id} reminder={r} busy={busyId === r.id} onUpdate={update} onRemove={remove} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ReminderRow({
  reminder,
  busy,
  onUpdate,
  onRemove,
}: {
  reminder: Reminder;
  busy: boolean;
  onUpdate: (r: Reminder, patch: { status?: string }) => void;
  onRemove: (r: Reminder) => void;
}) {
  const done = reminder.status !== "pending";
  const CheckIcon = reminder.status === "dismissed" ? XCircle : CheckCircle2;
  return (
    <Card className={clsx("p-4 flex flex-wrap items-center justify-between gap-3", done && "opacity-70")}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={clsx("font-medium text-ink", done && "line-through")}>
            {reminder.title}
          </span>
          {reminder.due_date_kind === "inferred" && <Badge variant="medium">Inferred date</Badge>}
        </div>
        <div className="flex flex-wrap items-baseline gap-x-3 mt-0.5">
          {reminder.due_date && (
            <span className="font-mono text-sm text-brass">{reminder.due_date}</span>
          )}
          {reminder.note && <span className="text-xs text-ink-faint">{reminder.note}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          disabled={busy}
          onClick={() => onUpdate(reminder, { status: done ? "pending" : "completed" })}
          className={clsx(
            "flex items-center gap-1 rounded-sm border px-2 py-1 text-[11px] font-mono uppercase tracking-wide transition-colors disabled:opacity-50",
            reminder.status === "completed"
              ? "border-risk-low bg-risk-lowBg text-risk-low"
              : "border-line text-ink-faint hover:border-risk-low hover:text-risk-low"
          )}
        >
          <CheckIcon size={11} /> {done ? "Reopen" : "Done"}
        </button>
        {!done && (
          <button
            disabled={busy}
            onClick={() => onUpdate(reminder, { status: "dismissed" })}
            className="flex items-center gap-1 rounded-sm border border-line px-2 py-1 text-[11px] font-mono uppercase tracking-wide text-ink-faint hover:border-risk-high hover:text-risk-high transition-colors disabled:opacity-50"
          >
            <XCircle size={11} /> Dismiss
          </button>
        )}
        <button
          disabled={busy}
          onClick={() => onRemove(reminder)}
          className="rounded-sm border border-line p-1.5 text-ink-faint hover:border-risk-high hover:text-risk-high transition-colors disabled:opacity-50"
          aria-label="Delete reminder"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </Card>
  );
}
