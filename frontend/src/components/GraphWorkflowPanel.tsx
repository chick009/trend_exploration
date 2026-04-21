import type { AnalysisMode, Market, RunStatusResponse } from "../api/types";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "./ui";

type StepStatus = "pending" | "active" | "complete" | "skipped";

export type GraphWorkflowStep = {
  id: string;
  title: string;
  nodeId: string;
  detail?: string;
  status: StepStatus;
};

export function buildGraphSteps(
  trace: string[],
  runStatus: string | undefined,
  analysisMode: AnalysisMode,
  market: Market,
): GraphWorkflowStep[] {
  const running = runStatus === "running" || runStatus === "queued";
  const intentLine = trace.find(
    (line) =>
      line.includes("[IntentParser]") &&
      (line.includes("market=") || line.includes("unsupported market") || line.includes("user_query=")),
  );
  const queryLine = trace.find((line) => line.includes("[IntentParser] user_query="));
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

  const trendDetail = trendLines.length ? trendLines.map((line) => line.replaceAll("[", "").replaceAll("]", "")).join(" · ") : regionHint;

  return [
    {
      id: "intent",
      title: "Intent parser",
      nodeId: "intent_parser",
      detail: queryLine ? "Parsed filters and captured the user prompt." : intentLine ? "Built query_params for retrieval." : undefined,
      status: intentLine ? "complete" : running ? "active" : "pending",
    },
    {
      id: "trend_gen",
      title: "Trend generation",
      nodeId: "trend_gen_agent",
      detail: trendDetail,
      status: trendLines.length > 0 ? "complete" : intentLine && running ? "active" : "pending",
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

type Props = {
  market: Market;
  analysisMode: AnalysisMode;
  analysisRun?: RunStatusResponse;
  workflowPrompt: string;
  onWorkflowPromptChange: (value: string) => void;
  onRunAnalysis: () => void;
  isBusy: boolean;
};

export function GraphWorkflowPanel({
  market,
  analysisMode,
  analysisRun,
  workflowPrompt,
  onWorkflowPromptChange,
  onRunAnalysis,
  isBusy,
}: Props) {
  const trace = analysisRun?.execution_trace ?? [];
  const steps = buildGraphSteps(trace, analysisRun?.status, analysisMode, market);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-white/10 pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <Badge tone="accent">LangGraph</Badge>
            <div className="space-y-1">
              <CardTitle>Trend discovery graph</CardTitle>
              <CardDescription>
                Mirrors <code className="inline-code">build_graph()</code>: START, intent parser, regional parallel trend generation, synthesizer, confidence gate, then formatter or END.
              </CardDescription>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <StatusPill status={analysisRun?.status ?? "idle"} />
            <Button variant="primary" onClick={onRunAnalysis} disabled={isBusy}>
              {isBusy ? "Running graph..." : "Run graph"}
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

        <div className="space-y-3" aria-label="Graph execution progress">
          {steps.map((item, index) => (
            <div key={item.id} className="relative pl-7">
              {index < steps.length - 1 ? <div className="absolute left-[11px] top-10 h-[calc(100%-16px)] w-px bg-white/10" /> : null}
              <div className="absolute left-0 top-2.5 h-[22px] w-[22px] rounded-full border border-white/10 bg-slate-900/90" />
              <article className="rounded-3xl border border-white/10 bg-white/3 p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-1">
                    <div className="text-base font-semibold text-slate-100">{item.title}</div>
                    <div className="text-xs uppercase tracking-[0.18em] text-slate-500">{item.nodeId}</div>
                  </div>
                  <StatusPill status={item.status} />
                </div>
                {item.detail ? <p className="mt-3 text-sm leading-6 text-slate-400">{item.detail}</p> : null}
              </article>
            </div>
          ))}
        </div>

        {analysisRun?.id ? (
          <div className="rounded-3xl border border-white/10 bg-white/3 px-4 py-3 text-sm text-slate-400">
            Active run <code className="inline-code">{analysisRun.id}</code>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
