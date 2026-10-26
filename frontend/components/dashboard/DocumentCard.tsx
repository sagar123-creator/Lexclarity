"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, FileType2, File as FileIcon, XCircle } from "lucide-react";
import { Badge, riskVariant, statusVariant } from "@/components/ui/Badge";
import { Card } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { ACTIVE_STATUSES } from "@/types";
import type { DocumentStatus, DocumentSummaryCard } from "@/types";

function fileIconFor(type: string) {
  if (type === "pdf") return FileText;
  if (type === "docx") return FileType2;
  return FileIcon;
}

function statusLabel(status: DocumentStatus) {
  if (status === "ready") return "Analyzed";
  if (status === "failed") return "Failed";
  if (status === "stopped") return "Stopped";
  return "Processing";
}

export function DocumentCard({ doc }: { doc: DocumentSummaryCard }) {
  // Local view of the status so a stop can settle here without waiting for the
  // dashboard's list to be re-fetched.
  const [status, setStatus] = useState<DocumentStatus>(doc.status);
  const [stopping, setStopping] = useState(false);
  useEffect(() => {
    setStatus(doc.status);
  }, [doc.status]);

  const Icon = fileIconFor(doc.file_type);
  const isActive = ACTIVE_STATUSES.includes(status);
  const href =
    status === "ready" || status === "failed" || status === "stopped"
      ? `/documents/${doc.id}`
      : `/upload`;

  async function handleStop(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setStopping(true);
    try {
      await api.stopAnalysis(doc.id);
      // A live run settles at its next stage boundary, so give it a moment.
      // Stale "processing" rows (left behind by a restart) settle instantly.
      let settled: DocumentStatus | null = null;
      for (let i = 0; i < 90; i++) {
        const current = await api.getDocument(doc.id);
        if (!ACTIVE_STATUSES.includes(current.status)) {
          settled = current.status;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      if (settled) setStatus(settled);
    } catch {
      // Leave the badge as-is; the request will still be honoured server-side
      // if it reached the API (e.g. only the status poll failed).
    } finally {
      setStopping(false);
    }
  }

  return (
    <Link href={href}>
      <Card className="p-5 hover:border-navy/30 transition-colors h-full flex flex-col">
        <div className="flex items-start justify-between mb-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-paper border border-line">
            <Icon size={16} className="text-navy" />
          </span>
          <Badge variant={statusVariant(status)}>
            {stopping && isActive ? "Stopping…" : statusLabel(status)}
          </Badge>
        </div>
        <p className="font-medium text-ink text-sm mb-1 line-clamp-2">{doc.filename}</p>
        <p className="text-xs text-ink-faint mb-4">
          {doc.document_type || "Document type pending"}
        </p>
        <div className="mt-auto flex items-center justify-between">
          <span className="text-xs text-ink-faint">
            {new Date(doc.created_at).toLocaleDateString()}
          </span>
          {isActive ? (
            <button
              type="button"
              onClick={handleStop}
              disabled={stopping}
              className="inline-flex items-center gap-1 text-xs text-ink-faint hover:text-risk-high disabled:opacity-60 disabled:hover:text-ink-faint transition-colors"
            >
              <XCircle size={13} />
              {stopping ? "Stopping…" : "Stop processing"}
            </button>
          ) : (
            status === "ready" &&
            doc.overall_risk_level && (
              <Badge variant={riskVariant(doc.overall_risk_level)}>
                {doc.overall_risk_level} Risk
              </Badge>
            )
          )}
        </div>
      </Card>
    </Link>
  );
}
