import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { GraphWorkflowPanel } from "../../components/GraphWorkflowPanel";
import { TrendCard } from "../../components/TrendCard";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, DataTable, StatusPill } from "../../components/ui";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { promptPresets } from "../../lib/options";
import { formatDateTime } from "../../lib/utils";

type Props = {
  workbench: TrendWorkbench;
};

export function LangGraphAgentTab({ workbench }: Props) {
  const { filters, actions, queries, runState } = workbench;
  const recentRunsQuery = useQuery({
    queryKey: ["analysis-runs", runState.analysisRunId],
    queryFn: () => api.listAnalysisRuns(20, 0),
    refetchInterval: 4000,
  });

  const report = queries.analysisQuery.data?.report ?? runState.report;
  const rawTrace = queries.analysisQuery.data?.execution_trace ?? [];

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <div className="grid gap-6 xl:sticky xl:top-28 xl:h-fit">
        <Card>
          <CardHeader>
            <Badge tone="accent">Agent demos</Badge>
            <CardTitle>Prompt presets</CardTitle>
            <CardDescription>Load a curated LangGraph scenario, then run the backend graph with one click.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {promptPresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  actions.setMarket(preset.market);
                  actions.setCategory(preset.category);
                  actions.setAnalysisMode(preset.analysisMode);
                  actions.setWorkflowPrompt(preset.query);
                }}
                className="w-full rounded-3xl border border-white/10 bg-white/3 p-4 text-left transition hover:bg-white/6"
              >
                <div className="text-sm font-semibold text-slate-100">{preset.label}</div>
                <div className="mt-1 text-sm leading-6 text-slate-400">{preset.query}</div>
              </button>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active analysis settings</CardTitle>
            <CardDescription>These controls feed directly into the LangGraph analysis request payload.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-300">
            <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3">Market: {filters.market}</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3">Category: {filters.category}</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3">Recency: {filters.recentDays} days</div>
            <div className="rounded-2xl border border-white/10 bg-white/3 px-4 py-3">
              Mode: {filters.analysisMode === "single_market" ? "Single market" : "Cross market"}
            </div>
            <Button variant="primary" className="w-full" disabled={runState.isBusy} onClick={actions.runAnalysis}>
              {runState.isBusy ? "Running analysis..." : "Run graph"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6">
        <GraphWorkflowPanel
          market={filters.market}
          analysisMode={filters.analysisMode}
          analysisRun={queries.analysisQuery.data}
          workflowPrompt={filters.workflowPrompt}
          onWorkflowPromptChange={actions.setWorkflowPrompt}
          onRunAnalysis={actions.runAnalysis}
          isBusy={runState.isBusy}
        />

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
          <Card>
            <CardHeader>
              <CardTitle>Recent agent runs</CardTitle>
              <CardDescription>Replay a previous execution trace by loading one of the saved analysis runs.</CardDescription>
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

          <Card>
            <CardHeader>
              <CardTitle>Raw execution trace</CardTitle>
              <CardDescription>Low-level trace lines emitted by the backend graph as it runs.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {rawTrace.length > 0 ? (
                rawTrace.map((entry) => (
                  <div key={entry} className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-300">
                    {entry}
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                  Run the graph or load a recent run to inspect its trace.
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Rendered report</CardTitle>
            <CardDescription>The LangGraph demo ends with the same trend report format consumed by the main dashboard.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {report ? (
              <>
                <div className="flex flex-wrap items-center gap-3 text-sm text-slate-400">
                  <StatusPill status={queries.analysisQuery.data?.status ?? "completed"} />
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
                No report loaded yet. Run the graph or load one of the recent analysis runs.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
