import type { RunStatusResponse, SourceHealth } from "../api/types";
import { formatDateTime, formatNumber } from "../lib/utils";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "./ui";

type Props = {
  ingestionRun?: RunStatusResponse;
  analysisRun?: RunStatusResponse;
  sourceHealth: SourceHealth[];
  guardrailFlags: string[];
};

const sourceHealthLabels: Record<string, string> = {
  google_trends: "Google Trends",
  sales: "Sales",
  tiktok: "TikTok photos",
  instagram: "Instagram",
};

export function ReasoningTrace({ ingestionRun, analysisRun, sourceHealth, guardrailFlags }: Props) {
  const combinedGuardrails = [...(ingestionRun?.guardrail_flags ?? []), ...guardrailFlags];
  const executionTrace = [...(analysisRun?.execution_trace ?? []), ...(ingestionRun?.execution_trace ?? [])];

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader>
          <Badge tone="accent">Trace</Badge>
          <CardTitle>Run status</CardTitle>
          <CardDescription>Monitor the active extraction batch and the latest LangGraph analysis run.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div className="rounded-3xl border border-white/10 bg-white/3 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium text-slate-200">Ingestion</span>
              <StatusPill status={ingestionRun?.status} />
            </div>
            <div className="text-sm text-slate-400">Batch {ingestionRun?.source_batch_id ?? "n/a"}</div>
          </div>
          <div className="rounded-3xl border border-white/10 bg-white/3 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium text-slate-200">Analysis</span>
              <StatusPill status={analysisRun?.status} />
            </div>
            <div className="text-sm text-slate-400">Report {analysisRun?.report?.report_id ?? "not generated"}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Execution log</CardTitle>
          <CardDescription>Live graph trace and ingestion runtime notes.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {executionTrace.length > 0 ? (
            executionTrace.map((entry) => (
              <div key={entry} className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3 text-sm text-slate-300">
                {entry}
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
              No execution log yet.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Guardrails</CardTitle>
          <CardDescription>Warnings raised during extraction or synthesis.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {combinedGuardrails.length > 0 ? (
            combinedGuardrails.map((flag) => (
              <div key={flag} className="rounded-2xl border border-amber-400/15 bg-amber-500/8 px-4 py-3 text-sm text-amber-100">
                {flag}
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
              No guardrail warnings raised.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Source freshness</CardTitle>
          <CardDescription>Latest completed batch and row counts in the warehouse.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {sourceHealth.map((source) => (
            <div key={source.source} className="rounded-3xl border border-white/10 bg-white/3 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-100">{sourceHealthLabels[source.source] ?? source.source}</div>
                  <div className="mt-1 text-xs text-slate-500">Last updated {formatDateTime(source.latest_completed_at)}</div>
                </div>
                <Badge tone="info" className="normal-case tracking-normal text-[12px]">
                  {formatNumber(source.row_count)} rows
                </Badge>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
