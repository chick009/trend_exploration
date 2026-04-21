export type Market = "HK" | "KR" | "TW" | "SG" | "cross";
export type Category = "skincare" | "haircare" | "makeup" | "supplements" | "all";
export type SourceName = "rednote" | "google_trends" | "sales" | "tiktok" | "instagram";
export type AnalysisMode = "single_market" | "cross_market";

export type IngestionRunRequest = {
  market: Market;
  category: Category;
  recent_days?: number;
  from_timestamp?: string;
  to_timestamp?: string;
  sources: SourceName[];
  seed_terms?: string[];
  max_seed_terms?: number;
  max_notes_per_keyword?: number;
  max_comment_posts_per_keyword?: number;
  max_comments_per_post?: number;
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

export type RunStatusResponse = {
  id: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  stats: Record<string, unknown>;
  execution_trace: string[];
  guardrail_flags: string[];
  source_batch_id?: string;
  report?: TrendReport;
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
