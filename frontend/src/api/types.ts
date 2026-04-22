export type Market = "HK" | "KR" | "TW" | "SG" | "cross";
export type Category = "skincare" | "haircare" | "makeup" | "supplements" | "all";
export type SourceName = "google_trends" | "sales" | "tiktok" | "instagram";
export type AnalysisMode = "single_market" | "cross_market";
export type InstagramFeedType = "top" | "recent";
export type RecencySupportStatus = "supported" | "partial" | "unsupported";

export type SourceRecencySupport = {
  source: SourceName;
  status: RecencySupportStatus;
  detail: string;
};

export type SuggestedKeyword = {
  keyword: string;
  rationale?: string | null;
};

export type KeywordSuggestionRequest = {
  market: Market;
  category: Category;
  recent_days?: number;
  from_timestamp?: string;
  to_timestamp?: string;
  sources: SourceName[];
  max_target_keywords?: number;
  tiktok_photo_count_per_keyword?: number | null;
  instagram_feed_type?: InstagramFeedType;
};

export type KeywordSuggestionResponse = {
  market: Market;
  category: Category;
  recent_days?: number | null;
  max_target_keywords: number;
  sources: SourceName[];
  suggestions: SuggestedKeyword[];
  guardrail_flags: string[];
  recency_support: SourceRecencySupport[];
};

export type IngestionRunRequest = {
  market: Market;
  category: Category;
  recent_days?: number;
  from_timestamp?: string;
  to_timestamp?: string;
  sources: SourceName[];
  target_keywords?: string[];
  suggested_keywords?: string[];
  max_target_keywords?: number;
  seed_terms?: string[];
  max_seed_terms?: number;
  /** TikTok photo search page size per approved keyword. */
  tiktok_photo_count_per_keyword?: number | null;
  instagram_feed_type?: InstagramFeedType;
};

export type AnalysisRunRequest = {
  market: Market;
  category: Category;
  recency_days: number;
  analysis_mode: AnalysisMode;
  /** Logged in LangGraph intent_parser and returned in execution_trace. */
  query?: string;
};

export type TrendEvidence = {
  social?: string;
  search?: string;
  sales?: string;
  cross_market?: string;
};

export type TrendCard = {
  rank: number;
  term: string;
  entity_type: string;
  virality_score: number;
  confidence_tier: string;
  headline: string;
  why_viral: string;
  evidence: TrendEvidence;
  signal_chips: string[];
  trend_stage: string;
  watch_flag: boolean;
  positivity_score?: number;
};

export type TrendReport = {
  report_id: string;
  generated_at: string;
  market: string;
  category: string;
  recency_days: number;
  trends: TrendCard[];
  watch_list: TrendCard[];
  regional_divergences: Array<Record<string, unknown>>;
  execution_trace: string[];
  guardrail_flags: string[];
};

export type ToolInvocationKind = "sql" | "llm" | "memory";
export type ToolInvocationStatus = "running" | "success" | "error";

export type ToolInvocation = {
  id: string;
  node: string;
  tool: string;
  tool_kind: ToolInvocationKind;
  title: string;
  status: ToolInvocationStatus;
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
  input_summary?: string | null;
  sql?: string | null;
  output_summary?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown>;
};

export type RunStatusResponse = {
  id: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  stats: Record<string, unknown>;
  execution_trace: string[];
  tool_invocations: ToolInvocation[];
  guardrail_flags: string[];
  target_keywords: string[];
  suggested_keywords: string[];
  recency_support: SourceRecencySupport[];
  source_batch_id?: string;
  report?: TrendReport;
};

export type AnalysisRunStreamEvent = {
  type: "run.created" | "run.updated" | "run.completed" | "run.failed";
  run: RunStatusResponse;
};

export type PaginatedRunsResponse = {
  items: RunStatusResponse[];
  total: number;
  limit: number;
  offset: number;
};

export type SourceHealth = {
  source: string;
  latest_batch_id: string | null;
  latest_completed_at: string | null;
  row_count: number;
};

export type SourcesHealthResponse = {
  sources: SourceHealth[];
};

export type DbTableInfo = {
  name: string;
  description: string;
  row_count: number;
  last_updated?: string | null;
};

export type DbTablesResponse = {
  tables: DbTableInfo[];
};

export type DbColumn = {
  name: string;
  data_type: string;
  nullable: boolean;
  is_primary_key: boolean;
  is_indexed: boolean;
};

export type DbTableSchemaResponse = {
  table: string;
  columns: DbColumn[];
};

export type DbRowsQuery = {
  limit?: number;
  offset?: number;
  search?: string;
  column?: string;
  order_by?: string;
  order_dir?: "asc" | "desc";
};

export type DbRowsResponse = {
  table: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  total: number;
  limit: number;
  offset: number;
};
