import { useState } from "react";

import type { TrendCard as TrendCardType } from "../api/types";
import { Badge, Button, Card } from "./ui";

type Props = {
  trend: TrendCardType;
};

export function TrendCard({ trend }: Props) {
  const [expanded, setExpanded] = useState(false);
  const viralityScore = Math.max(0, Math.min(100, Math.round(trend.virality_score * 100)));

  return (
    <Card className="space-y-4 rounded-[26px] bg-slate-950/45">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="info">#{trend.rank}</Badge>
            <Badge tone={trend.watch_flag ? "warning" : "success"}>{trend.confidence_tier}</Badge>
            <Badge tone="neutral">{trend.entity_type}</Badge>
            <Badge tone="accent">{trend.trend_stage}</Badge>
          </div>
          <div className="space-y-1">
            <h3 className="text-xl font-semibold text-slate-50">{trend.term}</h3>
            <p className="text-sm leading-6 text-slate-400">{trend.headline}</p>
          </div>
        </div>

        <div className="min-w-[120px] rounded-3xl border border-white/10 bg-white/3 px-4 py-3 text-right">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Virality</div>
          <div className="text-3xl font-semibold text-slate-50">{viralityScore}</div>
          {typeof trend.positivity_score === "number" ? (
            <div className="text-xs text-slate-400">Positivity {Math.round(trend.positivity_score * 100)}</div>
          ) : null}
        </div>
      </div>

      <div className="space-y-2">
        <div className="h-2.5 overflow-hidden rounded-full bg-white/8">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-sky-400 to-violet-400"
            style={{ width: `${viralityScore}%` }}
          />
        </div>
        <p className="text-sm leading-6 text-slate-300">{trend.why_viral}</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {trend.signal_chips.map((chip) => (
          <Badge key={chip} tone="info" className="normal-case tracking-normal text-[12px]">
            {chip}
          </Badge>
        ))}
      </div>

      <Button
        variant="ghost"
        size="sm"
        className="justify-start px-0 text-blue-200 hover:bg-transparent"
        onClick={() => setExpanded((current) => !current)}
      >
        {expanded ? "Hide reasoning" : "Why is this viral?"}
      </Button>

      {expanded ? (
        <div className="space-y-3 border-t border-white/10 pt-4">
          <div className="text-sm font-medium text-slate-200">Evidence summary</div>
          <ul className="space-y-2 text-sm leading-6 text-slate-300">
            {Object.entries(trend.evidence)
              .filter(([, value]) => Boolean(value))
              .map(([label, value]) => (
                <li key={label} className="rounded-2xl border border-white/8 bg-white/3 px-4 py-3">
                  <strong className="mr-2 text-slate-100">{label}:</strong>
                  <span>{value}</span>
                </li>
              ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}
