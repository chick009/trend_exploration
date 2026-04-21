import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { RunStatusResponse } from "../../api/types";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { categories, markets, sourceLabels, sourceOptions } from "../../lib/options";
import { formatDateTime, formatDuration, formatNumber } from "../../lib/utils";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, DataTable, JsonView, SimpleDialog, StatusPill } from "../../components/ui";

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

export function DataExtractionTab({ workbench }: Props) {
  const { filters, actions, queries, runState } = workbench;
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const recentRunsQuery = useQuery({
    queryKey: ["ingestion-runs", runState.ingestionRunId],
    queryFn: () => api.listIngestionRuns(20, 0),
    refetchInterval: 4000,
  });

  const selectedRunQuery = useQuery({
    queryKey: ["ingestion-run-detail", selectedRunId],
    queryFn: () => api.getIngestionRun(selectedRunId!),
    enabled: dialogOpen && Boolean(selectedRunId),
  });

  const selectedRun = selectedRunQuery.data ?? recentRunsQuery.data?.items.find((item) => item.id === selectedRunId);
  const selectedBatchId = selectedRun?.source_batch_id;

  const rednoteSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "social_posts", selectedBatchId],
    queryFn: () =>
      api.getTableRows("social_posts", {
        limit: 5,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "fetched_at",
        order_dir: "desc",
      }),
    enabled: dialogOpen && Boolean(selectedBatchId),
  });

  const searchSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "search_trends", selectedBatchId],
    queryFn: () =>
      api.getTableRows("search_trends", {
        limit: 5,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "snapshot_date",
        order_dir: "desc",
      }),
    enabled: dialogOpen && Boolean(selectedBatchId),
  });

  const tiktokSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "tiktok_photo_posts", selectedBatchId],
    queryFn: () =>
      api.getTableRows("tiktok_photo_posts", {
        limit: 5,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "fetched_at",
        order_dir: "desc",
      }),
    enabled: dialogOpen && Boolean(selectedBatchId),
  });

  const instagramSampleQuery = useQuery({
    queryKey: ["ingestion-sample", "instagram_posts", selectedBatchId],
    queryFn: () =>
      api.getTableRows("instagram_posts", {
        limit: 5,
        column: "source_batch_id",
        search: selectedBatchId ?? "",
        order_by: "fetched_at",
        order_dir: "desc",
      }),
    enabled: dialogOpen && Boolean(selectedBatchId),
  });

  const failedRuns = recentRunsQuery.data?.items.filter((item) => item.status === "failed" || item.error_message) ?? [];
  const sourceHealth = queries.sourceHealthQuery.data?.sources ?? [];

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader className="gap-3">
          <Badge tone="accent">Data extraction</Badge>
          <CardTitle>Run a new extraction batch</CardTitle>
          <CardDescription>
            Launch a new collection job, tune row limits, and inspect source-level sample rows or error messages afterward.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-[repeat(4,minmax(0,1fr))_220px]">
          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Market</span>
            <select value={filters.market} onChange={(event) => actions.setMarket(event.target.value as typeof filters.market)}>
              {markets.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Category</span>
            <select value={filters.category} onChange={(event) => actions.setCategory(event.target.value as typeof filters.category)}>
              {categories.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Seed terms</span>
            <input type="number" value={filters.maxSeedTerms} min={1} max={20} onChange={(event) => actions.setMaxSeedTerms(Number(event.target.value))} />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Notes per keyword</span>
            <input
              type="number"
              value={filters.maxNotesPerKeyword}
              min={1}
              max={20}
              onChange={(event) => actions.setMaxNotesPerKeyword(Number(event.target.value))}
            />
          </label>

          <div className="flex items-end">
            <Button variant="primary" size="lg" className="w-full" disabled={runState.isBusy} onClick={actions.runExtraction}>
              {runState.isBusy ? "Extraction running..." : "Extract batch"}
            </Button>
          </div>

          <div className="xl:col-span-3">
            <div className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Sources</div>
            <div className="flex flex-wrap gap-2">
              {sourceOptions.map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => actions.toggleSource(source)}
                  className={[
                    "rounded-full border px-3 py-2 text-sm transition",
                    filters.sources.includes(source)
                      ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white"
                      : "border-white/10 bg-white/3 text-slate-300 hover:bg-white/6",
                  ].join(" ")}
                >
                  {sourceLabels[source]}
                </button>
              ))}
            </div>
          </div>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Comment fetches</span>
            <input
              type="number"
              value={filters.maxCommentPostsPerKeyword}
              min={0}
              max={10}
              onChange={(event) => actions.setMaxCommentPostsPerKeyword(Number(event.target.value))}
            />
          </label>

          <label className="space-y-2">
            <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Comments per note</span>
            <input
              type="number"
              value={filters.maxCommentsPerPost}
              min={1}
              max={20}
              onChange={(event) => actions.setMaxCommentsPerPost(Number(event.target.value))}
            />
          </label>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.65fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Recent extraction runs</CardTitle>
            <CardDescription>Review job status, duration, row counts, and inspect individual batches in detail.</CardDescription>
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
                      className="text-blue-200 hover:bg-white/6"
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedRunId(row.id);
                        setDialogOpen(true);
                      }}
                    >
                      View
                    </Button>
                  ),
                },
              ]}
              onRowClick={(row) => {
                setSelectedRunId(row.id);
                setDialogOpen(true);
              }}
            />
          </CardContent>
        </Card>

        <div className="grid gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Source freshness</CardTitle>
              <CardDescription>Latest completed batch and warehouse row counts for each source.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {sourceHealth.map((source) => (
                <div key={source.source} className="rounded-3xl border border-white/10 bg-white/3 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-100">{sourceLabels[source.source as keyof typeof sourceLabels] ?? source.source}</div>
                      <div className="mt-1 text-xs text-slate-500">{formatDateTime(source.latest_completed_at)}</div>
                    </div>
                    <Badge tone="info" className="normal-case tracking-normal text-[12px]">
                      {formatNumber(source.row_count)} rows
                    </Badge>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Error log</CardTitle>
              <CardDescription>Failed runs and extraction warnings surfaced for quick triage.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {failedRuns.length > 0 ? (
                failedRuns.map((run) => (
                  <div key={run.id} className="rounded-3xl border border-red-400/20 bg-red-500/8 p-4">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <StatusPill status={run.status} />
                      <span className="text-xs text-slate-400">{formatDateTime(run.completed_at ?? run.started_at)}</span>
                    </div>
                    <div className="text-sm leading-6 text-red-100">{run.error_message ?? "Guardrail warning present in stats."}</div>
                  </div>
                ))
              ) : (
                <div className="rounded-3xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                  No extraction failures in the recent runs list.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <SimpleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Extraction run detail"
        description={selectedRunId ?? undefined}
        className="w-[min(94vw,1200px)]"
      >
        {selectedRun ? (
          <div className="grid gap-6">
            <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
              <Card className="bg-white/3">
                <CardHeader>
                  <CardTitle>Run summary</CardTitle>
                  <CardDescription>Status, duration, and stored run metadata.</CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Status</div>
                    <div className="mt-3">
                      <StatusPill status={selectedRun.status} />
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Duration</div>
                    <div className="mt-3 text-lg font-semibold text-slate-100">
                      {formatDuration(selectedRun.started_at, selectedRun.completed_at)}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Batch ID</div>
                    <div className="mt-3 break-all text-sm text-slate-200">{selectedRun.source_batch_id ?? "n/a"}</div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Rows collected</div>
                    <div className="mt-3 text-lg font-semibold text-slate-100">{formatNumber(getRowCount(selectedRun))}</div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-white/3">
                <CardHeader>
                  <CardTitle>Diagnostics</CardTitle>
                  <CardDescription>Error message, guardrails, and raw stats JSON.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {selectedRun.error_message ? (
                    <div className="rounded-2xl border border-red-400/20 bg-red-500/8 p-4 text-sm leading-6 text-red-100">
                      {selectedRun.error_message}
                    </div>
                  ) : null}
                  {(selectedRun.guardrail_flags ?? []).map((flag) => (
                    <div key={flag} className="rounded-2xl border border-amber-400/15 bg-amber-500/8 p-4 text-sm leading-6 text-amber-100">
                      {flag}
                    </div>
                  ))}
                  <JsonView title="Run stats" value={selectedRun.stats} triggerLabel="View stats JSON" />
                </CardContent>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
              {[
                { key: "social_posts", title: "RedNote samples", query: rednoteSampleQuery },
                { key: "search_trends", title: "Search trend samples", query: searchSampleQuery },
                { key: "tiktok_photo_posts", title: "TikTok photo samples", query: tiktokSampleQuery },
                { key: "instagram_posts", title: "Instagram samples", query: instagramSampleQuery },
              ].map((sample) => (
                <Card key={sample.key} className="bg-white/3">
                  <CardHeader>
                    <CardTitle>{sample.title}</CardTitle>
                    <CardDescription>Sample rows linked to the selected source batch.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {sample.query.isLoading ? (
                      <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">Loading sample rows...</div>
                    ) : sample.query.data?.rows.length ? (
                      sample.query.data.rows.map((row, rowIndex) => (
                        <div key={`${sample.key}-${rowIndex}`} className="rounded-2xl border border-white/10 bg-slate-950/35 p-4">
                          <pre className="overflow-x-auto text-xs leading-6 text-slate-300">{JSON.stringify(row, null, 2)}</pre>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-2xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">
                        No sample rows for this source batch.
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-3xl border border-dashed border-white/10 px-4 py-8 text-sm text-slate-500">Loading run detail...</div>
        )}
      </SimpleDialog>
    </div>
  );
}
