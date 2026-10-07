"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Inbox, Plus } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { DocumentCard } from "@/components/dashboard/DocumentCard";
import { Button } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { DocumentSummaryCard } from "@/types";

export default function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentSummaryCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .listDocuments()
      .then((docs) => active && setDocuments(docs))
      .catch(() => active && setError("Couldn't load your documents. Is the backend running?"));

    // Light polling so in-progress documents update their status live
    const interval = setInterval(() => {
      api.listDocuments().then((docs) => active && setDocuments(docs)).catch(() => {});
    }, 4000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-6xl w-full px-6 py-12 flex-1">
        <div className="flex items-center justify-between mb-8">
          <div>
            <div className="section-label mb-2">Dashboard</div>
            <h1 className="font-serif text-3xl font-semibold">Your documents</h1>
          </div>
          <Link href="/upload">
            <Button>
              <Plus size={16} /> Analyze Document
            </Button>
          </Link>
        </div>

        {error && (
          <div className="rounded-md border border-risk-high/20 bg-risk-highBg p-4 text-sm text-risk-high mb-6">
            {error}
          </div>
        )}

        {documents === null && !error && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-40 rounded-lg border border-line bg-white animate-pulse" />
            ))}
          </div>
        )}

        {documents && documents.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center rounded-lg border border-dashed border-line">
            <Inbox size={32} className="text-ink-faint mb-4" strokeWidth={1.5} />
            <p className="font-medium text-ink mb-1">No documents yet</p>
            <p className="text-sm text-ink-faint mb-6 max-w-sm">
              Upload your first legal document to get a summary, risk analysis, and a
              chatbot that can answer questions about it.
            </p>
            <Link href="/upload">
              <Button>
                <Plus size={16} /> Analyze Document
              </Button>
            </Link>
          </div>
        )}

        {documents && documents.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {documents.map((doc) => (
              <DocumentCard key={doc.id} doc={doc} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
