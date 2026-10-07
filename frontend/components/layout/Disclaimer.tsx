import { ShieldAlert } from "lucide-react";

export function Disclaimer({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={
        compact
          ? "flex items-start gap-2.5 rounded-md border border-line bg-paper px-3.5 py-2.5 text-xs text-ink-faint"
          : "flex items-start gap-3 rounded-lg border border-brass/30 bg-brass-soft/40 px-5 py-4 text-sm text-ink-soft"
      }
    >
      <ShieldAlert size={compact ? 14 : 18} className="mt-0.5 shrink-0 text-brass" />
      <p>
        <strong className="font-semibold text-ink">Disclaimer:</strong> LexClarity is an
        AI-powered document analysis tool and does not provide legal advice. Its analysis
        may contain errors or omissions. Important legal decisions should be reviewed with
        a qualified legal professional.
      </p>
    </div>
  );
}
