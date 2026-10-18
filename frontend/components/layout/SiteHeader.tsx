import Link from "next/link";
import { Scale } from "lucide-react";

export function SiteHeader() {
  return (
    <header className="border-b border-line bg-paper/95 backdrop-blur sticky top-0 z-40">
      <div className="mx-auto max-w-6xl px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 group">
          <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-navy text-white">
            <Scale size={16} strokeWidth={2} />
          </span>
          <span className="font-serif text-lg font-semibold tracking-tight">
            LexClarity
          </span>
        </Link>
        <nav className="flex items-center gap-6 text-sm">
          <Link href="/dashboard" className="text-ink-soft hover:text-ink transition-colors">
            Dashboard
          </Link>
          <Link href="/workspaces" className="text-ink-soft hover:text-ink transition-colors">
            Workspaces
          </Link>
          <Link href="/evaluation" className="text-ink-soft hover:text-ink transition-colors">
            Evaluation
          </Link>
          <Link
            href="/upload"
            className="rounded-md bg-navy px-4 py-2 text-white text-sm font-medium hover:bg-navy-dark transition-colors"
          >
            Analyze Document
          </Link>
        </nav>
      </div>
    </header>
  );
}
