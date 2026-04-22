import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { GraphFlowStepsSidebar, GraphWorkflowPanel } from "../../components/GraphWorkflowPanel";
import { ToolInvocationTimeline } from "../../components/ToolInvocationTimeline";
import { TrendCard } from "../../components/TrendCard";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, DataTable, StatusPill } from "../../components/ui";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { formatDateTime } from "../../lib/utils";

type Props = {
  workbench: TrendWorkbench;
};

export function LangGraphAgentTab({ workbench }: Props) {
  const { filters, actions, runState } = workbench;
  const recentRunsQuery = useQuery({
    queryKey: ["analysis-runs", runState.analysisRunId],
    queryFn: () => api.listAnalysisRuns(20, 0),
    refetchInterval: 4000,
  });

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
          <div className="eyebrow">History</div>
          <Card>
            <CardHeader>
              <CardTitle>Recent agent runs</CardTitle>
              <CardDescription>Open a run to load its stream, tool calls, and report below.</CardDescription>
            </CardHeader>
            <CardContent>
              <DataTable
                loading={recentRunsQuery.isLoading}
                rows={recentRunsQuery.data?.items ?? []}
                rowKey={(row) => row.id}
                columns={[
                  {
                    key: "status",
                    label: "Status",
                    render: (row) => <StatusPill status={row.status} />,
                  },
                  {
                    key: "started_at",
                    label: "Started",
                    render: (row) => formatDateTime(row.started_at),
                  },
                  {
                    key: "trace",
                    label: "Trace lines",
                    align: "right",
                    render: (row) => row.execution_trace.length,
                  },
                  {
                    key: "tools",
                    label: "Tool calls",
                    align: "right",
                    render: (row) => (row.tool_invocations ?? []).length,
                  },
                  {
                    key: "open",
                    label: "",
                    align: "right",
                    render: (row) => (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-blue-200"
                        onClick={(event) => {
                          event.stopPropagation();
                          actions.setAnalysisRunId(row.id);
                        }}
                      >
                        Load
                      </Button>
                    ),
                  },
                ]}
                onRowClick={(row) => actions.setAnalysisRunId(row.id)}
              />
            </CardContent>
          </Card>
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
                  No report for this run yet. Run the graph or load a completed analysis from history.
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
