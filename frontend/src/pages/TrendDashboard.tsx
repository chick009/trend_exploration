import { AppShell } from "../components/AppShell";

export function TrendDashboard() {
  return <AppShell />;
}
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { AnalysisMode, Category, Market, SourceName } from "../api/types";
import { FilterSidebar } from "../components/FilterSidebar";
import { GraphWorkflowPanel } from "../components/GraphWorkflowPanel";
import { ReasoningTrace } from "../components/ReasoningTrace";
import { TrendCard } from "../components/TrendCard";

export function TrendDashboard() {
  const [market, setMarket] = useState<Market>("HK");
  const [category, setCategory] = useState<Category>("skincare");
  const [recentDays, setRecentDays] = useState(14);
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("single_market");
  const [sources, setSources] = useState<SourceName[]>(["rednote", "google_trends", "sales"]);
  const [maxSeedTerms, setMaxSeedTerms] = useState(5);
  const [maxNotesPerKeyword, setMaxNotesPerKeyword] = useState(5);
  const [maxCommentPostsPerKeyword, setMaxCommentPostsPerKeyword] = useState(2);
  const [maxCommentsPerPost, setMaxCommentsPerPost] = useState(5);
  const [ingestionRunId, setIngestionRunId] = useState<string>();
  const [analysisRunId, setAnalysisRunId] = useState<string>();
  const [combinedFlowPending, setCombinedFlowPending] = useState(false);
  const [workflowPrompt, setWorkflowPrompt] = useState("");

  const analysisPayload = useMemo(
    () => ({
      market,
      category,
      recency_days: recentDays,
      analysis_mode: analysisMode,
      ...(workflowPrompt.trim() ? { query: workflowPrompt.trim() } : {}),
    }),
    [analysisMode, category, market, recentDays, workflowPrompt],
  );

  const sourceHealthQuery = useQuery({
    queryKey: ["source-health"],
    queryFn: () => api.getSourcesHealth(),
    refetchInterval: 15000,
  });

  const latestTrendsQuery = useQuery({
    queryKey: ["latest-trends", market, category],
    queryFn: () => api.getLatestTrends(market, category),
    retry: false,
  });

  const ingestionQuery = useQuery({
    queryKey: ["ingestion-run", ingestionRunId],
    queryFn: () => api.getIngestionRun(ingestionRunId!),
    enabled: Boolean(ingestionRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    },
  });

  const analysisQuery = useQuery({
    queryKey: ["analysis-run", analysisRunId],
    queryFn: () => api.getAnalysisRun(analysisRunId!),
    enabled: Boolean(analysisRunId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    },
  });

  const createIngestionMutation = useMutation({
    mutationFn: api.createIngestionRun,
    onSuccess: (response) => {
      setIngestionRunId(response.id);
    },
  });

  const createAnalysisMutation = useMutation({
    mutationFn: api.createAnalysisRun,
    onSuccess: (response) => {
      setAnalysisRunId(response.id);
    },
  });

  useEffect(() => {
    if (!combinedFlowPending) {
      return;
    }
    const status = ingestionQuery.data?.status;
    if (status === "completed") {
      setCombinedFlowPending(false);
      createAnalysisMutation.mutate(analysisPayload);
    }
    if (status === "failed") {
      setCombinedFlowPending(false);
    }
  }, [
    analysisMode,
    analysisPayload,
    category,
    combinedFlowPending,
    createAnalysisMutation,
    ingestionQuery.data?.status,
    market,
    recentDays,
    workflowPrompt,
  ]);

  const report = analysisQuery.data?.report ?? latestTrendsQuery.data;
  const guardrailFlags = useMemo(
    () => report?.guardrail_flags ?? [],
    [report?.guardrail_flags],
  );

  const isBusy =
    createIngestionMutation.isPending ||
    createAnalysisMutation.isPending ||
    ingestionQuery.data?.status === "running" ||
    analysisQuery.data?.status === "running" ||
    combinedFlowPending;
  const runErrorMessage =
    (ingestionQuery.data?.status === "failed" ? ingestionQuery.data.error_message : null) ??
    (analysisQuery.data?.status === "failed" ? analysisQuery.data.error_message : null);

  const handleToggleSource = (source: SourceName) => {
    setSources((current) =>
      current.includes(source) ? current.filter((item) => item !== source) : [...current, source],
    );
  };

  return (
    <div className="dashboard-layout">
      <FilterSidebar
        market={market}
        category={category}
        recentDays={recentDays}
        analysisMode={analysisMode}
        sources={sources}
        maxSeedTerms={maxSeedTerms}
        maxNotesPerKeyword={maxNotesPerKeyword}
        maxCommentPostsPerKeyword={maxCommentPostsPerKeyword}
        maxCommentsPerPost={maxCommentsPerPost}
        onMarketChange={setMarket}
        onCategoryChange={setCategory}
        onRecentDaysChange={setRecentDays}
        onAnalysisModeChange={setAnalysisMode}
        onToggleSource={handleToggleSource}
        onMaxSeedTermsChange={(value) => setMaxSeedTerms(Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5)))}
        onMaxNotesPerKeywordChange={(value) => {
          const nextValue = Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5));
          setMaxNotesPerKeyword(nextValue);
          setMaxCommentPostsPerKeyword((current) => Math.min(current, nextValue));
        }}
        onMaxCommentPostsPerKeywordChange={(value) =>
          setMaxCommentPostsPerKeyword(
            Math.min(maxNotesPerKeyword, Math.max(0, Number.isFinite(value) ? value : 2)),
          )
        }
        onMaxCommentsPerPostChange={(value) =>
          setMaxCommentsPerPost(Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5)))
        }
        onExtract={() =>
          createIngestionMutation.mutate({
            market,
            category,
            recent_days: recentDays,
            sources,
            max_seed_terms: maxSeedTerms,
            max_notes_per_keyword: maxNotesPerKeyword,
            max_comment_posts_per_keyword: Math.min(maxCommentPostsPerKeyword, maxNotesPerKeyword),
            max_comments_per_post: maxCommentsPerPost,
          })
        }
        onAnalyze={() => createAnalysisMutation.mutate(analysisPayload)}
        onRefreshAndAnalyze={() => {
          setCombinedFlowPending(true);
          createIngestionMutation.mutate({
            market,
            category,
            recent_days: recentDays,
            sources,
            max_seed_terms: maxSeedTerms,
            max_notes_per_keyword: maxNotesPerKeyword,
            max_comment_posts_per_keyword: Math.min(maxCommentPostsPerKeyword, maxNotesPerKeyword),
            max_comments_per_post: maxCommentsPerPost,
          });
        }}
        isBusy={isBusy}
      />

      <main className="panel content-panel">
        <GraphWorkflowPanel
          market={market}
          analysisMode={analysisMode}
          analysisRun={analysisQuery.data}
          workflowPrompt={workflowPrompt}
          onWorkflowPromptChange={setWorkflowPrompt}
          onRunAnalysis={() => createAnalysisMutation.mutate(analysisPayload)}
          isBusy={isBusy}
        />

        <header className="hero">
          <div>
            <p className="eyebrow">Health & Beauty Trend Discovery</p>
            <h1>Emerging viral trends with transparent evidence</h1>
            <p className="panel-copy">
              Surface high-signal ingredients, brands, and product functions by combining social,
              search, sales, and cross-market evidence.
            </p>
          </div>
          <div className="status-box">
            <span>{isBusy ? "Processing" : "Ready"}</span>
            <small>{analysisQuery.data?.status ?? ingestionQuery.data?.status ?? "idle"}</small>
          </div>
        </header>

        {createIngestionMutation.error || createAnalysisMutation.error ? (
          <div className="banner error-banner">
            {(createIngestionMutation.error as Error | null)?.message ??
              (createAnalysisMutation.error as Error | null)?.message}
          </div>
        ) : null}

        {runErrorMessage ? <div className="banner error-banner">{runErrorMessage}</div> : null}

        {!report ? (
          <div className="empty-state">
            <h2>No trend report yet</h2>
            <p>Run an extraction batch or analysis to populate the dashboard.</p>
          </div>
        ) : (
          <>
            <section>
              <div className="section-header">
                <h2>Confirmed Trends</h2>
                <p className="muted-text">
                  {report.market} · {report.category} · {report.recency_days} days
                </p>
              </div>
              <div className="trend-grid">
                {report.trends.map((trend) => (
                  <TrendCard key={`${trend.term}-${trend.rank}`} trend={trend} />
                ))}
              </div>
            </section>

            <section>
              <div className="section-header">
                <h2>Watch List</h2>
                <p className="muted-text">Lower-confidence items with partial confirmation.</p>
              </div>
              <div className="trend-grid">
                {report.watch_list.length > 0 ? (
                  report.watch_list.map((trend) => (
                    <TrendCard key={`${trend.term}-${trend.rank}-watch`} trend={trend} />
                  ))
                ) : (
                  <div className="empty-inline">No current watch-list trends.</div>
                )}
              </div>
            </section>
          </>
        )}
      </main>

      <ReasoningTrace
        ingestionRun={ingestionQuery.data}
        analysisRun={analysisQuery.data}
        sourceHealth={sourceHealthQuery.data?.sources ?? []}
        guardrailFlags={guardrailFlags}
      />
    </div>
  );
}
