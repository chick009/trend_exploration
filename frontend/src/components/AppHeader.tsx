import type { SourceHealth } from "../api/types";
import { formatDateTime, formatNumber } from "../lib/utils";
import { Card, StatusPill } from "./ui";

type Props = {
  sourceHealth: SourceHealth[];
  ingestionStatus?: string;
  analysisStatus?: string;
};

export function AppHeader({ sourceHealth, ingestionStatus, analysisStatus }: Props) {
  const totalRows = sourceHealth.reduce((sum, item) => sum + item.row_count, 0);
  const latestRefresh = sourceHealth
    .map((item) => item.latest_completed_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  const blurb =
    "Health and beauty trend intelligence with extraction visibility, database transparency, and LangGraph demos. " +
    "Read saved trend reports in the Trends tab, manage ingestion in Data Extraction, browse SQLite in SQL Database, and generate fresh reports with a streaming LangGraph agent—all in one workspace.";

  return (
    <Card className="overflow-hidden p-2 md:p-2.5">
      <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <div className="min-w-0 sm:max-w-[55%]">
          <h1 className="truncate text-xs font-semibold tracking-tight text-slate-100 md:text-sm">Trend exploration</h1>
          <p className="truncate text-[10px] leading-snug text-slate-500 md:text-[11px]" title={blurb}>
            Trends · Extraction · SQL · LangGraph
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 sm:shrink-0 sm:justify-end">
          <div className="flex items-center gap-1.5">
            <span className="hidden text-[10px] uppercase tracking-wide text-slate-500 sm:inline">Pipeline</span>
            <StatusPill status={ingestionStatus ?? "idle"} />
            <StatusPill status={analysisStatus ?? "idle"} />
          </div>
          <span className="hidden h-3 w-px bg-white/15 sm:inline" aria-hidden />
          <span className="text-[10px] text-slate-400 md:text-[11px]">
            <span className="text-slate-500">Rows </span>
            <span className="font-medium text-slate-200">{formatNumber(totalRows)}</span>
            <span className="text-slate-600"> · </span>
            <span className="text-slate-500">{sourceHealth.length} src</span>
          </span>
          <span className="hidden h-3 w-px bg-white/15 sm:inline" aria-hidden />
          <span className="text-[10px] text-slate-400 md:text-[11px]" title="Latest completed ingestion per source health">
            <span className="text-slate-500">Refresh </span>
            <span className="font-medium text-slate-300">{formatDateTime(latestRefresh)}</span>
          </span>
        </div>
      </div>
    </Card>
  );
}
