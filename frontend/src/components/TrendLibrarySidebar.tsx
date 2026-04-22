import type { ReactNode } from "react";

import type { Category, Market, RunStatusResponse } from "../api/types";
import { categories, markets } from "../lib/options";
import { formatDateTime } from "../lib/utils";
import { cn } from "../lib/utils";
import { Badge, Button, Card, StatusPill } from "./ui";

type Props = {
  market: Market;
  category: Category;
  onMarketChange: (value: Market) => void;
  onCategoryChange: (value: Category) => void;
  onRefreshLatest: () => void;
  latestFetching: boolean;
  displayMeta: { report_id: string; generated_at: string; market: string; category: string; recency_days: number } | null;
  viewSource: "latest" | "history";
  selectedRunId: string | null;
  onClearHistorySelection: () => void;
  matchingRuns: RunStatusResponse[];
  recentRunsLoading: boolean;
  onPickRun: (id: string) => void;
};

function SegmentButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded-xl border px-2.5 py-1.5 text-xs transition md:text-sm",
        active
          ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white shadow-lg shadow-blue-950/25"
          : "border-white/10 bg-white/3 text-slate-300 hover:bg-white/6",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export function TrendLibrarySidebar({
  market,
  category,
  onMarketChange,
  onCategoryChange,
  onRefreshLatest,
  latestFetching,
  displayMeta,
  viewSource,
  selectedRunId,
  onClearHistorySelection,
  matchingRuns,
  recentRunsLoading,
  onPickRun,
}: Props) {
  return (
    <Card className="flex h-full flex-col gap-3.5 lg:sticky lg:top-24">
      <div className="space-y-1.5">
        <Badge tone="accent">Trend library</Badge>
        <div className="space-y-0.5">
          <h2 className="text-lg font-semibold text-slate-50">Saved reports</h2>
          <p className="text-xs leading-relaxed text-slate-400">
            Browse trends already stored for each market and category. Pull fresh signals in Data Extraction, then generate a new report in the LangGraph Agent tab.
          </p>
        </div>
      </div>

      <section className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Market</div>
        <div className="flex flex-wrap gap-1.5">
          {markets.map((option) => (
            <SegmentButton key={option} active={market === option} onClick={() => onMarketChange(option)}>
              {option}
            </SegmentButton>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Category</div>
        <select value={category} onChange={(event) => onCategoryChange(event.target.value as Category)}>
          {categories.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </section>

      <div className="grid gap-2">
        <Button variant="secondary" size="md" className="w-full" onClick={onRefreshLatest} disabled={latestFetching}>
          {latestFetching ? "Refreshing…" : "Refresh from database"}
        </Button>
        {displayMeta ? (
          <div className="rounded-2xl border border-white/10 bg-white/3 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
            <div className="font-medium text-slate-300">Report {displayMeta.report_id}</div>
            <div className="mt-1">Generated {formatDateTime(displayMeta.generated_at)}</div>
            <div className="mt-0.5">
              {displayMeta.market} · {displayMeta.category} · {displayMeta.recency_days}d recency
            </div>
            {viewSource === "history" ? (
              <Button variant="ghost" size="sm" className="mt-2 h-8 w-full justify-center px-2 text-blue-200" onClick={onClearHistorySelection}>
                Back to latest saved
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="grid gap-2">
        <a
          href="#extraction"
          className={cn(
            "inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-2xl border border-white/10 bg-slate-800/75 px-4 text-sm font-medium text-slate-100 transition duration-150 hover:border-white/20 hover:bg-slate-700/80",
          )}
        >
          Go to data extraction
        </a>
        <a
          href="#agent"
          className={cn(
            "inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-2xl border border-transparent bg-gradient-to-r from-blue-600 to-violet-500 px-4 text-sm font-medium text-white shadow-lg shadow-blue-950/30 transition duration-150 hover:from-blue-500 hover:to-violet-400",
          )}
        >
          Generate with agent
        </a>
      </div>

      <div className="space-y-2 rounded-xl border border-white/10 bg-slate-950/35 p-3">
        <div className="text-sm font-semibold text-slate-100">Recent reports</div>
        <p className="text-[11px] leading-relaxed text-slate-500">
          Completed runs whose report matches this market and category. Pick one to inspect an older snapshot.
        </p>
        <div className="max-h-[280px] space-y-2 overflow-y-auto">
          {recentRunsLoading ? (
            <div className="text-xs text-slate-500">Loading…</div>
          ) : matchingRuns.length === 0 ? (
            <div className="text-xs leading-relaxed text-slate-500">No completed runs in the recent list for this slice.</div>
          ) : (
            matchingRuns.map((row) => (
              <button
                key={row.id}
                type="button"
                onClick={() => onPickRun(row.id)}
                className={[
                  "w-full rounded-2xl border px-3 py-2.5 text-left text-xs transition",
                  selectedRunId === row.id
                    ? "border-blue-400/50 bg-blue-950/30"
                    : "border-white/10 bg-white/3 hover:bg-white/6",
                ].join(" ")}
              >
                <div className="flex items-center justify-between gap-2">
                  <StatusPill status={row.status} />
                  <span className="text-[10px] text-slate-500">{formatDateTime(row.started_at)}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] text-slate-500">{row.id.slice(0, 8)}…</div>
              </button>
            ))
          )}
        </div>
      </div>
    </Card>
  );
}
