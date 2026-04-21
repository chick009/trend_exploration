import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { AnalysisMode, Category, IngestionRunRequest, Market, SourceName } from "../api/types";

export function useTrendWorkbench() {
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

  const ingestionPayload = useMemo<IngestionRunRequest>(
    () => ({
      market,
      category,
      recent_days: recentDays,
      sources,
      max_seed_terms: maxSeedTerms,
      max_notes_per_keyword: maxNotesPerKeyword,
      max_comment_posts_per_keyword: Math.min(maxCommentPostsPerKeyword, maxNotesPerKeyword),
      max_comments_per_post: maxCommentsPerPost,
    }),
    [
      category,
      market,
      maxCommentPostsPerKeyword,
      maxCommentsPerPost,
      maxNotesPerKeyword,
      maxSeedTerms,
      recentDays,
      sources,
    ],
  );

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
  }, [analysisPayload, combinedFlowPending, createAnalysisMutation, ingestionQuery.data?.status]);

  const report = analysisQuery.data?.report ?? latestTrendsQuery.data;
  const guardrailFlags = useMemo(
    () => analysisQuery.data?.guardrail_flags ?? report?.guardrail_flags ?? [],
    [analysisQuery.data?.guardrail_flags, report?.guardrail_flags],
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

  const toggleSource = (source: SourceName) => {
    setSources((current) =>
      current.includes(source) ? current.filter((item) => item !== source) : [...current, source],
    );
  };

  return {
    filters: {
      market,
      category,
      recentDays,
      analysisMode,
      sources,
      maxSeedTerms,
      maxNotesPerKeyword,
      maxCommentPostsPerKeyword,
      maxCommentsPerPost,
      workflowPrompt,
    },
    runState: {
      ingestionRunId,
      analysisRunId,
      report,
      guardrailFlags,
      isBusy,
      runErrorMessage,
    },
    queries: {
      sourceHealthQuery,
      latestTrendsQuery,
      ingestionQuery,
      analysisQuery,
    },
    mutations: {
      createIngestionMutation,
      createAnalysisMutation,
    },
    actions: {
      setMarket,
      setCategory,
      setRecentDays,
      setAnalysisMode,
      setSources,
      setMaxSeedTerms: (value: number) => setMaxSeedTerms(Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5))),
      setMaxNotesPerKeyword: (value: number) => {
        const nextValue = Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5));
        setMaxNotesPerKeyword(nextValue);
        setMaxCommentPostsPerKeyword((current) => Math.min(current, nextValue));
      },
      setMaxCommentPostsPerKeyword: (value: number) =>
        setMaxCommentPostsPerKeyword(Math.min(maxNotesPerKeyword, Math.max(0, Number.isFinite(value) ? value : 2))),
      setMaxCommentsPerPost: (value: number) =>
        setMaxCommentsPerPost(Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5))),
      setWorkflowPrompt,
      toggleSource,
      setIngestionRunId,
      setAnalysisRunId,
      runExtraction: () => createIngestionMutation.mutate(ingestionPayload),
      runAnalysis: () => createAnalysisMutation.mutate(analysisPayload),
      refreshAndAnalyze: () => {
        setCombinedFlowPending(true);
        createIngestionMutation.mutate(ingestionPayload);
      },
    },
  };
}

export type TrendWorkbench = ReturnType<typeof useTrendWorkbench>;
