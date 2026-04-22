import type { AnalysisMode, Category, Market, RunStatusResponse } from "../api/types";
import { analysisModes, categories, markets } from "../lib/options";
import { cn } from "../lib/utils";
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
      nodeId: "evidence_synthesizer",
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
  for (let index = 0; index < steps.length; index += 1) {
    if (steps[index].status === "complete" || steps[index].status === "skipped") {
      lastDone = index;
    }
  }
  const errorAt = lastDone + 1;
  return steps.map((step, index) => {
    if (index === errorAt) {
      return { ...step, status: "error" as const };
    }
    if (index > errorAt) {
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

type SidebarProps = {
  market: Market;
  analysisMode: AnalysisMode;
  analysisRun?: RunStatusResponse;
  selectedNodeId?: string;
  onSelectNode?: (nodeId: string) => void;
};

export function GraphFlowStepsSidebar({ market, analysisMode, analysisRun, selectedNodeId, onSelectNode }: SidebarProps) {
  const trace = analysisRun?.execution_trace ?? [];
  const runStatus = analysisRun?.status;
  const baseSteps = buildGraphSteps(trace, runStatus, analysisMode, market);
  const steps = withFailedRunStepError(baseSteps, runStatus);

  return (
    <Card className="border-white/10">
      <CardHeader className="space-y-1">
        <Badge tone="accent">LangGraph</Badge>
        <CardTitle className="text-base">Logic flow</CardTitle>
        <CardDescription>Click a node to inspect shared state received, prompt handoff, and shared state emitted.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {steps.map((item) => {
          const colorKey = flowColorForStatus(item.status);
          const cls = flowColorClasses[colorKey];
          const blurb =
            item.id === "trend_gen" ? item.detail ?? STATIC_FLOW_DESCRIPTION.trend_gen : STATIC_FLOW_DESCRIPTION[item.id] ?? item.detail;
          const selected = selectedNodeId === item.nodeId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectNode?.(item.nodeId)}
              className={cn(
                "w-full rounded-2xl border border-white/10 border-l-4 bg-white/[0.04] p-3 pl-4 text-left transition hover:bg-white/[0.06]",
                cls.border,
                selected && "ring-2 ring-blue-400/60",
              )}
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
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

type RunControlBarProps = {
  analysisRun?: RunStatusResponse;
  market: Market;
  category: Category;
  recentDays: number;
  analysisMode: AnalysisMode;
  onMarketChange: (value: Market) => void;
  onCategoryChange: (value: Category) => void;
  onRecentDaysChange: (value: number) => void;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  workflowPrompt: string;
  onWorkflowPromptChange: (value: string) => void;
  onRunAnalysis: () => void;
  isBusy: boolean;
  runErrorMessage?: string | null;
};

export function RunControlBar({
  analysisRun,
  market,
  category,
  recentDays,
  analysisMode,
  onMarketChange,
  onCategoryChange,
  onRecentDaysChange,
  onAnalysisModeChange,
  workflowPrompt,
  onWorkflowPromptChange,
  onRunAnalysis,
  isBusy,
  runErrorMessage,
}: RunControlBarProps) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-white/10 pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <Badge tone="info">Run graph</Badge>
            <div className="space-y-1">
              <CardTitle>Scope, prompt, and execution</CardTitle>
              <CardDescription>
                Configure the run below (same fields as the workbench). Optional query steers the graph; inspect nodes from the logic flow
                sidebar.
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

      <CardContent className="space-y-5">
        <div className="space-y-3">
          <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Analysis scope</div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <label className="space-y-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Market</span>
              <select
                value={market}
                disabled={isBusy}
                onChange={(event) => onMarketChange(event.target.value as Market)}
                className="w-full"
              >
                {markets.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Category</span>
              <select
                value={category}
                disabled={isBusy}
                onChange={(event) => onCategoryChange(event.target.value as Category)}
                className="w-full"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <div className="space-y-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Recency</span>
              <div className="flex flex-wrap gap-1.5">
                {[7, 14, 30].map((days) => (
                  <button
                    key={days}
                    type="button"
                    disabled={isBusy}
                    onClick={() => onRecentDaysChange(days)}
                    className={cn(
                      "rounded-lg border px-2.5 py-1 text-xs font-medium transition",
                      recentDays === days
                        ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white"
                        : "border-white/10 bg-white/3 text-slate-200 hover:bg-slate-800/60 hover:text-slate-100",
                      isBusy && "cursor-not-allowed opacity-60",
                    )}
                  >
                    {days}d
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Mode</span>
              <div className="flex flex-col gap-1.5">
                {analysisModes.map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    disabled={isBusy}
                    onClick={() => onAnalysisModeChange(mode)}
                    className={cn(
                      "rounded-lg border px-2.5 py-1.5 text-left text-xs font-medium transition",
                      analysisMode === mode
                        ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white"
                        : "border-white/10 bg-white/3 text-slate-200 hover:bg-slate-800/60 hover:text-slate-100",
                      isBusy && "cursor-not-allowed opacity-60",
                    )}
                  >
                    {mode === "single_market" ? "Single market" : "Cross market"}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

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
      </CardContent>
    </Card>
  );
}

export function StreamingTraceCard({
  analysisRun,
  market,
  analysisMode,
}: {
  analysisRun?: RunStatusResponse;
  market: Market;
  analysisMode: AnalysisMode;
}) {
  const trace = analysisRun?.execution_trace ?? [];
  return (
    <Card>
      <CardHeader className="space-y-1">
        <Badge tone="info">Streaming trace</Badge>
        <CardTitle>Execution log</CardTitle>
        <CardDescription>Expanded only when you need the raw line-by-line backend trace.</CardDescription>
      </CardHeader>
      <CardContent>
        <details className="group rounded-2xl border border-white/10 bg-slate-950/40">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200">
            <span className="group-open:hidden">Show streaming log</span>
            <span className="hidden group-open:inline">Hide streaming log</span>
          </summary>
          <div className="border-t border-white/10 px-4 py-4">
            <div className="max-h-[min(420px,48vh)] overflow-y-auto rounded-2xl border border-white/10 bg-slate-950/50 p-4">
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
                  No lines yet. Run the graph to stream `execution_trace` from the backend.
                </div>
              )}
            </div>

            {analysisRun?.id ? (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/3 px-4 py-3 text-sm text-slate-400">
                Run <code className="inline-code">{analysisRun.id}</code> · {market} · {analysisMode.replace("_", " ")}
              </div>
            ) : null}
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

export function GraphWorkflowPanel({
  market,
  category,
  recentDays,
  analysisMode,
  analysisRun,
  onMarketChange,
  onCategoryChange,
  onRecentDaysChange,
  onAnalysisModeChange,
  workflowPrompt,
  onWorkflowPromptChange,
  onRunAnalysis,
  isBusy,
  runErrorMessage,
}: {
  market: Market;
  category: Category;
  recentDays: number;
  analysisMode: AnalysisMode;
  analysisRun?: RunStatusResponse;
  onMarketChange: (value: Market) => void;
  onCategoryChange: (value: Category) => void;
  onRecentDaysChange: (value: number) => void;
  onAnalysisModeChange: (value: AnalysisMode) => void;
  workflowPrompt: string;
  onWorkflowPromptChange: (value: string) => void;
  onRunAnalysis: () => void;
  isBusy: boolean;
  runErrorMessage?: string | null;
}) {
  return (
    <div className="space-y-6">
      <RunControlBar
        analysisRun={analysisRun}
        market={market}
        category={category}
        recentDays={recentDays}
        analysisMode={analysisMode}
        onMarketChange={onMarketChange}
        onCategoryChange={onCategoryChange}
        onRecentDaysChange={onRecentDaysChange}
        onAnalysisModeChange={onAnalysisModeChange}
        workflowPrompt={workflowPrompt}
        onWorkflowPromptChange={onWorkflowPromptChange}
        onRunAnalysis={onRunAnalysis}
        isBusy={isBusy}
        runErrorMessage={runErrorMessage}
      />
      <StreamingTraceCard analysisRun={analysisRun} market={market} analysisMode={analysisMode} />
    </div>
  );
}
