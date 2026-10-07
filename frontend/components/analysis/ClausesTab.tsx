"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/primitives";
import type { ClauseItem } from "@/types";

export function ClausesTab({ clauses }: { clauses: ClauseItem[] }) {
  const [openId, setOpenId] = useState<string | null>(clauses[0]?.id ?? null);

  if (clauses.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">No key clauses were identified in this document.</p>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {clauses.map((clause) => {
        const isOpen = openId === clause.id;
        return (
          <Card key={clause.id} className="overflow-hidden">
            <button
              onClick={() => setOpenId(isOpen ? null : clause.id)}
              className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-paper transition-colors"
            >
              <div>
                <span className="section-label text-brass">{clause.category}</span>
                <h3 className="font-medium text-ink mt-0.5">{clause.title}</h3>
              </div>
              <ChevronDown
                size={18}
                className={clsx("text-ink-faint transition-transform shrink-0 ml-4", isOpen && "rotate-180")}
              />
            </button>
            {isOpen && (
              <div className="px-6 pb-6 pt-1 space-y-4 border-t border-line">
                {clause.original_text && (
                  <div className="pt-4">
                    <div className="section-label mb-1.5">Original Text</div>
                    <p className="text-sm text-ink-soft italic border-l-2 border-line pl-3 leading-relaxed">
                      "{clause.original_text}"
                    </p>
                  </div>
                )}
                {clause.plain_explanation && (
                  <div className="rounded-md bg-paper border border-line p-3.5">
                    <div className="section-label mb-1 text-navy">Plain English</div>
                    <p className="text-sm text-ink-soft">{clause.plain_explanation}</p>
                  </div>
                )}
                {clause.page_number && (
                  <p className="font-mono text-xs text-ink-faint">
                    Source: Page {clause.page_number}
                    {clause.section_reference ? ` — ${clause.section_reference}` : ""}
                  </p>
                )}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
