import { Users, CalendarClock } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import type { SummaryResponse } from "@/types";

export function OverviewTab({ summary }: { summary: SummaryResponse }) {
  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="section-label mb-3">Executive Summary</div>
        <p className="text-ink-soft leading-relaxed">
          {summary.executive_summary || "No summary was generated for this document."}
        </p>
        {summary.plain_english_overview && (
          <p className="text-ink-soft leading-relaxed mt-4 pt-4 border-t border-line">
            {summary.plain_english_overview}
          </p>
        )}
      </Card>

      <div className="grid md:grid-cols-2 gap-6">
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Users size={15} className="text-navy" />
            <div className="section-label">Parties</div>
          </div>
          {summary.entities.length === 0 && (
            <p className="text-sm text-ink-faint">No parties were identified.</p>
          )}
          <div className="space-y-3">
            {summary.entities.map((e) => (
              <div key={e.id} className="flex items-center justify-between text-sm">
                <span className="text-ink font-medium">{e.name}</span>
                {e.role && <span className="text-ink-faint font-mono text-xs">{e.role}</span>}
              </div>
            ))}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <CalendarClock size={15} className="text-navy" />
            <div className="section-label">Important Dates</div>
          </div>
          {summary.important_dates.length === 0 && (
            <p className="text-sm text-ink-faint">No dates were identified.</p>
          )}
          <div className="space-y-3">
            {summary.important_dates.map((d) => (
              <div key={d.id} className="text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-ink font-medium">{d.label}</span>
                  {d.date_value && (
                    <span className="text-brass font-mono text-xs">{d.date_value}</span>
                  )}
                </div>
                {d.description && <p className="text-ink-faint text-xs mt-0.5">{d.description}</p>}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-6">
        <div className="section-label mb-4">Key Obligations</div>
        {summary.obligations.length === 0 && (
          <p className="text-sm text-ink-faint">No obligations were identified.</p>
        )}
        <div className="space-y-5">
          {groupByParty(summary.obligations).map(([party, items]) => (
            <div key={party}>
              <p className="text-sm font-semibold text-ink mb-2">{party}</p>
              <ul className="space-y-1.5">
                {items.map((o) => (
                  <li key={o.id} className="text-sm text-ink-soft flex gap-2">
                    <span className="text-brass mt-1.5 h-1 w-1 rounded-full bg-brass shrink-0" />
                    <span>
                      {o.obligation_text}
                      {o.page_number && (
                        <span className="text-ink-faint font-mono text-xs ml-2">
                          p.{o.page_number}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function groupByParty<T extends { party_name: string }>(items: T[]): [string, T[]][] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const list = map.get(item.party_name) || [];
    list.push(item);
    map.set(item.party_name, list);
  }
  return Array.from(map.entries());
}
