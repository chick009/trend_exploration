import type { ToolInvocation, ToolInvocationKind, ToolInvocationStatus } from "../api/types";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "./ui";
import { formatDateTime } from "../lib/utils";

type Props = {
  invocations: ToolInvocation[];
  runStatus?: string;
};

const KIND_LABEL: Record<ToolInvocationKind, string> = {
  sql: "SQL",
  llm: "LLM",
  memory: "Memory",
};

const KIND_TONE: Record<ToolInvocationKind, "info" | "accent" | "success"> = {
  sql: "info",
  llm: "accent",
  memory: "success",
};

const STATUS_PILL: Record<ToolInvocationStatus, string> = {
  running: "running",
  success: "completed",
  error: "failed",
};

function formatDuration(durationMs?: number | null): string | null {
  if (durationMs == null || Number.isNaN(durationMs)) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)} ms`;
  }
  return `${(durationMs / 1000).toFixed(2)} s`;
}

function countByKind(invocations: ToolInvocation[]): Record<ToolInvocationKind, number> {
  const counts: Record<ToolInvocationKind, number> = { sql: 0, llm: 0, memory: 0 };
  for (const entry of invocations) {
    counts[entry.tool_kind] += 1;
  }
  return counts;
}

export function ToolInvocationTimeline({ invocations, runStatus }: Props) {
  const counts = countByKind(invocations);
  const isRunning = runStatus === "running" || runStatus === "queued";

  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <Badge tone="info">Tool use</Badge>
            <CardTitle>LangGraph tool timeline</CardTitle>
            <CardDescription>
              Live view of every tool the multi-agent run invokes: SQL queries against the internal SQLite database,
              LLM calls for planning and scoring, and memory reads/writes.
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={KIND_TONE.sql}>SQL · {counts.sql}</Badge>
            <Badge tone={KIND_TONE.llm}>LLM · {counts.llm}</Badge>
            <Badge tone={KIND_TONE.memory}>Memory · {counts.memory}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {invocations.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
            {isRunning
              ? "Waiting for the first tool call from the LangGraph run..."
              : "No tool invocations captured yet. Run the graph to populate the timeline."}
          </div>
        ) : (
          invocations.map((entry, index) => (
            <article
              key={entry.id}
              className="relative rounded-3xl border border-white/10 bg-white/3 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={KIND_TONE[entry.tool_kind]}>{KIND_LABEL[entry.tool_kind]}</Badge>
                    <span className="text-xs uppercase tracking-[0.18em] text-slate-500">#{index + 1}</span>
                    <code className="inline-code">{entry.tool}</code>
                  </div>
                  <div className="text-sm font-semibold text-slate-100">{entry.title}</div>
                  <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{entry.node}</div>
                </div>
                <div className="flex flex-col items-end gap-1 text-xs text-slate-400">
                  <StatusPill status={STATUS_PILL[entry.status]} />
                  {entry.duration_ms != null ? <span>{formatDuration(entry.duration_ms)}</span> : null}
                  {entry.started_at ? <span>{formatDateTime(entry.started_at)}</span> : null}
                </div>
              </div>

              {entry.input_summary ? (
                <p className="mt-3 text-sm text-slate-300">
                  <span className="text-slate-500">Input: </span>
                  {entry.input_summary}
                </p>
              ) : null}

              {entry.sql ? (
                <pre className="mt-3 max-h-60 overflow-auto rounded-2xl border border-white/5 bg-slate-950/70 p-3 text-xs leading-5 text-blue-100">
                  <code>{entry.sql}</code>
                </pre>
              ) : null}

              {entry.output_summary ? (
                <p className="mt-3 text-sm text-emerald-200">
                  <span className="text-slate-500">Output: </span>
                  {entry.output_summary}
                </p>
              ) : null}

              {entry.error ? (
                <p className="mt-3 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                  {entry.error}
                </p>
              ) : null}
            </article>
          ))
        )}
      </CardContent>
    </Card>
  );
}
