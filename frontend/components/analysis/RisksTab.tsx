import { AlertOctagon, AlertTriangle, Info } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { Badge, riskVariant } from "@/components/ui/Badge";
import type { RiskItem } from "@/types";

const LEVEL_ICON = { High: AlertOctagon, Medium: AlertTriangle, Low: Info };
const LEVEL_ORDER = { High: 0, Medium: 1, Low: 2 };

export function RisksTab({ risks }: { risks: RiskItem[] }) {
  if (risks.length === 0) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-ink-faint">
          No specific risks were flagged in this document. This does not guarantee the
          document is risk-free — consider a professional review for important decisions.
        </p>
      </Card>
    );
  }

  const sorted = [...risks].sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);

  return (
    <div className="space-y-4">
      {sorted.map((risk) => {
        const Icon = LEVEL_ICON[risk.level];
        return (
          <Card key={risk.id} className="p-6">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2.5">
                <Icon size={17} className={riskIconColor(risk.level)} />
                <h3 className="font-medium text-ink">{risk.title}</h3>
              </div>
              <Badge variant={riskVariant(risk.level)}>{risk.level} Risk</Badge>
            </div>
            <p className="text-sm text-ink-soft leading-relaxed mb-3">{risk.description}</p>
            <div className="rounded-md bg-paper border border-line p-3.5 mb-3">
              <div className="section-label mb-1 text-navy">Why it matters</div>
              <p className="text-sm text-ink-soft">{risk.why_it_matters}</p>
            </div>
            {risk.plain_explanation && (
              <p className="text-sm text-ink-faint italic mb-3">{risk.plain_explanation}</p>
            )}
            {risk.page_number && (
              <p className="font-mono text-xs text-ink-faint">
                Source: Page {risk.page_number}
                {risk.section_reference ? ` — ${risk.section_reference}` : ""}
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

function riskIconColor(level: string) {
  if (level === "High") return "text-risk-high";
  if (level === "Medium") return "text-risk-medium";
  return "text-risk-low";
}
