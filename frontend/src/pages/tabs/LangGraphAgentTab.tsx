import { GraphFlowStepsSidebar, GraphWorkflowPanel } from "../../components/GraphWorkflowPanel";
import { ToolInvocationTimeline } from "../../components/ToolInvocationTimeline";
import { TrendCard } from "../../components/TrendCard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, StatusPill } from "../../components/ui";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";

type Props = {
  workbench: TrendWorkbench;
};

function CurrentAgentStatusLine({ workbench }: { workbench: TrendWorkbench }) {
  const { runState } = workbench;
  const { analysisRun, runErrorMessage, analysisStreamActive } = runState;
  const streamBusy = analysisStreamActive;

  if (streamBusy || analysisRun?.status === "running" || analysisRun?.status === "queued") {
    return <p className="text-sm text-slate-300">Loading…</p>;
  }
  if (runErrorMessage) {
    return <p className="text-sm font-medium text-rose-200/90">Error: {runErrorMessage}</p>;
  }
  if (analysisRun?.status === "completed") {
    return <p className="text-sm font-medium text-emerald-200/90">Success</p>;
  }
  if (analysisRun?.status === "failed") {
    return (
      <p className="text-sm font-medium text-rose-200/90">
        Error{analysisRun.error_message ? `: ${analysisRun.error_message}` : ""}
      </p>
    );
  }
  return <p className="text-sm text-slate-500">Idle. Run the graph to see status, or open Execution log for run history.</p>;
}

export function LangGraphAgentTab({ workbench }: Props) {
  const { filters, actions, runState } = workbench;

  const report = runState.agentReport;
  const toolInvocations = runState.analysisRun?.tool_invocations ?? [];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
      <div className="grid gap-4 xl:sticky xl:top-28 xl:h-fit">
        <GraphFlowStepsSidebar
          market={filters.market}
          analysisMode={filters.analysisMode}
          analysisRun={runState.analysisRun}
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Analysis input</CardTitle>
            <CardDescription>Scope comes from the workbench filters; optional query is below in the stream panel.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-300">
            <div className="rounded-2xl border border-white/10 bg-white/3 px-3 py-2">Market: {filters.market}</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-3 py-2">Category: {filters.category}</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-3 py-2">Recency: {filters.recentDays} days</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-3 py-2">
              Mode: {filters.analysisMode === "single_market" ? "Single market" : "Cross market"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Current agent run</CardTitle>
            <CardDescription>Loading, success, or error for the active workbench run only.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <CurrentAgentStatusLine workbench={workbench} />
            <a
              href="#execution_log"
              className="inline-block text-sm text-blue-200/95 underline decoration-blue-200/30 underline-offset-2 hover:decoration-blue-200/80"
            >
              Open execution log for run history, traces, and tools
            </a>
          </CardContent>
        </Card>
      </div>

      <div className="grid min-w-0 gap-6">
        <section className="space-y-4">
          <div className="eyebrow">Stream and tools</div>
          <GraphWorkflowPanel
            market={filters.market}
            analysisMode={filters.analysisMode}
            analysisRun={runState.analysisRun}
            workflowPrompt={filters.workflowPrompt}
            onWorkflowPromptChange={actions.setWorkflowPrompt}
            onRunAnalysis={actions.runAnalysis}
            isBusy={runState.isBusy}
            runErrorMessage={runState.runErrorMessage}
          />

          <ToolInvocationTimeline invocations={toolInvocations} runStatus={runState.analysisRun?.status} />
        </section>

        <section className="space-y-3">
          <div className="eyebrow">Output</div>
          <Card>
            <CardHeader>
              <CardTitle>Report</CardTitle>
              <CardDescription>Trend cards from the loaded or most recent run.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {report ? (
                <>
                  <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
                    <StatusPill status={runState.analysisRun?.status ?? "completed"} />
                    <span>{report.market}</span>
                    <span>{report.category}</span>
                    <span>{report.recency_days} days</span>
                  </div>

                  <div className="grid gap-4">
                    {report.trends.map((trend) => (
                      <TrendCard key={`${trend.term}-${trend.rank}-agent`} trend={trend} />
                    ))}
                  </div>
                </>
              ) : (
                <div className="rounded-3xl border border-dashed border-white/10 px-4 py-10 text-sm text-slate-500">
                  No report for this run yet. Run the graph or load a run from Execution log.
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
