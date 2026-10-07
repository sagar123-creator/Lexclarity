import Link from "next/link";
import {
  ArrowRight, FileSearch, ShieldAlert, MessageSquareText,
  ScrollText, CalendarClock, Users, Sparkles,
} from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { Card } from "@/components/ui/primitives";

const FEATURES = [
  {
    icon: ScrollText,
    title: "Structured summaries",
    desc: "Executive summary, document type, and a plain-English walkthrough of what you actually agreed to.",
  },
  {
    icon: ShieldAlert,
    title: "Risk analysis",
    desc: "Clauses that may warrant a second look — rated High, Medium, or Low, each with a plain explanation.",
  },
  {
    icon: Users,
    title: "Parties & obligations",
    desc: "Who's who, and exactly what each party is required to do — sourced to the clause it comes from.",
  },
  {
    icon: CalendarClock,
    title: "Key dates & deadlines",
    desc: "Notice periods, renewal windows, and payment schedules pulled out of dense contract language.",
  },
  {
    icon: Sparkles,
    title: "Explain Simply",
    desc: "Any clause, translated from legalese into language that doesn't require a law degree.",
  },
  {
    icon: MessageSquareText,
    title: "Ask LexClarity",
    desc: "A chatbot that answers only from your document — with a page and section cited for every claim.",
  },
];

const STEPS = [
  { label: "Upload", desc: "PDF, DOCX, or TXT — drag in your contract or agreement." },
  { label: "Analyze", desc: "LexClarity extracts, chunks, and indexes the document for retrieval." },
  { label: "Understand", desc: "Read the summary, risks, clauses, obligations, and key dates." },
  { label: "Ask", desc: "Chat with the document itself. Every answer cites its source." },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />

      {/* Hero */}
      <section className="border-b border-line">
        <div className="mx-auto max-w-6xl px-6 py-20 grid lg:grid-cols-[1.1fr_0.9fr] gap-14 items-center">
          <div>
            <div className="section-label mb-5">§ AI Legal Document Analyzer</div>
            <h1 className="font-serif text-5xl md:text-6xl leading-[1.05] font-semibold tracking-tight text-ink">
              Understand legal
              <br />
              documents.{" "}
              <span className="text-navy italic">Clearly.</span>
            </h1>
            <p className="mt-6 text-lg text-ink-soft max-w-xl leading-relaxed">
              Upload a contract and LexClarity reads it the way a careful colleague
              would — surfacing the risks, obligations, and deadlines buried in
              the clauses, then answering your questions with citations back to
              the source text. Nothing invented, nothing assumed.
            </p>
            <div className="mt-9 flex items-center gap-4">
              <Link
                href="/upload"
                className="inline-flex items-center gap-2 rounded-md bg-navy px-6 py-3.5 text-white font-medium hover:bg-navy-dark transition-colors"
              >
                Analyze a Document <ArrowRight size={16} />
              </Link>
              <Link href="/dashboard" className="text-sm font-medium text-ink-soft hover:text-ink">
                View dashboard
              </Link>
            </div>
          </div>

          {/* Signature element: a stylized "annotated clause" card */}
          <Card className="p-0 overflow-hidden">
            <div className="border-b border-line px-5 py-3 flex items-center justify-between">
              <span className="font-mono text-xs text-ink-faint">service_agreement.pdf — p.8</span>
              <span className="font-mono text-xs text-risk-medium bg-risk-mediumBg px-2 py-0.5 rounded-sm">
                MEDIUM RISK
              </span>
            </div>
            <div className="px-5 py-5 space-y-4">
              <div>
                <div className="section-label mb-1.5">§12 — Termination</div>
                <p className="text-sm text-ink-soft leading-relaxed border-l-2 border-line pl-3">
                  "Either Party may terminate this Agreement for any reason upon
                  ninety (90) days' prior written notice..."
                </p>
              </div>
              <div className="rounded-md bg-paper border border-line p-3.5">
                <div className="section-label mb-1 text-navy">Plain English</div>
                <p className="text-sm text-ink-soft">
                  Either side can walk away without a reason — they just need to
                  give 90 days' notice first.
                </p>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <MessageSquareText size={14} className="text-brass" />
                <p className="text-xs text-ink-faint italic">
                  "What's my notice period?" → 90 days, cited to Page 8, §12.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <div className="section-label mb-3">What you get</div>
        <h2 className="font-serif text-3xl font-semibold mb-12 max-w-xl">
          Every document, broken down the same rigorous way.
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <div key={f.title} className="p-6 rounded-lg border border-line bg-white">
              <f.icon size={20} className="text-navy mb-4" strokeWidth={1.75} />
              <h3 className="font-medium text-ink mb-1.5">{f.title}</h3>
              <p className="text-sm text-ink-faint leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="border-y border-line bg-white">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <div className="section-label mb-3">How it works</div>
          <h2 className="font-serif text-3xl font-semibold mb-12 max-w-xl">
            Upload → Analyze → Understand → Ask
          </h2>
          <div className="grid md:grid-cols-4 gap-8">
            {STEPS.map((s, i) => (
              <div key={s.label} className="relative">
                <div className="font-mono text-xs text-brass mb-3">
                  {String(i + 1).padStart(2, "0")}
                </div>
                <h3 className="font-serif text-lg font-semibold mb-1.5">{s.label}</h3>
                <p className="text-sm text-ink-faint leading-relaxed">{s.desc}</p>
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-1.5 -right-4 w-8 border-t border-dashed border-line" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <Card className="p-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 bg-navy text-white border-none">
          <div>
            <h3 className="font-serif text-2xl font-semibold mb-2">
              Ready to see what's actually in your contract?
            </h3>
            <p className="text-white/70 text-sm max-w-md">
              Upload any employment agreement, NDA, lease, or service contract
              to get started. No legal background required.
            </p>
          </div>
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 rounded-md bg-white text-navy px-6 py-3.5 font-medium hover:bg-paper transition-colors whitespace-nowrap"
          >
            Analyze a Document <ArrowRight size={16} />
          </Link>
        </Card>
      </section>

      <footer className="mx-auto max-w-6xl px-6 pb-16">
        <Disclaimer />
      </footer>
    </div>
  );
}
