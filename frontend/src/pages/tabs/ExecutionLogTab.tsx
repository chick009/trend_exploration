import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { RunStatusResponse } from "../../api/types";
import { ToolInvocationTimeline } from "../../components/ToolInvocationTimeline";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DataTable,
  JsonView,
  SimpleDialog,
  StatusPill,
} from "../../components/ui";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { sourceLabels } from "../../lib/options";
import { formatDateTime, formatDuration, formatNumber } from "../../lib/utils";

type Props = {
  workbench: TrendWorkbench;
};

function getRowCount(run: RunStatusResponse) {
  const stats = run.stats ?? {};
  return ["search_rows", "social_rows", "sales_rows", "tiktok_rows", "instagram_rows"]
    .map((key) => Number(stats[key] ?? 0))
    .filter((value) => Number.isFinite(value))
    .reduce((sum, value) => sum + value, 0);
}

const BATCH_SAMPLE_PREVIEW = 5;
const BATCH_SAMPLE_FULL = 100;

type BatchSampleTable = "sales_data" | "tiktok_photo_posts" | "instagram_posts";

export function ExecutionLogTab({ workbench }: Props) {
  const { actions, runState } = workbench;

  const [selectedIngestionRunId, setSelectedIngestionRunId] = useState<string | null>(null);
  const [ingestionDialogOpen, setIngestionDialogOpen] = useState(false);
  const [batchSampleLimits, setBatchSampleLimits] = useState<Record<BatchSampleTable, number>>({
    sales_data: BATCH_SAMPLE_PREVIEW,
    tiktok_photo_posts: BATCH_SAMPLE_PREVIEW,
    instagram_posts: BATCH_SAMPLE_PREVIEW,
  });

  const [selectedAgentRunId, setSelectedAgentRunId] = useState<string | null>(null);

  const recentIngestionQuery = useQuery({
    queryKey: ["ingestion-runs", runState.ingestionRunId],
    queryFn: () => api.listIngestionRuns(20, 0),
    refetchInterval: 4000,
  });

  const recentAnalysisQuery = useQuery({
    queryKey: ["analysis-runs", "execution-log", runState.analysisRunId],
    queryFn: () => api.listAnalysisRuns(20, 0),
    refetchInterval: 4000,
  });

  const selectedIngestionDetailQuery = useQuery({
    queryKey: ["ingestion-run-detail", selectedIngestionRunId],
    queryFn: () => api.getIngestionRun(selectedIngestionRunId!),
    enabled: ingestionDialogOpen && Boolean(selectedIngestionRunId),
  });

  const selectedAgentDetailQuery = useQuery({
    queryKey: ["analysis-run", "execution-log-detail", selectedAgentRunId],
    queryFn: () => api.getAnalysisRun(selectedAgentRunId!),
    enabled: Boolean(selectedAgentRunId),
  });

  const selectedIngestionRun =
    selectedIngestionDetailQuery.data ?? recentIngestionQuery.data?.items.find((item) => item.id === selectedIngestionRunId);
  const selectedBatchId = selectedIngestionRun?.source_batch_id;

  useEffect(() => {
    if (ingestionDialogOpen && selectedBatchId) {
      setBatchSampleLimits({
        sales_data: BATCH_SAMPLE_PREVIEW,
        tiktok_photo_posts: BATCH_SAMPLE_PREVIEW,
        instagram_posts: BATCH_SAMPLE_PREVIEW,
      });
    }
  }, [ingestionDialogOpen, selectedBatchId]);

  const salesSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "sales_data", selectedBatchId, batchSampleLimits.sales_data],
    queryFn: () =>
      api.getTableRows("sales_data", {
        limit: batchSampleLimits.sales_data,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "week_start",
        order_dir: "desc",
      }),
    enabled: ingestionDialogOpen && Boolean(selectedBatchId),
  });

  const tiktokSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "tiktok_photo_posts", selectedBatchId, batchSampleLimits.tiktok_photo_posts],
    queryFn: () =>
      api.getTableRows("tiktok_photo_posts", {
        limit: batchSampleLimits.tiktok_photo_posts,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "fetched_at",
        order_dir: "desc",
      }),
    enabled: ingestionDialogOpen && Boolean(selectedBatchId),
  });

  const instagramSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "instagram_posts", selectedBatchId, batchSampleLimits.instagram_posts],
    queryFn: () =>
      api.getTableRows("instagram_posts", {
        limit: batchSampleLimits.instagram_posts,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "fetched_at",
        order_dir: "desc",
      }),
    enabled: ingestionDialogOpen && Boolean(selectedBatchId),
  });

  const failedIngestionRuns =
    recentIngestionQuery.data?.items.filter((item) => item.status === "failed" || item.error_message) ?? [];

  return (
    <div className="grid gap-6">
      <div>
        <div className="eyebrow">Ingestion</div>
        <h2 className="mt-1 text-lg font-semibold text-slate-50">Recent extraction runs</h2>
        <p className="mt-1 text-sm text-slate-500">Status, row counts, and batch inspection. Ingestion runs do not emit a line trace; see stats and errors below.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent extraction runs</CardTitle>
          <CardDescription>Review job status, duration, row counts, and open a run for full diagnostics and sample rows.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            loading={recentIngestionQuery.isLoading}
            rows={recentIngestionQuery.data?.items ?? []}
            rowKey={(row) => row.id}
            columns={[
              {
                key: "status",
                label: "Status",
                render: (row) => <StatusPill status={row.status} />,
              },
              {
                key: "source_batch_id",
                label: "Batch",
                render: (row) => <code className="inline-code">{row.source_batch_id ?? "n/a"}</code>,
              },
              {
                key: "started_at",
                label: "Started",
                render: (row) => formatDateTime(row.started_at),
              },
              {
                key: "duration",
                label: "Duration",
                render: (row) => formatDuration(row.started_at, row.completed_at),
              },
              {
                key: "rows",
                label: "Rows",
                align: "right",
                render: (row) => formatNumber(getRowCount(row)),
              },
              {
                key: "view",
                label: "",
                align: "right",
                render: (row) => (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-blue-200"
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedIngestionRunId(row.id);
                      setIngestionDialogOpen(true);
                    }}
                  >
                    View
                  </Button>
                ),
              },
            ]}
            onRowClick={(row) => {
              setSelectedIngestionRunId(row.id);
              setIngestionDialogOpen(true);
            }}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Extraction error log</CardTitle>
          <CardDescription>Failed runs and warnings from recent extractions.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {failedIngestionRuns.length > 0 ? (
            failedIngestionRuns.map((run) => (
              <div key={run.id} className="rounded-xl border border-red-400/20 bg-red-500/8 p-3">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <StatusPill status={run.status} />
                  <span className="text-[11px] text-slate-400">{formatDateTime(run.completed_at ?? run.started_at)}</span>
                </div>
                <div className="text-xs leading-relaxed text-red-100">{run.error_message ?? "Guardrail warning present in stats."}</div>
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-xs text-slate-500">
              No extraction failures in the recent runs list.
            </div>
          )}
        </CardContent>
      </Card>

      <div>
        <div className="eyebrow">LangGraph</div>
        <h2 className="mt-1 text-lg font-semibold text-slate-50">Recent agent runs</h2>
        <p className="mt-1 text-sm text-slate-500">Select a run to load the streaming execution trace and tool invocations on this page.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent agent runs</CardTitle>
          <CardDescription>Open a run to mirror it in the workbench, or select a row to inspect the log below without switching tabs.</CardDescription>
        </CardHeader>
        <CardContent>
          <DataTable
            loading={recentAnalysisQuery.isLoading}
            rows={recentAnalysisQuery.data?.items ?? []}
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
            onRowClick={(row) => {
              setSelectedAgentRunId(row.id);
              actions.setAnalysisRunId(row.id);
            }}
          />
        </CardContent>
      </Card>

      {selectedAgentRunId ? (
        <Card>
          <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Agent run log</CardTitle>
              <CardDescription>Execution trace and tool calls for the selected run.</CardDescription>
            </div>
            {selectedAgentDetailQuery.data?.id ? (
              <code className="text-xs text-slate-500">{selectedAgentDetailQuery.data.id}</code>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedAgentDetailQuery.isLoading ? (
              <p className="text-sm text-slate-500">Loading…</p>
            ) : null}
            {selectedAgentDetailQuery.isError ? (
              <p className="text-sm text-rose-200">Error loading this run.</p>
            ) : null}
            {selectedAgentDetailQuery.data?.status === "completed" ? (
              <p className="text-sm font-medium text-emerald-200/90">Success</p>
            ) : null}
            {selectedAgentDetailQuery.data?.status === "failed" ? (
              <p className="text-sm font-medium text-rose-200/90">
                Error{selectedAgentDetailQuery.data.error_message ? `: ${selectedAgentDetailQuery.data.error_message}` : ""}
              </p>
            ) : null}
            {selectedAgentDetailQuery.data && ["running", "queued"].includes(selectedAgentDetailQuery.data.status) ? (
              <p className="text-sm text-slate-300">Loading… (run in progress)</p>
            ) : null}

            <div>
              <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">execution_trace</div>
              <div className="max-h-[min(400px,50vh)] overflow-y-auto rounded-2xl border border-white/10 bg-slate-950/50 p-4">
                {selectedAgentDetailQuery.data && selectedAgentDetailQuery.data.execution_trace.length > 0 ? (
                  <ol className="list-decimal space-y-1.5 pl-4 font-mono text-[11px] leading-relaxed text-slate-300 [word-break:break-word]">
                    {selectedAgentDetailQuery.data.execution_trace.map((line, index) => (
                      <li key={`${index}-${line.slice(0, 48)}`} className="marker:text-slate-600">
                        {line}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm text-slate-500">
                    {selectedAgentDetailQuery.data ? "No trace lines for this run yet." : "Select a run to load trace data."}
                  </p>
                )}
              </div>
            </div>

            {selectedAgentDetailQuery.data ? (
              <ToolInvocationTimeline invocations={selectedAgentDetailQuery.data.tool_invocations ?? []} runStatus={selectedAgentDetailQuery.data.status} />
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <SimpleDialog
        open={ingestionDialogOpen}
        onOpenChange={setIngestionDialogOpen}
        title="Extraction run detail"
        description={selectedIngestionRunId ?? undefined}
        className="w-[min(94vw,960px)] max-h-[min(88vh,720px)] overflow-y-auto"
      >
        {selectedIngestionRun ? (
          <div className="grid gap-4">
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
              <Card className="bg-white/3">
                <CardHeader>
                  <CardTitle>Run summary</CardTitle>
                  <CardDescription>Status, duration, approved keywords, and stored run metadata.</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</div>
                    <div className="mt-2">
                      <StatusPill status={selectedIngestionRun.status} />
                    </div>
                    {selectedIngestionRun.status === "completed" ? (
                      <p className="mt-2 text-sm font-medium text-emerald-200/90">Success</p>
                    ) : null}
                    {selectedIngestionRun.status === "failed" ? (
                      <p className="mt-2 text-sm font-medium text-rose-200/90">Error</p>
                    ) : null}
                    {["running", "queued"].includes(selectedIngestionRun.status) ? (
                      <p className="mt-2 text-sm text-slate-300">Loading…</p>
                    ) : null}
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Duration</div>
                    <div className="mt-2 text-sm font-semibold text-slate-100">
                      {formatDuration(selectedIngestionRun.started_at, selectedIngestionRun.completed_at)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Batch ID</div>
                    <div className="mt-2 break-all text-xs text-slate-200">{selectedIngestionRun.source_batch_id ?? "n/a"}</div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Rows collected</div>
                    <div className="mt-2 text-sm font-semibold text-slate-100">{formatNumber(getRowCount(selectedIngestionRun))}</div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3 sm:col-span-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Approved keywords</div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(selectedIngestionRun.target_keywords ?? []).length > 0 ? (
                        selectedIngestionRun.target_keywords.map((keyword) => (
                          <Badge key={keyword} tone="info" className="normal-case tracking-normal text-[11px]">
                            {keyword}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-xs text-slate-400">No approved keywords stored for this run.</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-white/3">
                <CardHeader>
                  <CardTitle>Diagnostics</CardTitle>
                  <CardDescription>Error message, guardrails, and raw stats JSON.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {selectedIngestionRun.error_message ? (
                    <div className="rounded-xl border border-red-400/20 bg-red-500/8 p-3 text-xs leading-relaxed text-red-100">
                      {selectedIngestionRun.error_message}
                    </div>
                  ) : null}
                  {(selectedIngestionRun.guardrail_flags ?? []).map((flag) => (
                    <div key={flag} className="rounded-xl border border-amber-400/15 bg-amber-500/8 p-3 text-xs leading-relaxed text-amber-100">
                      {flag}
                    </div>
                  ))}
                  {(selectedIngestionRun.recency_support ?? []).map((item) => (
                    <div key={`${item.source}-${item.status}`} className="rounded-xl border border-white/10 bg-slate-950/35 p-3 text-xs leading-relaxed text-slate-300">
                      <div className="font-medium text-slate-100">
                        {sourceLabels[item.source]} · {item.status}
                      </div>
                      <div className="mt-1 text-slate-400">{item.detail}</div>
                    </div>
                  ))}
                  <JsonView title="Run stats" value={selectedIngestionRun.stats} triggerLabel="View stats JSON" />
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {(
                [
                  { key: "sales_data" as const, title: "Sales data", query: salesSampleQuery },
                  { key: "tiktok_photo_posts" as const, title: "TikTok photo posts", query: tiktokSampleQuery },
                  { key: "instagram_posts" as const, title: "Instagram posts", query: instagramSampleQuery },
                ] as const
              ).map((sample) => {
                const limit = batchSampleLimits[sample.key];
                const total = sample.query.data?.total ?? 0;
                const showExpand = limit === BATCH_SAMPLE_PREVIEW && total > BATCH_SAMPLE_PREVIEW;
                const showCollapse = limit > BATCH_SAMPLE_PREVIEW;

                return (
                  <Card key={sample.key} className="bg-white/3">
                    <CardHeader>
                      <CardTitle>{sample.title}</CardTitle>
                      <CardDescription>
                        {sample.query.isLoading
                          ? "Loading…"
                          : total > 0
                            ? `Showing ${formatNumber(sample.query.data?.rows.length ?? 0)} of ${formatNumber(total)} rows for this batch.`
                            : "No rows for this batch."}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {sample.query.isLoading ? (
                        <div className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-xs text-slate-500">Loading sample rows...</div>
                      ) : sample.query.data?.rows.length ? (
                        sample.query.data.rows.map((row, rowIndex) => (
                          <div key={`${sample.key}-${rowIndex}`} className="rounded-lg border border-white/10 bg-slate-950/35 p-2">
                            <pre className="overflow-x-auto text-[11px] leading-snug text-slate-300">{JSON.stringify(row, null, 2)}</pre>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-xs text-slate-500">No rows linked to this source batch.</div>
                      )}
                      {showExpand ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          className="w-full"
                          onClick={() => setBatchSampleLimits((prev) => ({ ...prev, [sample.key]: BATCH_SAMPLE_FULL }))}
                        >
                          Show all ({formatNumber(total)})
                        </Button>
                      ) : null}
                      {showCollapse ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="w-full"
                          onClick={() => setBatchSampleLimits((prev) => ({ ...prev, [sample.key]: BATCH_SAMPLE_PREVIEW }))}
                        >
                          Back to preview ({BATCH_SAMPLE_PREVIEW} rows)
                        </Button>
                      ) : null}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-xs text-slate-500">Loading run detail...</div>
        )}
      </SimpleDialog>
    </div>
  );
}
