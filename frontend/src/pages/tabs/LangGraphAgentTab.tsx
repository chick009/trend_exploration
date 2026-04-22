import { useEffect, useMemo, useState } from "react";

import { AgentNodeDrawer } from "../../components/AgentNodeDrawer";
import {
  buildGraphSteps,
  GraphFlowStepsSidebar,
  RunControlBar,
  StreamingTraceCard,
  withFailedRunStepError,
} from "../../components/GraphWorkflowPanel";
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
  const [selectedNodeId, setSelectedNodeId] = useState<string>();

  const graphSteps = useMemo(() => {
    const baseSteps = buildGraphSteps(
      runState.analysisRun?.execution_trace ?? [],
      runState.analysisRun?.status,
      filters.analysisMode,
      filters.market,
    );
    return withFailedRunStepError(baseSteps, runState.analysisRun?.status);
  }, [filters.analysisMode, filters.market, runState.analysisRun?.execution_trace, runState.analysisRun?.status]);

  useEffect(() => {
    if (graphSteps.length === 0) {
      return;
    }
    if (selectedNodeId && graphSteps.some((step) => step.nodeId === selectedNodeId)) {
      return;
    }
    const preferredStep =
      graphSteps.find((step) => step.status === "active") ??
      graphSteps.find((step) => step.status === "complete" || step.status === "error" || step.status === "skipped") ??
      graphSteps[0];
    setSelectedNodeId(preferredStep.nodeId);
  }, [graphSteps, selectedNodeId]);

  const selectedStep = graphSteps.find((step) => step.nodeId === selectedNodeId);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(260px,320px)_minmax(0,1fr)]">
      <div className="grid gap-4 xl:sticky xl:top-28 xl:h-fit">
        <GraphFlowStepsSidebar
          market={filters.market}
          analysisMode={filters.analysisMode}
          analysisRun={runState.analysisRun}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />

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
          <div className="eyebrow">Run and inspect</div>
          <RunControlBar
            analysisRun={runState.analysisRun}
            market={filters.market}
            category={filters.category}
            recentDays={filters.recentDays}
            analysisMode={filters.analysisMode}
            onMarketChange={actions.setMarket}
            onCategoryChange={actions.setCategory}
            onRecentDaysChange={actions.setRecentDays}
            onAnalysisModeChange={actions.setAnalysisMode}
            workflowPrompt={filters.workflowPrompt}
            onWorkflowPromptChange={actions.setWorkflowPrompt}
            onRunAnalysis={actions.runAnalysis}
            isBusy={runState.isBusy}
            runErrorMessage={runState.runErrorMessage}
          />
          <AgentNodeDrawer step={selectedStep} analysisRun={runState.analysisRun} />
          <StreamingTraceCard
            analysisRun={runState.analysisRun}
            market={filters.market}
            analysisMode={filters.analysisMode}
          />
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
