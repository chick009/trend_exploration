import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { FilterSidebar } from "../../components/FilterSidebar";
import { GraphWorkflowPanel } from "../../components/GraphWorkflowPanel";
import { ReasoningTrace } from "../../components/ReasoningTrace";
import { TrendCard } from "../../components/TrendCard";
import { Badge, Card } from "../../components/ui";

type Props = {
  workbench: TrendWorkbench;
};

export function TrendsTab({ workbench }: Props) {
  const { filters, runState, queries, mutations, actions } = workbench;
  const { report, guardrailFlags, isBusy, runErrorMessage } = runState;
  const sourceHealth = queries.sourceHealthQuery.data?.sources ?? [];
  const mutationError =
    (mutations.createIngestionMutation.error as Error | null)?.message ??
    (mutations.createAnalysisMutation.error as Error | null)?.message;

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_340px]">
      <FilterSidebar
        market={filters.market}
        category={filters.category}
        recentDays={filters.recentDays}
        analysisMode={filters.analysisMode}
        sources={filters.sources}
        maxSeedTerms={filters.maxSeedTerms}
        maxNotesPerKeyword={filters.maxNotesPerKeyword}
        maxCommentPostsPerKeyword={filters.maxCommentPostsPerKeyword}
        maxCommentsPerPost={filters.maxCommentsPerPost}
        onMarketChange={actions.setMarket}
        onCategoryChange={actions.setCategory}
        onRecentDaysChange={actions.setRecentDays}
        onAnalysisModeChange={actions.setAnalysisMode}
        onToggleSource={actions.toggleSource}
        onMaxSeedTermsChange={actions.setMaxSeedTerms}
        onMaxNotesPerKeywordChange={actions.setMaxNotesPerKeyword}
        onMaxCommentPostsPerKeywordChange={actions.setMaxCommentPostsPerKeyword}
        onMaxCommentsPerPostChange={actions.setMaxCommentsPerPost}
        onExtract={actions.runExtraction}
        onAnalyze={actions.runAnalysis}
        onRefreshAndAnalyze={actions.refreshAndAnalyze}
        isBusy={isBusy}
      />

      <div className="grid gap-6">
        <GraphWorkflowPanel
          market={filters.market}
          analysisMode={filters.analysisMode}
          analysisRun={queries.analysisQuery.data}
          workflowPrompt={filters.workflowPrompt}
          onWorkflowPromptChange={actions.setWorkflowPrompt}
          onRunAnalysis={actions.runAnalysis}
          isBusy={isBusy}
        />

        {mutationError ? <div className="banner error-banner">{mutationError}</div> : null}
        {runErrorMessage ? <div className="banner error-banner">{runErrorMessage}</div> : null}

        {!report ? (
          <Card className="flex min-h-[280px] items-center justify-center">
            <div className="max-w-md text-center">
              <Badge tone="neutral">Awaiting report</Badge>
              <h2 className="mt-4 text-2xl font-semibold text-slate-50">No trend report yet</h2>
              <p className="mt-3 text-sm leading-7 text-slate-400">
                Run an extraction batch or analysis to populate the trend board with confirmed items and watch-list candidates.
              </p>
            </div>
          </Card>
        ) : (
          <>
            <section className="space-y-4">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="eyebrow">Confirmed trends</div>
                  <h2 className="mt-1 text-2xl font-semibold text-slate-50">Transparent evidence, ranked by virality</h2>
                </div>
                <div className="text-sm text-slate-400">
                  {report.market} · {report.category} · {report.recency_days} days
                </div>
              </div>
              <div className="grid gap-4">
                {report.trends.map((trend) => (
                  <TrendCard key={`${trend.term}-${trend.rank}`} trend={trend} />
                ))}
              </div>
            </section>

            <section className="space-y-4">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <div className="eyebrow">Watch list</div>
                  <h2 className="mt-1 text-2xl font-semibold text-slate-50">Lower-confidence items worth monitoring</h2>
                </div>
                <div className="text-sm text-slate-400">Partial confirmation across sources or markets.</div>
              </div>
              <div className="grid gap-4">
                {report.watch_list.length > 0 ? (
                  report.watch_list.map((trend) => <TrendCard key={`${trend.term}-${trend.rank}-watch`} trend={trend} />)
                ) : (
                  <div className="empty-inline text-sm text-slate-400">No current watch-list trends.</div>
                )}
              </div>
            </section>
          </>
        )}
      </div>

      <ReasoningTrace
        ingestionRun={queries.ingestionQuery.data}
        analysisRun={queries.analysisQuery.data}
        sourceHealth={sourceHealth}
        guardrailFlags={guardrailFlags}
      />
    </div>
  );
}
