"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { UploadDropzone } from "@/components/upload/UploadDropzone";
import { ProcessingStepper } from "@/components/upload/ProcessingStepper";
import { Card, Button } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { DocumentStatus } from "@/types";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [status, setStatus] = useState<DocumentStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleUpload(selected: File) {
    setFile(selected);
    setUploading(true);
    setError(null);
    try {
      const res = await api.uploadDocument(selected);
      setDocumentId(res.document.id);
      setStatus(res.document.status);
      startPolling(res.document.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  }

  function startPolling(id: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const doc = await api.getDocument(id);
        setStatus(doc.status);
        if (doc.status === "ready") {
          clearInterval(pollRef.current!);
          setTimeout(() => router.push(`/documents/${id}`), 600);
        } else if (doc.status === "failed") {
          clearInterval(pollRef.current!);
          setError(doc.error_message || "Processing failed.");
        }
      } catch {
        // transient network error while polling — keep trying
      }
    }, 2000);
  }

  async function handleRetry() {
    if (!documentId) return;
    setError(null);
    setStatus("uploaded");
    try {
      await api.retryAnalysis(documentId);
      startPolling(documentId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Retry failed.");
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-2xl w-full px-6 py-16 flex-1">
        <div className="section-label mb-3">Step 1 of 2</div>
        <h1 className="font-serif text-3xl font-semibold mb-2">Analyze a document</h1>
        <p className="text-ink-faint mb-8">
          Upload a legal document to get a structured summary, risk analysis, and a
          chatbot that can answer questions about it.
        </p>

        <Card className="p-8">
          {!documentId && (
            <UploadDropzone onFileSelected={handleUpload} disabled={uploading} />
          )}

          {documentId && status && status !== "failed" && (
            <div>
              <p className="text-sm text-ink-faint mb-6">
                Processing <span className="font-medium text-ink">{file?.name}</span>…
                this usually takes under a minute.
              </p>
              <ProcessingStepper status={status} />
            </div>
          )}

          {error && (
            <div className="mt-2 rounded-md border border-risk-high/20 bg-risk-highBg p-4">
              <div className="flex items-start gap-2.5">
                <AlertTriangle size={16} className="text-risk-high mt-0.5 shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-risk-high mb-1">
                    Processing failed
                  </p>
                  <p className="text-sm text-ink-soft">{error}</p>
                </div>
              </div>
              {documentId && (
                <Button variant="secondary" size="sm" className="mt-4" onClick={handleRetry}>
                  <RotateCcw size={14} /> Try again
                </Button>
              )}
            </div>
          )}
        </Card>

        <div className="mt-8">
          <Disclaimer compact />
        </div>
      </main>
    </div>
  );
}
