"use client";

import clsx from "clsx";
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  AlertTriangle,
} from "lucide-react";

const STYLES: Record<
  string,
  { className: string; label: string; Icon: typeof CheckCircle2 }
> = {
  supported: {
    className: "bg-risk-lowBg text-risk-low",
    label: "Supported",
    Icon: CheckCircle2,
  },
  contradicted: {
    className: "bg-risk-highBg text-risk-high",
    label: "Contradicted",
    Icon: XCircle,
  },
  insufficient: {
    className: "bg-line/60 text-ink-soft",
    label: "Insufficient evidence",
    Icon: HelpCircle,
  },
  needs_review: {
    className: "bg-brass-soft text-brass",
    label: "Needs review",
    Icon: AlertTriangle,
  },
};

/**
 * Trust indicator for a finding. Every label maps to a deterministic
 * verification status computed by the backend — never an LLM opinion alone.
 */
export function VerificationBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  if (!status) return null;
  const style = STYLES[status];
  if (!style) return null;
  const { className: styleClass, label, Icon } = style;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium font-mono uppercase tracking-wide",
        styleClass,
        className
      )}
      title={`Verification status: ${label}`}
    >
      <Icon size={12} /> {label}
    </span>
  );
}
