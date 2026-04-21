import type { ReactNode } from "react";

import type { AnalysisMode, Category, Market, SourceName } from "../api/types";
import { analysisModes, categories, markets, sourceLabels, sourceOptions } from "../lib/options";
import { Badge, Button, Card } from "./ui";

type Props = {
  market: Market;
  category: Category;
  recentDays: number;
  analysisMode: AnalysisMode;
  sources: SourceName[];
  maxSeedTerms: number;
  maxNotesPerKeyword: number;
  maxCommentPostsPerKeyword: number;
  maxCommentsPerPost: number;
  onMarketChange: (value: Market) => void;
  onCategoryChange: (value: Category) => void;
  onRecentDaysChange: (value: number) => void;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  onToggleSource: (source: SourceName) => void;
  onMaxSeedTermsChange: (value: number) => void;
  onMaxNotesPerKeywordChange: (value: number) => void;
  onMaxCommentPostsPerKeywordChange: (value: number) => void;
  onMaxCommentsPerPostChange: (value: number) => void;
  onExtract: () => void;
  onAnalyze: () => void;
  onRefreshAndAnalyze: () => void;
  isBusy: boolean;
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
        "rounded-2xl border px-3 py-2 text-sm transition",
        active
          ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white shadow-lg shadow-blue-950/25"
          : "border-white/10 bg-white/3 text-slate-300 hover:bg-white/6",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">{label}</span>
      <input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

export function FilterSidebar({
  market,
  category,
  recentDays,
  analysisMode,
  sources,
  maxSeedTerms,
  maxNotesPerKeyword,
  maxCommentPostsPerKeyword,
  maxCommentsPerPost,
  onMarketChange,
  onCategoryChange,
  onRecentDaysChange,
  onAnalysisModeChange,
  onToggleSource,
  onMaxSeedTermsChange,
  onMaxNotesPerKeywordChange,
  onMaxCommentPostsPerKeywordChange,
  onMaxCommentsPerPostChange,
  onExtract,
  onAnalyze,
  onRefreshAndAnalyze,
  isBusy,
}: Props) {
  return (
    <Card className="flex h-full flex-col gap-5 lg:sticky lg:top-28">
      <div className="space-y-2">
        <Badge tone="accent">Controls</Badge>
        <div className="space-y-1">
          <h2 className="text-xl font-semibold text-slate-50">Trend workbench</h2>
          <p className="text-sm leading-6 text-slate-400">
            Adjust markets, sources, and cost guardrails before refreshing data or running the LangGraph analysis flow.
          </p>
        </div>
      </div>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Market</div>
        <div className="flex flex-wrap gap-2">
          {markets.map((option) => (
            <SegmentButton key={option} active={market === option} onClick={() => onMarketChange(option)}>
              {option}
            </SegmentButton>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Category</div>
        <select value={category} onChange={(event) => onCategoryChange(event.target.value as Category)}>
          {categories.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </section>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Recency window</div>
        <div className="flex flex-wrap gap-2">
          {[7, 14, 30].map((days) => (
            <SegmentButton key={days} active={recentDays === days} onClick={() => onRecentDaysChange(days)}>
              {days}d
            </SegmentButton>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Analysis mode</div>
        <div className="grid gap-2">
          {analysisModes.map((option) => (
            <SegmentButton key={option} active={analysisMode === option} onClick={() => onAnalysisModeChange(option)}>
              {option === "single_market" ? "Single market" : "Cross market"}
            </SegmentButton>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Sources</div>
        <div className="space-y-2">
          {sourceOptions.map((source) => (
            <label key={source} className="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/3 px-3 py-3">
              <div className="space-y-1">
                <div className="text-sm font-medium text-slate-100">{sourceLabels[source]}</div>
                <div className="text-xs text-slate-500">
                  {source === "tiktok" ? "Stored in SQLite from TikHub photo search." : "Included in extraction batches."}
                </div>
              </div>
              <input
                type="checkbox"
                checked={sources.includes(source)}
                onChange={() => onToggleSource(source)}
                className="h-4 w-4 accent-blue-500"
              />
            </label>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Cost guardrails</div>
        <div className="grid gap-3">
          <NumberField label="Seed terms" value={maxSeedTerms} min={1} max={20} onChange={onMaxSeedTermsChange} />
          <NumberField label="Notes per keyword" value={maxNotesPerKeyword} min={1} max={20} onChange={onMaxNotesPerKeywordChange} />
          <NumberField
            label="Comment fetches per keyword"
            value={maxCommentPostsPerKeyword}
            min={0}
            max={10}
            onChange={onMaxCommentPostsPerKeywordChange}
          />
          <NumberField label="Comments per note" value={maxCommentsPerPost} min={1} max={20} onChange={onMaxCommentsPerPostChange} />
        </div>
      </section>

      <div className="mt-auto grid gap-3 pt-2">
        <Button variant="primary" size="lg" onClick={onExtract} disabled={isBusy} className="w-full">
          Extract batch
        </Button>
        <Button variant="secondary" size="lg" onClick={onAnalyze} disabled={isBusy} className="w-full">
          Run analysis
        </Button>
        <Button variant="secondary" size="lg" onClick={onRefreshAndAnalyze} disabled={isBusy} className="w-full">
          Refresh and analyze
        </Button>
      </div>
    </Card>
  );
}
