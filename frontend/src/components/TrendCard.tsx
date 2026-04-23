import { useState } from "react";

import type { TrendCard as TrendCardType } from "../api/types";
import { Badge, Button, Card } from "./ui";

type Props = {
  trend: TrendCardType;
};

export function TrendCard({ trend }: Props) {
  const [expanded, setExpanded] = useState(false);
  const viralityScore = Math.max(0, Math.min(100, Math.round(trend.virality_score * 100)));
  const primaryTrendText = trend.trend_statement?.trim() || trend.headline;
  const viralReasons =
    trend.viral_reasons?.map((reason) => reason.trim()).filter((reason) => reason.length > 0) ?? [];

  return (
    <Card className="space-y-3 rounded-2xl bg-slate-950/45">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="info">#{trend.rank}</Badge>
            <Badge tone={trend.watch_flag ? "warning" : "success"}>{trend.confidence_tier}</Badge>
            <Badge tone="neutral">{trend.entity_type}</Badge>
            <Badge tone="accent">{trend.trend_stage}</Badge>
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-semibold leading-snug text-slate-50">{primaryTrendText}</h3>
            <p className="text-xs leading-relaxed text-slate-400">
              Signal term: <span className="font-medium text-slate-300">{trend.term}</span>
            </p>
          </div>
        </div>

        <div className="min-w-[100px] rounded-xl border border-white/10 bg-white/3 px-3 py-2 text-right">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">Virality</div>
          <div className="text-2xl font-semibold text-slate-50">{viralityScore}</div>
          {typeof trend.positivity_score === "number" ? (
            <div className="text-[11px] text-slate-400">Positivity {Math.round(trend.positivity_score * 100)}</div>
          ) : null}
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="h-2 overflow-hidden rounded-full bg-white/8">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-sky-400 to-violet-400"
            style={{ width: `${viralityScore}%` }}
          />
        </div>
        <p className="text-xs leading-relaxed text-slate-300">{trend.why_viral}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
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
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-200">Why this is viral</div>
            <ul className="space-y-2 text-sm leading-6 text-slate-300">
              {(viralReasons.length > 0 ? viralReasons : [trend.why_viral]).map((reason, index) => (
                <li key={`${reason}-${index}`} className="rounded-2xl border border-white/8 bg-white/3 px-4 py-3">
                  {reason}
                </li>
              ))}
            </ul>
          </div>

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
