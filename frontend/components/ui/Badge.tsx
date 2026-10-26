import clsx from "clsx";

type BadgeVariant =
  | "default"
  | "high"
  | "medium"
  | "low"
  | "processing"
  | "ready"
  | "failed"
  | "stopped";

const variantStyles: Record<BadgeVariant, string> = {
  default: "bg-line/60 text-ink-soft",
  high: "bg-risk-highBg text-risk-high",
  medium: "bg-risk-mediumBg text-risk-medium",
  low: "bg-risk-lowBg text-risk-low",
  processing: "bg-brass-soft text-brass",
  ready: "bg-risk-lowBg text-risk-low",
  failed: "bg-risk-highBg text-risk-high",
  stopped: "bg-line/60 text-ink-soft",
};

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium font-mono uppercase tracking-wide",
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function riskVariant(level: string | null | undefined): BadgeVariant {
  if (level === "High") return "high";
  if (level === "Medium") return "medium";
  if (level === "Low") return "low";
  return "default";
}

export function statusVariant(status: string): BadgeVariant {
  if (status === "ready") return "ready";
  if (status === "failed") return "failed";
  if (status === "stopped") return "stopped";
  return "processing";
}
