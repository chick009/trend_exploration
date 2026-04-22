import type { AnalysisMode, Category, Market, SourceName } from "../api/types";

export const markets: Market[] = ["HK", "KR", "TW", "SG", "cross"];
export const categories: Category[] = ["skincare", "haircare", "makeup", "supplements", "all"];
/** Sources available for extraction batches (no sales seed). */
export const extractionSourceOptions: SourceName[] = ["google_trends", "tiktok", "instagram"];

/** Full list including legacy or non-extraction sources (labels, logs). */
export const sourceOptions: SourceName[] = ["google_trends", "sales", "tiktok", "instagram"];
export const analysisModes: AnalysisMode[] = ["single_market", "cross_market"];

export const sourceLabels: Record<SourceName, string> = {
  google_trends: "Google Trends",
  sales: "Sales seed",
  tiktok: "TikTok photos (TikHub)",
  instagram: "Instagram (TikHub)",
};

export const promptPresets = [
  {
    label: "Barrier repair in HK",
    query: "Focus on barrier repair and sensitive skin narratives in HK.",
    market: "HK" as const,
    category: "skincare" as const,
    analysisMode: "single_market" as const,
  },
  {
    label: "Cross-market ingredient breakouts",
    query: "Compare ingredient breakouts across HK, KR, TW, and SG.",
    market: "cross" as const,
    category: "all" as const,
    analysisMode: "cross_market" as const,
  },
  {
    label: "KR makeup breakouts",
    query: "Prioritize makeup narratives and products breaking out in KR.",
    market: "KR" as const,
    category: "makeup" as const,
    analysisMode: "single_market" as const,
  },
  {
    label: "Supplement watch list",
    query: "Look for rising supplements themes that still need confirmation.",
    market: "SG" as const,
    category: "supplements" as const,
    analysisMode: "single_market" as const,
  },
];
