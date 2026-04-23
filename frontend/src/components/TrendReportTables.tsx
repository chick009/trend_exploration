import type { TrendCard } from "../api/types";
import { DataTable, type DataColumn } from "./ui";

type Props = {
  confirmed: TrendCard[];
  watch: TrendCard[];
  regionalDivergences: Array<Record<string, unknown>>;
};

function viralityDisplay(t: TrendCard): string {
  return String(Math.max(0, Math.min(100, Math.round(t.virality_score * 100))));
}

function shortText(text: string, max = 96): string {
  if (text.length <= max) {
    return text;
  }
  return `${text.slice(0, max - 1)}…`;
}

const trendTableColumns: DataColumn<TrendCard>[] = [
  { key: "rank", label: "Rank", align: "right", className: "whitespace-nowrap" },
  {
    key: "headline",
    label: "Trend",
    className: "max-w-[min(100vw,28rem)] text-slate-300",
    render: (row) => (
      <span className="line-clamp-2" title={row.trend_statement || row.headline}>
        {shortText(row.trend_statement || row.headline, 120)}
      </span>
    ),
  },
  { key: "term", label: "Signal term", className: "min-w-[140px] font-medium" },
  {
    key: "virality_score",
    label: "Virality",
    align: "right",
    className: "whitespace-nowrap",
    render: (row) => viralityDisplay(row),
  },
  { key: "confidence_tier", label: "Tier", className: "whitespace-nowrap" },
  { key: "trend_stage", label: "Stage", className: "whitespace-nowrap" },
  { key: "entity_type", label: "Type", className: "whitespace-nowrap" },
  {
    key: "evidence",
    label: "Signals",
    className: "text-xs text-slate-400",
    render: (row) => (row.signal_chips?.length ? row.signal_chips.join(" · ") : "—"),
  },
];

type DivergenceRow = { term: string; marketLine: string };

function divergenceRows(raw: Array<Record<string, unknown>>): DivergenceRow[] {
  return raw.map((row) => {
    const term = typeof row.term === "string" ? row.term : String(row.term ?? "—");
    const scores = row.market_scores;
    if (scores && typeof scores === "object" && scores !== null && !Array.isArray(scores)) {
      const line = Object.entries(scores as Record<string, number>)
        .map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(2) : String(v)}`)
        .join(" · ");
      return { term, marketLine: line || "—" };
    }
    return { term, marketLine: JSON.stringify(row) };
  });
}

const divergenceColumns: DataColumn<DivergenceRow>[] = [
  { key: "term", label: "Term", className: "font-medium" },
  { key: "marketLine", label: "Score by market", className: "text-slate-300" },
];

export function TrendReportTables({ confirmed, watch, regionalDivergences }: Props) {
  const divRows = divergenceRows(regionalDivergences);
  return (
    <div className="space-y-5">
      {confirmed.length > 0 ? (
        <div>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Confirmed — table</div>
          <DataTable
            rowKey={(row) => `c-${row.rank}-${row.term}`}
            columns={trendTableColumns}
            rows={confirmed}
            emptyState={<div className="text-sm text-slate-500">No rows.</div>}
          />
        </div>
      ) : null}

      {watch.length > 0 ? (
        <div>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Watch list — table</div>
          <DataTable
            rowKey={(row) => `w-${row.rank}-${row.term}`}
            columns={trendTableColumns}
            rows={watch}
            emptyState={<div className="text-sm text-slate-500">No rows.</div>}
          />
        </div>
      ) : null}

      {divRows.length > 0 ? (
        <div>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Regional divergences</div>
          <p className="mb-2 text-xs text-slate-500">
            Terms where cross-market virality spread exceeds the internal threshold.
          </p>
          <DataTable rowKey={(row) => `d-${row.term}`} columns={divergenceColumns} rows={divRows} />
        </div>
      ) : null}
    </div>
  );
}
