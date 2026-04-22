import type { ReactNode } from "react";

import type { AnalysisMode, Category, InstagramFeedType, Market, SourceName } from "../api/types";
import { analysisModes, categories, markets, extractionSourceOptions, sourceLabels } from "../lib/options";
import { Badge, Button, Card } from "./ui";

type Props = {
  market: Market;
  category: Category;
  recentDays: number;
  analysisMode: AnalysisMode;
  sources: SourceName[];
  maxTargetKeywords: number;
  tiktokPhotosPerKeyword: number;
  instagramFeedType: InstagramFeedType;
  requiresKeywords: boolean;
  keywordsApproved: boolean;
  approvedKeywordCount: number;
  onMarketChange: (value: Market) => void;
  onCategoryChange: (value: Category) => void;
  onRecentDaysChange: (value: number) => void;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  onToggleSource: (source: SourceName) => void;
  onMaxTargetKeywordsChange: (value: number) => void;
  onTiktokPhotosPerKeywordChange: (value: number) => void;
  onInstagramFeedTypeChange: (value: InstagramFeedType) => void;
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
        "rounded-xl border px-2.5 py-1.5 text-xs transition md:text-sm",
        active
          ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white shadow-lg shadow-blue-950/25"
          : "border-white/10 bg-white/3 text-slate-200 hover:bg-slate-800/60 hover:text-slate-100",
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
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">{label}</span>
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
  maxTargetKeywords,
  tiktokPhotosPerKeyword,
  instagramFeedType,
  requiresKeywords,
  keywordsApproved,
  approvedKeywordCount,
  onMarketChange,
  onCategoryChange,
  onRecentDaysChange,
  onAnalysisModeChange,
  onToggleSource,
  onMaxTargetKeywordsChange,
  onTiktokPhotosPerKeywordChange,
  onInstagramFeedTypeChange,
  onExtract,
  onAnalyze,
  onRefreshAndAnalyze,
  isBusy,
}: Props) {
  return (
    <Card className="flex h-full flex-col gap-3.5 lg:sticky lg:top-24">
      <div className="space-y-1.5">
        <Badge tone="accent">Controls</Badge>
        <div className="space-y-0.5">
          <h2 className="text-lg font-semibold text-slate-50">Trend workbench</h2>
          <p className="text-xs leading-relaxed text-slate-400">
            Adjust markets, sources, and cost guardrails before refreshing data or running the LangGraph analysis flow.
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

      {sources.includes("google_trends") ? (
        <section className="space-y-2">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Google Trends recency</div>
          <p className="text-[11px] leading-relaxed text-slate-500">Only Google Trends queries use this day window via SerpAPI.</p>
          <div className="flex flex-wrap gap-2">
            {[7, 14, 30].map((days) => (
              <SegmentButton key={days} active={recentDays === days} onClick={() => onRecentDaysChange(days)}>
                {days}d
              </SegmentButton>
            ))}
          </div>
        </section>
      ) : null}

      <section className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Analysis mode</div>
        <div className="grid gap-1.5">
          {analysisModes.map((option) => (
            <SegmentButton key={option} active={analysisMode === option} onClick={() => onAnalysisModeChange(option)}>
              {option === "single_market" ? "Single market" : "Cross market"}
            </SegmentButton>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Sources</div>
        <div className="space-y-1.5">
          {extractionSourceOptions.map((source) => (
            <label
              key={source}
              className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/3 px-2.5 py-2"
            >
              <div className="space-y-0.5">
                <div className="text-xs font-medium text-slate-100">{sourceLabels[source]}</div>
                <div className="text-[11px] leading-snug text-slate-500">
                  {source === "google_trends"
                    ? "Keyword time range follows the recency control when enabled above."
                    : source === "tiktok"
                      ? "TikHub photo search; stored in SQLite."
                      : "TikHub hashtag posts; stored in SQLite."}
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

      <section className="space-y-2">
        <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Shared limits</div>
        <div className="grid gap-2">
          <NumberField label="Keyword suggestions" value={maxTargetKeywords} min={1} max={20} onChange={onMaxTargetKeywordsChange} />
        </div>
      </section>

      {sources.includes("google_trends") ? (
        <section className="rounded-xl border border-white/8 bg-white/2 px-2.5 py-2 text-[11px] leading-relaxed text-slate-500">
          <span className="font-medium text-slate-400">Google Trends</span> uses the recency window and the approved keyword list from the Data Extraction tab.
        </section>
      ) : null}

      {sources.includes("tiktok") ? (
        <section className="space-y-2">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">TikTok photo search</div>
          <NumberField label="Photos per keyword" value={tiktokPhotosPerKeyword} min={1} max={50} onChange={onTiktokPhotosPerKeywordChange} />
        </section>
      ) : null}

      {sources.includes("instagram") ? (
        <section className="space-y-2">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Instagram hashtag</div>
          <label className="flex flex-col gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Feed ranking</span>
            <select value={instagramFeedType} onChange={(event) => onInstagramFeedTypeChange(event.target.value as InstagramFeedType)}>
              <option value="top">Top posts</option>
              <option value="recent">Recent posts</option>
            </select>
          </label>
        </section>
      ) : null}

      <section className="rounded-xl border border-white/8 bg-white/2 px-2.5 py-2 text-[11px] leading-relaxed text-slate-500">
        <span className="font-medium text-slate-400">Keyword approval</span>{" "}
        {requiresKeywords
          ? keywordsApproved
            ? `${approvedKeywordCount} keywords approved for the current extraction settings.`
            : "Generate and approve keywords in the Data Extraction tab before running extraction."
          : "Current sources do not require target keywords."}
      </section>

      <div className="mt-auto grid gap-2 pt-1">
        <Button variant="primary" size="md" onClick={onExtract} disabled={isBusy || (requiresKeywords && !keywordsApproved)} className="w-full">
          Extract batch
        </Button>
        <Button variant="secondary" size="md" onClick={onAnalyze} disabled={isBusy} className="w-full">
          Run analysis
        </Button>
        <Button
          variant="secondary"
          size="md"
          onClick={onRefreshAndAnalyze}
          disabled={isBusy || (requiresKeywords && !keywordsApproved)}
          className="w-full"
        >
          Refresh and analyze
        </Button>
      </div>
    </Card>
  );
}
