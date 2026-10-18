"use client";

import clsx from "clsx";
import { useState, createContext, useContext } from "react";

export function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-line bg-white shadow-card",
        className
      )}
    >
      {children}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  ...props
}: {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const sizes = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2.5 text-sm",
  };
  const variants = {
    primary: "bg-navy text-white hover:bg-navy-dark",
    secondary: "bg-white text-ink border border-line hover:bg-paper",
    ghost: "text-ink-soft hover:bg-paper",
    danger: "bg-white text-risk-high border border-risk-high/30 hover:bg-risk-highBg",
  };
  return (
    <button className={clsx(base, sizes[size], variants[variant], className)} {...props}>
      {children}
    </button>
  );
}

// --- Tabs ---

const TabsContext = createContext<{
  active: string;
  setActive: (v: string) => void;
} | null>(null);

export function Tabs({
  defaultValue,
  value,
  onChange,
  children,
  className,
}: {
  defaultValue?: string;
  /** Controlled mode: supply both value and onChange. */
  value?: string;
  onChange?: (v: string) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const [internal, setInternal] = useState(defaultValue ?? "");
  const active = value !== undefined ? value : internal;
  const setActive = (v: string) => {
    if (value === undefined) setInternal(v);
    onChange?.(v);
  };
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-1 border-b border-line overflow-x-auto">{children}</div>
  );
}

export function TabsTrigger({ value, children }: { value: string; children: React.ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("TabsTrigger must be used within Tabs");
  const isActive = ctx.active === value;
  return (
    <button
      onClick={() => ctx.setActive(value)}
      className={clsx(
        "whitespace-nowrap px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors",
        isActive
          ? "border-navy text-navy"
          : "border-transparent text-ink-faint hover:text-ink-soft"
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, children }: { value: string; children: React.ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("TabsContent must be used within Tabs");
  if (ctx.active !== value) return null;
  return <div className="pt-6">{children}</div>;
}
