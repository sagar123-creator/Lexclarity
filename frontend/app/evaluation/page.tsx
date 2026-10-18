"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Gauge,
  Loader2,
  ArrowLeft,
  PlayCircle,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { Card, Button } from "@/components/ui/primitives";
import { Badge } from "@/components/ui/Badge";
import { api, ApiError } from "@/lib/api";
import type { EvaluationRun, EvaluationStatus } from "@/types";

/**
 * Accuracy evaluation dashboard. When no real evaluation run exists this page
 * shows "Not evaluated" — it never fabricates scores or displays mock metrics.
 */
export default function EvaluationPage() {
  const [status, setStatus] = useState<EvaluationStatus | null>(null);
  const [runs, setRuns] = useState<EvaluationRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([api.getEvaluationStatus(), api.listEvaluationRuns()]);
      setStatus(s);
      setRuns(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load evaluation status.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function triggerRun() {
    setRunning(true);
    setError(null);
    try {
      await api.runEvaluation();
      await load();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Evaluation failed — check the backend logs for details."
      );
    } finally {
      setRunning(false);
    }
  }

  const metrics = status?.metrics || null;

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink mb-6"
        >
          <ArrowLeft size={14} /> Back to dashboard
        </Link>

        <div className="mb-8">
          <div className="section-label mb-2">Accuracy evaluation</div>
          <h1 className="font-serif text-2xl font-semibold">How well is LexClarity performing?</h1>
          <p className="mt-1 text-sm text-ink-faint max-w-2xl">
            Runs the real pipeline against a labelled dataset and scores risk detection and
            clause extraction. This dashboard reports only actual measured runs.
          </p>
        </div>

        {error && (
          <p className="mb-6 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
        )}

        {!status && !error && (
          <div className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" /> Loading evaluation status…
          </div>
        )}

        {status && !status.evaluated && (
          <Card className="p-10 text-center">
            <Gauge size={26} className="mx-auto text-ink-faint mb-3" />
            <h2 className="font-serif text-lg font-semibold mb-1">Not evaluated</h2>
            <p className="text-sm text-ink-faint max-w-md mx-auto mb-5">
              {status.message ||
                "No completed evaluation run exists yet. Accuracy metrics will appear here after a real run."}
            </p>
            <Button onClick={triggerRun} disabled={running}>
              {running ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <PlayCircle size={14} />
              )}
              Run evaluation now
            </Button>
            <p className="mt-3 text-xs text-ink-faint">
              This executes the full pipeline (including LLM calls) and may take several minutes.
            </p>
          </Card>
        )}

        {status?.evaluated && (
          <div className="space-y-6">
            <Card className="p-6">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-risk-low" />
                  <h2 className="font-serif text-lg font-semibold">Evaluated</h2>
                  {status.dataset_name && <Badge>{status.dataset_name}</Badge>}
                </div>
                <Button variant="secondary" size="sm" onClick={triggerRun} disabled={running}>
                  {running ? <Loader2 size={13} className="animate-spin" /> : <PlayCircle size={13} />}
                  Re-run
                </Button>
              </div>
              {status.finished_at && (
                <p className="font-mono text-xs text-ink-faint">
                  Last run finished {new Date(status.finished_at).toLocaleString()}
                </p>
              )}

              {metrics && (
                <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(metrics).map(([key, value]) => (
                    <div key={key} className="rounded-md border border-line bg-paper px-4 py-3">
                      <div className="section-label mb-1">{formatMetricKey(key)}</div>
                      <p className="text-lg font-serif font-semibold text-ink">
                        {formatMetricValue(value)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {runs && runs.length > 0 && (
          <Card className="p-6 mt-6">
            <div className="section-label mb-3">Run history</div>
            <div className="space-y-2">
              {runs.map((r) => (
                <div
                  key={r.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-line px-4 py-2.5"
                >
                  <div className="flex items-center gap-2.5">
                    {r.status === "completed" ? (
                      <CheckCircle2 size={14} className="text-risk-low" />
                    ) : r.status === "failed" ? (
                      <AlertTriangle size={14} className="text-risk-high" />
                    ) : (
                      <Loader2 size={14} className="animate-spin text-ink-faint" />
                    )}
                    <span className="text-sm text-ink">{r.dataset_name}</span>
                    <Badge>{r.status}</Badge>
                  </div>
                  <span className="font-mono text-xs text-ink-faint">
                    {new Date(r.started_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        )}

        <div className="mt-10">
          <Disclaimer />
        </div>
      </main>
    </div>
  );
}

function formatMetricKey(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatMetricValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
