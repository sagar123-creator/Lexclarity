"use client";

import clsx from "clsx";

export type SectionKey = "analyze" | "act";

/**
 * Top-level section switcher: ANALYZE (understand the document) vs ACT
 * (do something about it). Two tabs only — the visual weight stays on content.
 */
export function SectionNav({
  value,
  onChange,
  analyzeCount,
  actCount,
}: {
  value: SectionKey;
  onChange: (v: SectionKey) => void;
  analyzeCount?: number;
  actCount?: number;
}) {
  return (
    <div className="inline-flex rounded-md border border-line bg-white p-1">
      <button
        onClick={() => onChange("analyze")}
        className={clsx(
          "rounded-sm px-5 py-2 text-sm font-medium tracking-wide transition-colors",
          value === "analyze" ? "bg-navy text-white" : "text-ink-soft hover:text-ink"
        )}
      >
        ANALYZE
        {analyzeCount != null && (
          <span className="ml-1.5 font-mono text-xs opacity-70">{analyzeCount}</span>
        )}
      </button>
      <button
        onClick={() => onChange("act")}
        className={clsx(
          "rounded-sm px-5 py-2 text-sm font-medium tracking-wide transition-colors",
          value === "act" ? "bg-navy text-white" : "text-ink-soft hover:text-ink"
        )}
      >
        ACT
        {actCount != null && (
          <span className="ml-1.5 font-mono text-xs opacity-70">{actCount}</span>
        )}
      </button>
    </div>
  );
}
