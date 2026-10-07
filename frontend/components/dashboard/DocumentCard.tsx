import Link from "next/link";
import { FileText, FileType2, File as FileIcon } from "lucide-react";
import { Badge, riskVariant, statusVariant } from "@/components/ui/Badge";
import { Card } from "@/components/ui/primitives";
import type { DocumentSummaryCard } from "@/types";

function fileIconFor(type: string) {
  if (type === "pdf") return FileText;
  if (type === "docx") return FileType2;
  return FileIcon;
}

function statusLabel(status: string) {
  if (status === "ready") return "Analyzed";
  if (status === "failed") return "Failed";
  return "Processing";
}

export function DocumentCard({ doc }: { doc: DocumentSummaryCard }) {
  const Icon = fileIconFor(doc.file_type);
  const href = doc.status === "ready" || doc.status === "failed"
    ? `/documents/${doc.id}`
    : `/upload`;

  return (
    <Link href={href}>
      <Card className="p-5 hover:border-navy/30 transition-colors h-full flex flex-col">
        <div className="flex items-start justify-between mb-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-paper border border-line">
            <Icon size={16} className="text-navy" />
          </span>
          <Badge variant={statusVariant(doc.status)}>{statusLabel(doc.status)}</Badge>
        </div>
        <p className="font-medium text-ink text-sm mb-1 line-clamp-2">{doc.filename}</p>
        <p className="text-xs text-ink-faint mb-4">
          {doc.document_type || "Document type pending"}
        </p>
        <div className="mt-auto flex items-center justify-between">
          <span className="text-xs text-ink-faint">
            {new Date(doc.created_at).toLocaleDateString()}
          </span>
          {doc.status === "ready" && doc.overall_risk_level && (
            <Badge variant={riskVariant(doc.overall_risk_level)}>
              {doc.overall_risk_level} Risk
            </Badge>
          )}
        </div>
      </Card>
    </Link>
  );
}
