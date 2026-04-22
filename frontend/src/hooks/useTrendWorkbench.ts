import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type {
  AnalysisMode,
  Category,
  IngestionRunRequest,
  InstagramFeedType,
  KeywordSuggestionRequest,
  KeywordSuggestionResponse,
  Market,
  RunStatusResponse,
  SourceName,
} from "../api/types";

const KEYWORD_DRIVEN_SOURCES: SourceName[] = ["google_trends", "tiktok", "instagram"];

function normalizeKeywords(input: string) {
  const seen = new Set<string>();
  return input
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .filter((item) => {
      const key = item.toLocaleLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .slice(0, 20);
}

export function useTrendWorkbench() {
  const queryClient = useQueryClient();
  const [market, setMarket] = useState<Market>("HK");
  const [category, setCategory] = useState<Category>("skincare");
  const [recentDays, setRecentDays] = useState(14);
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("single_market");
  const [sources, setSources] = useState<SourceName[]>(["google_trends", "sales"]);
  const [maxTargetKeywords, setMaxTargetKeywords] = useState(5);
  const [tiktokPhotosPerKeyword, setTiktokPhotosPerKeyword] = useState(5);
  const [instagramFeedType, setInstagramFeedType] = useState<InstagramFeedType>("top");
  const [keywordSuggestions, setKeywordSuggestions] = useState<KeywordSuggestionResponse>();
  const [targetKeywords, setTargetKeywords] = useState<string[]>([]);
  const [approvedKeywordConfigKey, setApprovedKeywordConfigKey] = useState<string | null>(null);
  const [ingestionRunId, setIngestionRunId] = useState<string>();
  const [analysisRunId, setAnalysisRunId] = useState<string>();
  const [combinedFlowPending, setCombinedFlowPending] = useState(false);
  const [workflowPrompt, setWorkflowPrompt] = useState("");
  const [analysisStreamRun, setAnalysisStreamRun] = useState<RunStatusResponse>();
  const [analysisStreamActive, setAnalysisStreamActive] = useState(false);
  const [analysisStartRunId, setAnalysisStartRunId] = useState<string>();
  const [analysisStartError, setAnalysisStartError] = useState<string | null>(null);
  const analysisAbortRef = useRef<AbortController | null>(null);

  const requiresKeywords = useMemo(
    () => sources.some((source) => KEYWORD_DRIVEN_SOURCES.includes(source)),
    [sources],
  );

  const suggestionPayload = useMemo<KeywordSuggestionRequest>(
    () => ({
      market,
      category,
      recent_days: recentDays,
      sources,
      max_target_keywords: maxTargetKeywords,
      tiktok_photo_count_per_keyword: tiktokPhotosPerKeyword,
      instagram_feed_type: instagramFeedType,
    }),
    [category, instagramFeedType, market, maxTargetKeywords, recentDays, sources, tiktokPhotosPerKeyword],
  );

  const keywordConfigKey = useMemo(
    () => JSON.stringify(suggestionPayload),
    [suggestionPayload],
  );

  const keywordsApproved = !requiresKeywords || (approvedKeywordConfigKey === keywordConfigKey && targetKeywords.length > 0);
  const keywordApprovalStale = Boolean(requiresKeywords && approvedKeywordConfigKey && approvedKeywordConfigKey !== keywordConfigKey);

  const ingestionPayload = useMemo<IngestionRunRequest>(
    () => ({
      market,
      category,
      recent_days: recentDays,
      sources,
      max_target_keywords: maxTargetKeywords,
      target_keywords: targetKeywords,
      suggested_keywords: keywordSuggestions?.suggestions.map((item) => item.keyword) ?? targetKeywords,
      tiktok_photo_count_per_keyword: tiktokPhotosPerKeyword,
      instagram_feed_type: instagramFeedType,
    }),
    [
      category,
      instagramFeedType,
      market,
      maxTargetKeywords,
      keywordSuggestions?.suggestions,
      recentDays,
      sources,
      targetKeywords,
      tiktokPhotosPerKeyword,
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
    enabled: Boolean(analysisRunId) && !analysisStreamActive,
    refetchInterval: (query) => {
      if (analysisStreamActive) {
        return false;
      }
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

  const suggestKeywordsMutation = useMutation({
    mutationFn: api.suggestIngestionKeywords,
    onSuccess: (response) => {
      setKeywordSuggestions(response);
      setTargetKeywords(response.suggestions.map((item) => item.keyword));
      setApprovedKeywordConfigKey(null);
    },
  });

  const startAnalysisStream = useCallback(async () => {
    if (analysisStreamActive) {
      return;
    }

    analysisAbortRef.current?.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;
    setAnalysisStartError(null);
    setAnalysisStreamActive(true);
    setAnalysisStreamRun(undefined);

    let streamedRunId: string | undefined;
    try {
      await api.streamAnalysisRun(
        analysisPayload,
        (event) => {
          streamedRunId = event.run.id;
          setAnalysisRunId(event.run.id);
          setAnalysisStreamRun(event.run);
          queryClient.setQueryData(["analysis-run", event.run.id], event.run);
          if (event.type === "run.created") {
            setAnalysisStartRunId(event.run.id);
          }
        },
        controller.signal,
      );
    } catch (error) {
      if ((error as Error).name !== "AbortError") {
        setAnalysisStartError((error as Error).message);
      }
    } finally {
      if (analysisAbortRef.current === controller) {
        analysisAbortRef.current = null;
      }
      setAnalysisStreamActive(false);
      if (streamedRunId) {
        void queryClient.invalidateQueries({ queryKey: ["analysis-run", streamedRunId] });
      }
      void queryClient.invalidateQueries({ queryKey: ["analysis-runs"] });
      void queryClient.invalidateQueries({ queryKey: ["latest-trends", market, category] });
    }
  }, [analysisPayload, analysisStreamActive, category, market, queryClient]);

  useEffect(() => {
    return () => {
      analysisAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!combinedFlowPending) {
      return;
    }
    const status = ingestionQuery.data?.status;
    if (status === "completed") {
      setCombinedFlowPending(false);
      void startAnalysisStream();
    }
    if (status === "failed") {
      setCombinedFlowPending(false);
    }
  }, [combinedFlowPending, ingestionQuery.data?.status, startAnalysisStream]);

  const analysisRun =
    analysisStreamRun && analysisStreamRun.id === analysisRunId ? analysisStreamRun : analysisQuery.data;
  const savedTrendsReport = latestTrendsQuery.data;
  const agentReport = analysisRun?.report;
  const guardrailFlags = useMemo(
    () => analysisRun?.guardrail_flags ?? savedTrendsReport?.guardrail_flags ?? [],
    [analysisRun?.guardrail_flags, savedTrendsReport?.guardrail_flags],
  );

  const refreshLatestTrends = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["latest-trends", market, category] });
  }, [category, market, queryClient]);

  const isBusy =
    suggestKeywordsMutation.isPending ||
    createIngestionMutation.isPending ||
    analysisStreamActive ||
    ingestionQuery.data?.status === "running" ||
    analysisRun?.status === "queued" ||
    analysisRun?.status === "running" ||
    combinedFlowPending;

  const runErrorMessage =
    analysisStartError ??
    (ingestionQuery.data?.status === "failed" ? ingestionQuery.data.error_message : null) ??
    (analysisRun?.status === "failed" ? analysisRun.error_message : null);

  const toggleSource = (source: SourceName) => {
    setSources((current) =>
      current.includes(source) ? current.filter((item) => item !== source) : [...current, source],
    );
  };

  const keywordText = useMemo(() => targetKeywords.join("\n"), [targetKeywords]);

  const setTargetKeywordText = (value: string) => {
    setTargetKeywords(normalizeKeywords(value));
    setApprovedKeywordConfigKey(null);
  };

  return {
    filters: {
      market,
      category,
      recentDays,
      analysisMode,
      sources,
      maxTargetKeywords,
      tiktokPhotosPerKeyword,
      instagramFeedType,
      workflowPrompt,
    },
    keywordState: {
      requiresKeywords,
      keywordSuggestions,
      keywordText,
      targetKeywords,
      keywordsApproved,
      keywordApprovalStale,
      recencySupport: keywordSuggestions?.recency_support ?? [],
      keywordGuardrailFlags: keywordSuggestions?.guardrail_flags ?? [],
    },
    runState: {
      ingestionRunId,
      analysisRunId,
      analysisRun,
      analysisStartRunId,
      /** Report from the active or loaded analysis run (LangGraph tab). */
      agentReport,
      /** Latest completed report persisted for the current market/category (Trend library tab). */
      savedTrendsReport,
      latestTrendsIsError: latestTrendsQuery.isError,
      latestTrendsIsPending: latestTrendsQuery.isPending,
      latestTrendsIsFetching: latestTrendsQuery.isFetching,
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
      suggestKeywordsMutation,
      createIngestionMutation,
    },
    actions: {
      setMarket,
      setCategory,
      setRecentDays,
      setAnalysisMode,
      setSources,
      setMaxTargetKeywords: (value: number) =>
        setMaxTargetKeywords(Math.min(20, Math.max(1, Number.isFinite(value) ? value : 5))),
      setTiktokPhotosPerKeyword: (value: number) =>
        setTiktokPhotosPerKeyword(Math.min(50, Math.max(1, Number.isFinite(value) ? value : 5))),
      setInstagramFeedType,
      requestKeywordSuggestions: () => suggestKeywordsMutation.mutate(suggestionPayload),
      setTargetKeywordText,
      approveTargetKeywords: () => {
        if (!requiresKeywords || targetKeywords.length > 0) {
          setApprovedKeywordConfigKey(keywordConfigKey);
        }
      },
      setWorkflowPrompt,
      toggleSource,
      setIngestionRunId,
      setAnalysisRunId,
      refreshLatestTrends,
      runExtraction: () => {
        if (!keywordsApproved) {
          return;
        }
        createIngestionMutation.mutate(ingestionPayload);
      },
      runAnalysis: () => {
        void startAnalysisStream();
      },
      refreshAndAnalyze: () => {
        if (!keywordsApproved) {
          return;
        }
        setCombinedFlowPending(true);
        createIngestionMutation.mutate(ingestionPayload);
      },
    },
  };
}

export type TrendWorkbench = ReturnType<typeof useTrendWorkbench>;
