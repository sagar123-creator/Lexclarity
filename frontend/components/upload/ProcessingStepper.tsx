import { Check, Loader2 } from "lucide-react";
import clsx from "clsx";
import type { DocumentStatus } from "@/types";

const STAGES: { key: DocumentStatus; label: string }[] = [
  { key: "uploaded", label: "Upload received" },
  { key: "extracting", label: "Extracting text" },
  { key: "chunking", label: "Chunking document" },
  { key: "embedding", label: "Generating embeddings" },
  { key: "analyzing", label: "Analyzing content" },
  { key: "ready", label: "Ready" },
];

export function ProcessingStepper({ status }: { status: DocumentStatus }) {
  const currentIndex = STAGES.findIndex((s) => s.key === status);

  return (
    <div className="space-y-3">
      {STAGES.map((stage, i) => {
        const isDone = status === "ready" || i < currentIndex;
        const isCurrent = i === currentIndex && status !== "ready";
        return (
          <div key={stage.key} className="flex items-center gap-3">
            <span
              className={clsx(
                "flex h-6 w-6 items-center justify-center rounded-full text-xs shrink-0",
                isDone && "bg-risk-low text-white",
                isCurrent && "bg-navy text-white",
                !isDone && !isCurrent && "bg-line text-ink-faint"
              )}
            >
              {isDone ? <Check size={13} /> : isCurrent ? <Loader2 size={13} className="animate-spin" /> : i + 1}
            </span>
            <span
              className={clsx(
                "text-sm",
                isDone || isCurrent ? "text-ink font-medium" : "text-ink-faint"
              )}
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
