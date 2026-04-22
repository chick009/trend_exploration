import type { AnalysisMode, Market, RunStatusResponse } from "../api/types";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "./ui";

export type GraphFlowStepStatus = "pending" | "active" | "complete" | "skipped" | "error";

export type GraphWorkflowStep = {
  id: string;
  title: string;
  nodeId: string;
  detail?: string;
  status: GraphFlowStepStatus;
};

const STATIC_FLOW_DESCRIPTION: Record<string, string> = {
  intent: "Converts the optional prompt into SQL-aligned filters.",
  backend_data: "Loads social, search, and sales signals outside LangGraph before agent execution.",
  trend_gen: "Parallel agents via Send() for the active market (cross-market uses multiple regions).",
  synth: "Combines source evidence into candidate scores.",
  gate: "Routes to formatter only when enough confidence is present.",
  format: "Builds the final report payload for this tab.",
};

export function buildGraphSteps(
  trace: string[],
  runStatus: string | undefined,
  analysisMode: AnalysisMode,
  market: Market,
): GraphWorkflowStep[] {
  const running = runStatus === "running" || runStatus === "queued";
  const intentLine = trace.find((line) => line.includes("[IntentParser]"));
  const queryLine = trace.find((line) => line.includes("[IntentParser] user_query="));
  const backendDataLine = trace.find((line) => line.includes("[BackendData]"));
  const trendLines = trace.filter((line) => line.includes("[TrendGen:"));
  const synthLine = trace.find((line) => line.includes("[Synthesizer]"));
  const gateLine = trace.find((line) => line.includes("[ConfidenceGate]"));
  const formatterLine = trace.find((line) => line.includes("[Formatter]"));

  const routesToFormatter = gateLine?.includes("route=formatter") ?? false;
  const gateEnds = gateLine?.includes("route=end") ?? false;
  const regionHint =
    analysisMode === "cross_market" || market === "cross"
      ? "Parallel agents: HK, KR, TW, SG"
      : `Parallel agents via Send() for ${market === "cross" ? "regions" : market}`;

  const trendDetail = trendLines.length
    ? trendLines.map((line) => line.replaceAll("[", "").replaceAll("]", "")).join(" · ")
    : regionHint;

  return [
    {
      id: "intent",
      title: "Text-to-SQL planner",
      nodeId: "intent_parser",
      detail: queryLine
        ? "Mapped the prompt into SQL-aligned filters and preserved the original request."
        : intentLine
          ? "Prepared the SQL query plan that the backend loader uses before the graph starts."
          : "Converts the optional prompt into SQL-aligned filters.",
      status: intentLine ? "complete" : running ? "active" : "pending",
    },
    {
      id: "backend_data",
      title: "Backend signal loading",
      nodeId: "backend_preload",
      detail: backendDataLine ?? "Loads social, search, and sales signals outside LangGraph before agent execution.",
      status: backendDataLine ? "complete" : intentLine && running ? "active" : "pending",
    },
    {
      id: "trend_gen",
      title: "Trend generation",
      nodeId: "trend_gen_agent",
      detail: trendDetail,
      status: trendLines.length > 0 ? "complete" : backendDataLine && running ? "active" : "pending",
    },
    {
      id: "synth",
      title: "Evidence synthesizer",
      nodeId: "synthesizer",
      detail: synthLine ?? "Combines source evidence into candidate scores.",
      status: synthLine ? "complete" : trendLines.length > 0 && running ? "active" : "pending",
    },
    {
      id: "gate",
      title: "Confidence gate",
      nodeId: "confidence_gate",
      detail: gateLine ?? "Routes to formatter only when enough confidence is present.",
      status: gateLine ? "complete" : synthLine && running ? "active" : "pending",
    },
    {
      id: "format",
      title: "Report formatter",
      nodeId: "formatter",
      detail: formatterLine ?? "Builds the final response payload for the frontend.",
      status: gateEnds ? "skipped" : formatterLine ? "complete" : routesToFormatter && gateLine && running ? "active" : "pending",
    },
  ];
}

export function withFailedRunStepError(steps: GraphWorkflowStep[], runStatus: string | undefined): GraphWorkflowStep[] {
  if (runStatus !== "failed") {
    return steps;
  }
  let lastDone = -1;
  for (let i = 0; i < steps.length; i += 1) {
    if (steps[i].status === "complete" || steps[i].status === "skipped") {
      lastDone = i;
    }
  }
  const errAt = lastDone + 1;
  return steps.map((step, i) => {
    if (i === errAt) {
      return { ...step, status: "error" as const };
    }
    if (i > errAt) {
      return { ...step, status: "pending" as const };
    }
    return step;
  });
}

type FlowColor = "success" | "error" | "pending";

function flowColorForStatus(status: GraphFlowStepStatus): FlowColor {
  if (status === "complete" || status === "skipped") {
    return "success";
  }
  if (status === "error") {
    return "error";
  }
  return "pending";
}

const flowColorClasses: Record<FlowColor, { border: string; label: string; badge: "success" | "danger" | "info" }> = {
  success: {
    border: "border-l-emerald-500/80",
    label: "text-emerald-200/90",
    badge: "success",
  },
  error: {
    border: "border-l-rose-500/90",
    label: "text-rose-200/90",
    badge: "danger",
  },
  pending: {
    border: "border-l-sky-500/85",
    label: "text-sky-200/90",
    badge: "info",
  },
};

const FLOW_STATUS_LABEL: Record<GraphFlowStepStatus, string> = {
  complete: "completed",
  skipped: "skipped",
  error: "error",
  pending: "pending",
  active: "active",
};

export function GraphFlowStepsSidebar({
  market,
  analysisMode,
  analysisRun,
}: {
  market: Market;
  analysisMode: AnalysisMode;
  analysisRun?: RunStatusResponse;
}) {
  const trace = analysisRun?.execution_trace ?? [];
  const runStatus = analysisRun?.status;
  const baseSteps = buildGraphSteps(trace, runStatus, analysisMode, market);
  const steps = withFailedRunStepError(baseSteps, runStatus);

  return (
    <Card className="border-white/10">
      <CardHeader className="space-y-1">
        <Badge tone="accent">LangGraph</Badge>
        <CardTitle className="text-base">Logic flow</CardTitle>
        <CardDescription>Planner → preload → agents → synthesis → gate → report.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {steps.map((item) => {
          const colorKey = flowColorForStatus(item.status);
          const cls = flowColorClasses[colorKey];
          const blurb =
            item.id === "trend_gen" ? item.detail ?? STATIC_FLOW_DESCRIPTION.trend_gen : STATIC_FLOW_DESCRIPTION[item.id] ?? item.detail;
          return (
            <div
              key={item.id}
              className={`rounded-2xl border border-white/10 border-l-4 bg-white/[0.04] p-3 pl-4 ${cls.border}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold text-slate-100">{item.title}</div>
                  <div className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-slate-500">
                    {item.nodeId}
                  </div>
                </div>
                <Badge tone={cls.badge} className="shrink-0">
                  {FLOW_STATUS_LABEL[item.status]}
                </Badge>
              </div>
              {blurb ? <p className={`mt-2 text-xs leading-relaxed ${cls.label}`}>{blurb}</p> : null}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

type StreamPanelProps = {
  market: Market;
  analysisMode: AnalysisMode;
  analysisRun?: RunStatusResponse;
  workflowPrompt: string;
  onWorkflowPromptChange: (value: string) => void;
  onRunAnalysis: () => void;
  isBusy: boolean;
  runErrorMessage?: string | null;
};

export function GraphWorkflowPanel({
  market,
  analysisMode,
  analysisRun,
  workflowPrompt,
  onWorkflowPromptChange,
  onRunAnalysis,
  isBusy,
  runErrorMessage,
}: StreamPanelProps) {
  const trace = analysisRun?.execution_trace ?? [];

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-white/10 pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <Badge tone="info">Stream</Badge>
            <div className="space-y-1">
              <CardTitle>Runtime trace and tool calls</CardTitle>
              <CardDescription>
                Line-delimited log stream as the run progresses; tool invocations are summarized in the next card.
              </CardDescription>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <StatusPill status={analysisRun?.status ?? "idle"} />
            <Button variant="primary" onClick={onRunAnalysis} disabled={isBusy}>
              {isBusy ? "Running…" : "Run graph"}
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        <label className="block space-y-2">
          <span className="text-sm font-medium text-slate-200">Optional query</span>
          <textarea
            rows={3}
            placeholder="e.g. Focus on barrier repair and sensitive skin narratives in HK."
            value={workflowPrompt}
            onChange={(event) => onWorkflowPromptChange(event.target.value)}
            disabled={isBusy}
            className="min-h-[96px] w-full resize-y"
          />
        </label>

        {runErrorMessage ? (
          <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
            {runErrorMessage}
          </div>
        ) : null}

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Streaming log</div>
          <div className="max-h-[min(520px,60vh)] overflow-y-auto rounded-2xl border border-white/10 bg-slate-950/50 p-4">
            {trace.length > 0 ? (
              <ol className="list-decimal space-y-2 pl-4 font-mono text-[11px] leading-relaxed text-slate-300 [word-break:break-word]">
                {trace.map((line, index) => (
                  <li key={`${index}-${line.slice(0, 64)}`} className="marker:text-slate-600">
                    {line}
                  </li>
                ))}
              </ol>
            ) : (
              <div className="px-1 py-10 text-center text-sm text-slate-500">
                No lines yet. Run the graph to stream execution_trace from the backend.
              </div>
            )}
          </div>
        </div>

        {analysisRun?.id ? (
          <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3 text-sm text-slate-400">
            Run <code className="inline-code">{analysisRun.id}</code> · {market} · {analysisMode.replace("_", " ")}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
