import type { SourceHealth } from "../api/types";
import { formatDateTime, formatNumber } from "../lib/utils";
import { Badge, Card, StatusPill } from "./ui";

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

  return (
    <Card className="overflow-hidden">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Badge tone="accent">Trend exploration workspace</Badge>
          <div className="space-y-3">
            <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-slate-50 md:text-4xl">
              Health and beauty trend intelligence with extraction visibility, database transparency, and LangGraph demos.
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-slate-400 md:text-base">
              Review the confirmed trends, inspect extraction batches with sample rows and error states, browse the SQLite warehouse,
              and demo the LangGraph backend in a single professional workspace.
            </p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-1">
          <div className="rounded-[24px] border border-white/10 bg-white/4 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Pipeline</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <StatusPill status={ingestionStatus ?? "idle"} />
              <StatusPill status={analysisStatus ?? "idle"} />
            </div>
          </div>

          <div className="rounded-[24px] border border-white/10 bg-white/4 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Indexed rows</div>
            <div className="mt-3 text-2xl font-semibold text-slate-50">{formatNumber(totalRows)}</div>
            <div className="mt-1 text-sm text-slate-400">{sourceHealth.length} tracked sources</div>
          </div>

          <div className="rounded-[24px] border border-white/10 bg-white/4 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Latest refresh</div>
            <div className="mt-3 text-sm font-medium text-slate-200">{formatDateTime(latestRefresh)}</div>
            <div className="mt-1 text-sm text-slate-400">Aggregated from source health checks.</div>
          </div>
        </div>
      </div>
    </Card>
  );
}
