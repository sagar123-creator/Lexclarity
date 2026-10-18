"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Plus, Loader2, ArrowLeft } from "lucide-react";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { Disclaimer } from "@/components/layout/Disclaimer";
import { Card, Button } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";
import type { Workspace } from "@/types";

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      setWorkspaces(await api.listWorkspaces());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load workspaces.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      await api.createWorkspace(name.trim(), description.trim() || undefined);
      setName("");
      setDescription("");
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the workspace.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <SiteHeader />
      <main className="mx-auto max-w-6xl w-full px-6 py-10 flex-1">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-ink-faint hover:text-ink mb-6"
        >
          <ArrowLeft size={14} /> Back to dashboard
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
          <div>
            <div className="section-label mb-2">Multi-document workspaces</div>
            <h1 className="font-serif text-2xl font-semibold">Workspaces</h1>
            <p className="mt-1 text-sm text-ink-faint max-w-2xl">
              Group related contracts — a vendor, a matter, a renewal cycle — and ask questions
              across all of them at once, with per-document citations and conflict flags.
            </p>
          </div>
          <Button onClick={() => setShowForm((s) => !s)}>
            <Plus size={14} /> New workspace
          </Button>
        </div>

        {showForm && (
          <Card className="p-6 mb-6">
            <form onSubmit={create} className="grid md:grid-cols-3 gap-3">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Workspace name (e.g. Acme vendor contracts)"
                className="rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy"
              />
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Description (optional)"
                className="rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy md:col-span-2"
              />
              <div className="md:col-span-3">
                <Button type="submit" size="sm" disabled={creating || !name.trim()}>
                  {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Create workspace
                </Button>
              </div>
            </form>
          </Card>
        )}

        {error && (
          <p className="mb-4 text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
        )}

        {!workspaces && (
          <div className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" /> Loading workspaces…
          </div>
        )}

        {workspaces && workspaces.length === 0 && (
          <Card className="p-10 text-center">
            <FolderKanban size={24} className="mx-auto text-ink-faint mb-3" />
            <p className="text-sm text-ink-faint">
              No workspaces yet. Create one to group related documents.
            </p>
          </Card>
        )}

        {workspaces && workspaces.length > 0 && (
          <div className="grid md:grid-cols-2 gap-4">
            {workspaces.map((w) => (
              <Link key={w.id} href={`/workspaces/${w.id}`}>
                <Card className="p-6 h-full hover:border-navy transition-colors">
                  <div className="flex items-center gap-2.5 mb-2">
                    <FolderKanban size={16} className="text-navy" />
                    <h3 className="font-medium text-ink">{w.name}</h3>
                  </div>
                  {w.description && (
                    <p className="text-sm text-ink-faint">{w.description}</p>
                  )}
                  <p className="mt-3 font-mono text-xs text-ink-faint">
                    Created {new Date(w.created_at).toLocaleDateString()}
                  </p>
                </Card>
              </Link>
            ))}
          </div>
        )}

        <div className="mt-10">
          <Disclaimer />
        </div>
      </main>
    </div>
  );
}
