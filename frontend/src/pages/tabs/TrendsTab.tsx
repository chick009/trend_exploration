import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { TrendCard as TrendCardModel } from "../../api/types";
import { ReasoningTrace } from "../../components/ReasoningTrace";
import { TrendCard } from "../../components/TrendCard";
import { TrendReportTables } from "../../components/TrendReportTables";
import { TrendLibrarySidebar } from "../../components/TrendLibrarySidebar";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";

type Props = {
  workbench: TrendWorkbench;
};

type SectionFilter = "all" | "confirmed" | "watch";
type SortKey = "virality" | "rank" | "term";

function sortTrends(list: TrendCardModel[], sortKey: SortKey): TrendCardModel[] {
  const next = [...list];
  if (sortKey === "rank") {
    next.sort((a, b) => a.rank - b.rank);
  } else if (sortKey === "term") {
    next.sort((a, b) => a.term.localeCompare(b.term));
  } else {
    next.sort((a, b) => b.virality_score - a.virality_score);
  }
  return next;
}

function filterTrends(
  trends: TrendCardModel[],
  watchList: TrendCardModel[],
  section: SectionFilter,
  search: string,
  tier: string | null,
  sortKey: SortKey,
): { confirmed: TrendCardModel[]; watch: TrendCardModel[] } {
  const q = search.trim().toLowerCase();
  const matches = (t: TrendCardModel) => {
    if (tier && t.confidence_tier !== tier) {
      return false;
    }
    if (!q) {
      return true;
    }
    return (
      t.term.toLowerCase().includes(q) ||
      t.headline.toLowerCase().includes(q) ||
      t.why_viral.toLowerCase().includes(q) ||
      (t.viral_reasons ?? []).some((reason) => reason.toLowerCase().includes(q))
    );
  };

  let confirmed = trends.filter(matches);
  let watch = watchList.filter(matches);
  if (section === "confirmed") {
    watch = [];
  }
  if (section === "watch") {
    confirmed = [];
  }
  return { confirmed: sortTrends(confirmed, sortKey), watch: sortTrends(watch, sortKey) };
}

export function TrendsTab({ workbench }: Props) {
  const { filters, runState, queries, actions } = workbench;
  const { analysisRun, guardrailFlags } = runState;
  const sourceHealth = queries.sourceHealthQuery.data?.sources ?? [];

  const [trendsHistoryRunId, setTrendsHistoryRunId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState<SectionFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("virality");
  const [tierFilter, setTierFilter] = useState<string | null>(null);

  useEffect(() => {
    setTrendsHistoryRunId(null);
  }, [filters.market, filters.category]);

  const recentRunsQuery = useQuery({
    queryKey: ["analysis-runs", "trends-tab", filters.market, filters.category],
    queryFn: () => api.listAnalysisRuns(40, 0),
    refetchInterval: 8000,
  });

  const historyRunQuery = useQuery({
    queryKey: ["analysis-run", trendsHistoryRunId],
    queryFn: () => api.getAnalysisRun(trendsHistoryRunId!),
    enabled: Boolean(trendsHistoryRunId),
  });

  const savedReport = runState.savedTrendsReport;
  const displayReport = trendsHistoryRunId ? historyRunQuery.data?.report : savedReport;
  const viewSource: "latest" | "history" = trendsHistoryRunId ? "history" : "latest";

  const matchingRuns = useMemo(() => {
    const items = recentRunsQuery.data?.items ?? [];
    return items.filter(
      (row) =>
        row.status === "completed" &&
        row.report &&
        row.report.market === filters.market &&
        row.report.category === filters.category,
    );
  }, [recentRunsQuery.data?.items, filters.market, filters.category]);

  const { confirmed: shownTrends, watch: shownWatch } = useMemo(
    () =>
      displayReport
        ? filterTrends(displayReport.trends, displayReport.watch_list, sectionFilter, search, tierFilter, sortKey)
        : { confirmed: [], watch: [] },
    [displayReport, sectionFilter, search, tierFilter, sortKey],
  );

  const uniqueTiers = useMemo(() => {
    if (!displayReport) {
      return [];
    }
    const tiers = new Set<string>();
    displayReport.trends.forEach((t) => tiers.add(t.confidence_tier));
    displayReport.watch_list.forEach((t) => tiers.add(t.confidence_tier));
    return [...tiers].sort();
  }, [displayReport]);

  const displayMeta = displayReport
    ? {
        report_id: displayReport.report_id,
        generated_at: displayReport.generated_at,
        market: displayReport.market,
        category: displayReport.category,
        recency_days: displayReport.recency_days,
      }
    : null;

  const sliceMismatch =
    Boolean(displayReport) &&
    Boolean(trendsHistoryRunId) &&
    (displayReport!.market !== filters.market || displayReport!.category !== filters.category);

  const libraryLoading =
    Boolean(trendsHistoryRunId) && historyRunQuery.isPending && !historyRunQuery.data?.report;
  const latestMissing =
    !trendsHistoryRunId && runState.latestTrendsIsError && !runState.latestTrendsIsPending && !savedReport;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(260px,280px)_minmax(0,1fr)]">
      <TrendLibrarySidebar
        market={filters.market}
        category={filters.category}
        onMarketChange={actions.setMarket}
        onCategoryChange={actions.setCategory}
        onRefreshLatest={actions.refreshLatestTrends}
        latestFetching={runState.latestTrendsIsFetching}
        displayMeta={displayMeta}
        viewSource={viewSource}
        selectedRunId={trendsHistoryRunId}
        onClearHistorySelection={() => setTrendsHistoryRunId(null)}
        matchingRuns={matchingRuns}
        recentRunsLoading={recentRunsQuery.isLoading}
        onPickRun={(id) => setTrendsHistoryRunId(id)}
      />

      <div className="grid gap-4">
        {trendsHistoryRunId && historyRunQuery.isError ? (
          <div className="banner error-banner text-sm">Could not load this analysis run.</div>
        ) : null}

        {sliceMismatch ? (
          <div className="banner border-amber-400/30 bg-amber-950/25 text-sm text-amber-100/90">
            This saved run’s report is for {displayReport!.market} / {displayReport!.category}. Switch the sidebar to match, or choose another run.
          </div>
        ) : null}

        {libraryLoading ? (
          <Card className="flex min-h-[180px] items-center justify-center">
            <div className="text-sm text-slate-400">Loading report…</div>
          </Card>
        ) : null}

        {!libraryLoading && displayReport ? (
          <>
            <div className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/3 p-4 lg:flex-row lg:flex-wrap lg:items-end">
              <label className="grid min-w-[200px] flex-1 gap-1.5">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Search</span>
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Trend, signal term, or why viral…"
                  className="w-full"
                />
              </label>
              <label className="grid min-w-[140px] gap-1.5">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Sort</span>
                <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
                  <option value="virality">Virality (high → low)</option>
                  <option value="rank">Rank</option>
                  <option value="term">Signal term A–Z</option>
                </select>
              </label>
              <label className="grid min-w-[160px] gap-1.5">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Show</span>
                <select value={sectionFilter} onChange={(e) => setSectionFilter(e.target.value as SectionFilter)}>
                  <option value="all">Confirmed and watch list</option>
                  <option value="confirmed">Confirmed only</option>
                  <option value="watch">Watch list only</option>
                </select>
              </label>
              {uniqueTiers.length > 0 ? (
                <label className="grid min-w-[160px] gap-1.5">
                  <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Confidence</span>
                  <select value={tierFilter ?? ""} onChange={(e) => setTierFilter(e.target.value || null)}>
                    <option value="">All tiers</option>
                    {uniqueTiers.map((tier) => (
                      <option key={tier} value={tier}>
                        {tier}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>

            {shownTrends.length > 0 || shownWatch.length > 0 || (displayReport.regional_divergences?.length ?? 0) > 0 ? (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Data tables</CardTitle>
                  <CardDescription>Same report as the cards—compact rows you can scan and copy.</CardDescription>
                </CardHeader>
                <CardContent>
                  <TrendReportTables
                    confirmed={shownTrends}
                    watch={shownWatch}
                    regionalDivergences={displayReport.regional_divergences ?? []}
                  />
                </CardContent>
              </Card>
            ) : null}

            {sectionFilter !== "watch" ? (
              <section className="space-y-3">
                <div className="flex flex-col gap-1 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="eyebrow">Confirmed trends</div>
                    <h2 className="mt-0.5 text-lg font-semibold text-slate-50">Transparent evidence, ranked by virality</h2>
                  </div>
                  <div className="text-xs text-slate-400">
                    {displayReport.market} · {displayReport.category} · {displayReport.recency_days} days
                  </div>
                </div>
                <div className="grid gap-3">
                  {shownTrends.length > 0 ? (
                    shownTrends.map((trend) => <TrendCard key={`${trend.term}-${trend.rank}`} trend={trend} />)
                  ) : (
                    <div className="empty-inline text-sm text-slate-400">No trends match your filters.</div>
                  )}
                </div>
              </section>
            ) : null}

            {sectionFilter !== "confirmed" ? (
              <section className="space-y-3">
                <div className="flex flex-col gap-1 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <div className="eyebrow">Watch list</div>
                    <h2 className="mt-0.5 text-lg font-semibold text-slate-50">Lower-confidence items worth monitoring</h2>
                  </div>
                  <div className="text-xs text-slate-400">Partial confirmation across sources or markets.</div>
                </div>
                <div className="grid gap-3">
                  {shownWatch.length > 0 ? (
                    shownWatch.map((trend) => <TrendCard key={`${trend.term}-${trend.rank}-watch`} trend={trend} />)
                  ) : (
                    <div className="empty-inline text-sm text-slate-400">No watch-list items match your filters.</div>
                  )}
                </div>
              </section>
            ) : null}
          </>
        ) : null}

        {!libraryLoading && !displayReport && latestMissing ? (
          <Card className="flex min-h-[220px] items-center justify-center">
            <div className="max-w-md text-center">
              <Badge tone="neutral">No saved report</Badge>
              <h2 className="mt-3 text-lg font-semibold text-slate-50">Nothing in the library for this slice yet</h2>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">
                Run data extraction, then use the LangGraph Agent tab to generate a report. When it completes, it is stored automatically and will appear here.
              </p>
              <p className="mt-3 text-xs">
                <a href="#extraction" className="text-blue-200 underline-offset-2 hover:underline">
                  Data extraction
                </a>
                <span className="text-slate-500"> · </span>
                <a href="#agent" className="text-blue-200 underline-offset-2 hover:underline">
                  LangGraph agent
                </a>
              </p>
            </div>
          </Card>
        ) : null}

        {!libraryLoading && !displayReport && !latestMissing && runState.latestTrendsIsPending ? (
          <Card className="flex min-h-[180px] items-center justify-center">
            <div className="text-sm text-slate-400">Loading latest report…</div>
          </Card>
        ) : null}

        {!libraryLoading && !displayReport && trendsHistoryRunId && !historyRunQuery.isPending && !historyRunQuery.data?.report ? (
          <Card className="flex min-h-[160px] items-center justify-center">
            <div className="max-w-md text-center text-sm text-slate-400">This run does not include a completed report yet.</div>
          </Card>
        ) : null}

        <details className="rounded-2xl border border-white/10 bg-slate-950/25">
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-200">
            Pipeline context (advanced)
          </summary>
          <div className="border-t border-white/10 px-2 pb-4 pt-2">
            <ReasoningTrace
              ingestionRun={queries.ingestionQuery.data}
              analysisRun={analysisRun}
              sourceHealth={sourceHealth}
              guardrailFlags={guardrailFlags}
            />
          </div>
        </details>
      </div>
    </div>
  );
}
