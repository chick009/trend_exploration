import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { InstagramFeedType, RunStatusResponse } from "../../api/types";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import { categories, markets, sourceLabels, sourceOptions } from "../../lib/options";
import { formatDateTime, formatDuration, formatNumber } from "../../lib/utils";
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

export function DataExtractionTab({ workbench }: Props) {
  const { filters, keywordState, actions, queries, runState, mutations } = workbench;
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [batchSampleLimits, setBatchSampleLimits] = useState<Record<BatchSampleTable, number>>({
    sales_data: BATCH_SAMPLE_PREVIEW,
    tiktok_photo_posts: BATCH_SAMPLE_PREVIEW,
    instagram_posts: BATCH_SAMPLE_PREVIEW,
  });

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

  useEffect(() => {
    if (dialogOpen && selectedBatchId) {
      setBatchSampleLimits({
        sales_data: BATCH_SAMPLE_PREVIEW,
        tiktok_photo_posts: BATCH_SAMPLE_PREVIEW,
        instagram_posts: BATCH_SAMPLE_PREVIEW,
      });
    }
  }, [dialogOpen, selectedBatchId]);

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
    enabled: dialogOpen && Boolean(selectedBatchId),
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
    enabled: dialogOpen && Boolean(selectedBatchId),
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
    enabled: dialogOpen && Boolean(selectedBatchId),
  });

  const failedRuns = recentRunsQuery.data?.items.filter((item) => item.status === "failed" || item.error_message) ?? [];
  const sourceHealth = queries.sourceHealthQuery.data?.sources ?? [];
  const suggestionRows = keywordState.keywordSuggestions?.suggestions ?? [];

  return (
    <div className="grid gap-4">
      <Card>
        <CardHeader className="gap-2">
          <Badge tone="accent">Data extraction</Badge>
          <CardTitle>Run a new extraction batch</CardTitle>
          <CardDescription>
            Configure the sources first, generate target keywords from market and category, then approve the edited list before extraction starts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end">
            <label className="min-w-[140px] flex-1 space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Market</span>
              <select value={filters.market} onChange={(event) => actions.setMarket(event.target.value as typeof filters.market)}>
                {markets.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-[160px] flex-1 space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Category</span>
              <select value={filters.category} onChange={(event) => actions.setCategory(event.target.value as typeof filters.category)}>
                {categories.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <div className="min-w-[200px] flex-1 space-y-1">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Recency</span>
              <div className="flex flex-wrap gap-1.5">
                {[7, 14, 30].map((days) => (
                  <button
                    key={days}
                    type="button"
                    onClick={() => actions.setRecentDays(days)}
                    className={[
                      "rounded-lg border px-2.5 py-1 text-xs font-medium transition",
                      filters.recentDays === days
                        ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white"
                        : "border-white/10 bg-white/3 text-slate-300 hover:bg-white/6",
                    ].join(" ")}
                  >
                    {days}d
                  </button>
                ))}
              </div>
            </div>
            <label className="w-full min-w-[120px] max-w-[160px] space-y-1 sm:w-auto">
              <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Keyword count</span>
              <input
                type="number"
                value={filters.maxTargetKeywords}
                min={1}
                max={20}
                onChange={(event) => actions.setMaxTargetKeywords(Number(event.target.value))}
              />
            </label>
          </div>

          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Sources</div>
            <div className="flex flex-wrap gap-1.5">
              {sourceOptions.map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => actions.toggleSource(source)}
                  className={[
                    "rounded-full border px-2.5 py-1 text-xs font-medium transition md:text-[13px]",
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

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {filters.sources.includes("google_trends") ? (
              <div className="rounded-xl border border-white/10 bg-white/3 p-3">
                <div className="text-xs font-semibold text-slate-200">Google Trends</div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Honors recency ({filters.recentDays} days) and queries each approved keyword through SerpAPI.
                </p>
              </div>
            ) : null}

            {filters.sources.includes("tiktok") ? (
              <div className="rounded-xl border border-white/10 bg-white/3 p-3">
                <div className="text-xs font-semibold text-slate-200">TikTok photos</div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Uses each approved keyword. Recency is informational only because TikHub does not expose a true date window.
                </p>
                <label className="mt-3 block space-y-1">
                  <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Photos per keyword</span>
                  <input
                    type="number"
                    value={filters.tiktokPhotosPerKeyword}
                    min={1}
                    max={50}
                    onChange={(event) => actions.setTiktokPhotosPerKeyword(Number(event.target.value))}
                  />
                </label>
              </div>
            ) : null}

            {filters.sources.includes("instagram") ? (
              <div className="rounded-xl border border-white/10 bg-white/3 p-3">
                <div className="text-xs font-semibold text-slate-200">Instagram hashtag</div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Uses each approved keyword. The feed can rank by recent posts, but it does not enforce an exact day range.
                </p>
                <label className="mt-3 block space-y-1">
                  <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Feed ranking</span>
                  <select
                    value={filters.instagramFeedType}
                    onChange={(event) => actions.setInstagramFeedType(event.target.value as InstagramFeedType)}
                  >
                    <option value="top">Top posts</option>
                    <option value="recent">Recent posts</option>
                  </select>
                </label>
              </div>
            ) : null}

            {filters.sources.includes("sales") ? (
              <div className="rounded-xl border border-white/10 bg-white/3 p-3">
                <div className="text-xs font-semibold text-slate-200">Sales seed</div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Refreshes the local sales seed table only. This source runs without target keywords.
                </p>
              </div>
            ) : null}
          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
            <div className="rounded-xl border border-white/10 bg-white/3 p-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="text-xs font-semibold text-slate-200">Target keywords</div>
                  <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                    Generate a draft list from the selected market and category, then edit it before approval. Use one keyword per line.
                  </p>
                </div>
                <div className="flex w-full flex-col gap-2 lg:w-auto lg:min-w-[180px]">
                  <Button variant="secondary" size="md" className="w-full" disabled={runState.isBusy} onClick={actions.requestKeywordSuggestions}>
                    {mutations.suggestKeywordsMutation.isPending ? "Generating…" : "Suggest keywords"}
                  </Button>
                  <Button
                    variant="secondary"
                    size="md"
                    className="w-full"
                    disabled={runState.isBusy || (keywordState.requiresKeywords && keywordState.targetKeywords.length === 0)}
                    onClick={actions.approveTargetKeywords}
                  >
                    {keywordState.keywordsApproved ? "Keywords approved" : "Approve keywords"}
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    className="w-full"
                    disabled={runState.isBusy || !keywordState.keywordsApproved}
                    onClick={actions.runExtraction}
                  >
                    {runState.isBusy ? "Running…" : "Extract batch"}
                  </Button>
                </div>
              </div>

              <label className="mt-3 block space-y-1">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Approved keyword list</span>
                <textarea
                  value={keywordState.keywordText}
                  onChange={(event) => actions.setTargetKeywordText(event.target.value)}
                  rows={8}
                  className="min-h-[180px] w-full rounded-xl border border-white/10 bg-slate-950/35 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-blue-400/40"
                  placeholder={keywordState.requiresKeywords ? "Generate suggestions, then edit one keyword per line." : "Sales-only runs do not require keywords."}
                />
              </label>

              {keywordState.keywordApprovalStale ? (
                <div className="mt-3 rounded-xl border border-amber-400/15 bg-amber-500/8 p-3 text-xs leading-relaxed text-amber-100">
                  Extraction settings changed after approval. Review the list and approve again before running.
                </div>
              ) : null}

              {!keywordState.requiresKeywords ? (
                <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/35 p-3 text-xs leading-relaxed text-slate-400">
                  The selected sources do not require target keywords, so you can approve and run immediately.
                </div>
              ) : null}

              {keywordState.keywordGuardrailFlags.map((flag) => (
                <div key={flag} className="mt-3 rounded-xl border border-amber-400/15 bg-amber-500/8 p-3 text-xs leading-relaxed text-amber-100">
                  {flag}
                </div>
              ))}

              {suggestionRows.length > 0 ? (
                <div className="mt-4 grid gap-2">
                  <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Latest suggestions</div>
                  {suggestionRows.map((suggestion) => (
                    <div key={suggestion.keyword} className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                      <div className="text-sm font-medium text-slate-100">{suggestion.keyword}</div>
                      {suggestion.rationale ? <div className="mt-1 text-xs leading-relaxed text-slate-400">{suggestion.rationale}</div> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            <div className="rounded-xl border border-white/10 bg-white/3 p-3">
              <div className="text-xs font-semibold text-slate-200">Recency support</div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                Recency is source-aware. Suggest keywords to preview how each selected source interprets the current recency setting.
              </p>
              <div className="mt-3 space-y-2">
                {keywordState.recencySupport.length > 0 ? (
                  keywordState.recencySupport.map((item) => (
                    <div key={item.source} className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-sm font-medium text-slate-100">{sourceLabels[item.source]}</div>
                        <Badge
                          tone={item.status === "supported" ? "success" : item.status === "partial" ? "info" : "warning"}
                          className="normal-case tracking-normal text-[11px]"
                        >
                          {item.status}
                        </Badge>
                      </div>
                      <div className="mt-1 text-xs leading-relaxed text-slate-400">{item.detail}</div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-xs text-slate-500">
                    Generate suggestions to load per-source recency guidance.
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.65fr)]">
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

        <div className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Source freshness</CardTitle>
              <CardDescription>Latest completed batch and warehouse row counts for each source.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {sourceHealth.map((source) => (
                <div key={source.source} className="rounded-xl border border-white/10 bg-white/3 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-xs font-medium text-slate-100">{sourceLabels[source.source as keyof typeof sourceLabels] ?? source.source}</div>
                      <div className="mt-0.5 text-[11px] text-slate-500">{formatDateTime(source.latest_completed_at)}</div>
                    </div>
                    <Badge tone="info" className="normal-case tracking-normal text-[11px]">
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
            <CardContent className="space-y-2">
              {failedRuns.length > 0 ? (
                failedRuns.map((run) => (
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
        </div>
      </div>

      <SimpleDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Extraction run detail"
        description={selectedRunId ?? undefined}
        className="w-[min(94vw,960px)] max-h-[min(88vh,720px)] overflow-y-auto"
      >
        {selectedRun ? (
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
                      <StatusPill status={selectedRun.status} />
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Duration</div>
                    <div className="mt-2 text-sm font-semibold text-slate-100">
                      {formatDuration(selectedRun.started_at, selectedRun.completed_at)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Batch ID</div>
                    <div className="mt-2 break-all text-xs text-slate-200">{selectedRun.source_batch_id ?? "n/a"}</div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Rows collected</div>
                    <div className="mt-2 text-sm font-semibold text-slate-100">{formatNumber(getRowCount(selectedRun))}</div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-slate-950/35 p-3 sm:col-span-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-500">Approved keywords</div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(selectedRun.target_keywords ?? []).length > 0 ? (
                        selectedRun.target_keywords.map((keyword) => (
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
                  {selectedRun.error_message ? (
                    <div className="rounded-xl border border-red-400/20 bg-red-500/8 p-3 text-xs leading-relaxed text-red-100">
                      {selectedRun.error_message}
                    </div>
                  ) : null}
                  {(selectedRun.guardrail_flags ?? []).map((flag) => (
                    <div key={flag} className="rounded-xl border border-amber-400/15 bg-amber-500/8 p-3 text-xs leading-relaxed text-amber-100">
                      {flag}
                    </div>
                  ))}
                  {(selectedRun.recency_support ?? []).map((item) => (
                    <div key={`${item.source}-${item.status}`} className="rounded-xl border border-white/10 bg-slate-950/35 p-3 text-xs leading-relaxed text-slate-300">
                      <div className="font-medium text-slate-100">
                        {sourceLabels[item.source]} · {item.status}
                      </div>
                      <div className="mt-1 text-slate-400">{item.detail}</div>
                    </div>
                  ))}
                  <JsonView title="Run stats" value={selectedRun.stats} triggerLabel="View stats JSON" />
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
                        <div className="rounded-lg border border-dashed border-white/10 px-3 py-5 text-xs text-slate-500">
                          No rows linked to this source batch.
                        </div>
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
