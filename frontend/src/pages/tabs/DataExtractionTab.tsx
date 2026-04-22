import { categories, markets, sourceLabels, extractionSourceOptions } from "../../lib/options";
import type { InstagramFeedType } from "../../api/types";
import type { TrendWorkbench } from "../../hooks/useTrendWorkbench";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui";
import { formatDateTime, formatNumber } from "../../lib/utils";

type Props = {
  workbench: TrendWorkbench;
};

const EXTRACTION_HEALTH_SOURCES = ["google_trends", "tiktok", "instagram"] as const;

function CurrentIngestionStatusLine({ workbench }: { workbench: TrendWorkbench }) {
  const { queries, runState, mutations } = workbench;
  const run = queries.ingestionQuery.data;
  const starting = mutations.createIngestionMutation.isPending;
  const hasRunId = Boolean(runState.ingestionRunId);
  const inFlight =
    runState.ingestionRunId &&
    (run?.status === "running" || run?.status === "queued" || (queries.ingestionQuery.isPending && !run));

  if (starting || inFlight) {
    return <span className="text-xs font-medium text-slate-200">Loading…</span>;
  }
  if (!hasRunId) {
    return <span className="text-xs text-slate-500">No extraction run yet.</span>;
  }
  if (run?.status === "completed") {
    return <span className="text-xs font-medium text-emerald-200/90">Success</span>;
  }
  if (run?.status === "failed") {
    const msg = run.error_message?.trim();
    return (
      <span className="text-xs font-medium text-rose-200/90" title={msg ?? undefined}>
        Error{msg ? `: ${msg.length > 120 ? `${msg.slice(0, 120)}…` : msg}` : ""}
      </span>
    );
  }
  return <span className="text-xs text-slate-500">Idle</span>;
}

function ExtractionFreshnessInline({ workbench }: { workbench: TrendWorkbench }) {
  const health = workbench.queries.sourceHealthQuery.data?.sources ?? [];
  const rows = health.filter((item) => EXTRACTION_HEALTH_SOURCES.includes(item.source as (typeof EXTRACTION_HEALTH_SOURCES)[number]));

  if (workbench.queries.sourceHealthQuery.isLoading) {
    return <span className="text-xs text-slate-500">Freshness loading…</span>;
  }
  if (rows.length === 0) {
    return <span className="text-xs text-slate-500">No freshness data.</span>;
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-400">
      {rows.map((item) => (
        <span key={item.source} className="whitespace-nowrap">
          <span className="font-medium text-slate-300">{sourceLabels[item.source as keyof typeof sourceLabels] ?? item.source}</span>
          {" · "}
          {formatNumber(item.row_count)} rows
          {item.latest_completed_at ? (
            <>
              {" · "}
              <span className="text-slate-500">{formatDateTime(item.latest_completed_at)}</span>
            </>
          ) : null}
        </span>
      ))}
    </div>
  );
}

export function DataExtractionTab({ workbench }: Props) {
  const { filters, keywordState, actions, runState, mutations } = workbench;
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
            {filters.sources.includes("google_trends") ? (
              <div className="min-w-[200px] flex-1 space-y-1">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Google Trends recency</span>
                <p className="text-[10px] leading-snug text-slate-500">Applies only to Google Trends (SerpAPI window).</p>
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
                          : "border-white/10 bg-white/3 text-slate-200 hover:bg-slate-800/60 hover:text-slate-100",
                      ].join(" ")}
                    >
                      {days}d
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
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
              {extractionSourceOptions.map((source) => (
                <button
                  key={source}
                  type="button"
                  onClick={() => actions.toggleSource(source)}
                  className={[
                    "rounded-full border px-2.5 py-1 text-xs font-medium transition md:text-[13px]",
                    filters.sources.includes(source)
                      ? "border-transparent bg-gradient-to-r from-blue-600 to-violet-500 text-white"
                      : "border-white/10 bg-white/3 text-slate-200 hover:bg-slate-800/60 hover:text-slate-100",
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
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Uses each approved keyword via TikHub photo search.</p>
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
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">Uses each approved keyword; choose how results are ranked.</p>
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

          </div>

          <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
            <div className="rounded-xl border border-white/10 bg-white/3 p-3">
              <div>
                <div className="text-xs font-semibold text-slate-200">Target keywords</div>
                <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                  Generate a draft list from the selected market and category, then edit it before approval. Use one keyword per line.
                </p>
              </div>

              <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-stretch lg:justify-between">
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

                <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 border-white/10 lg:border-l lg:pl-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Latest extraction</span>
                    <CurrentIngestionStatusLine workbench={workbench} />
                  </div>
                  <div>
                    <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500">Source freshness</div>
                    <div className="mt-0.5">
                      <ExtractionFreshnessInline workbench={workbench} />
                    </div>
                  </div>
                  <a
                    href="#execution_log"
                    className="text-[11px] text-blue-200/95 underline decoration-blue-200/30 underline-offset-2 hover:decoration-blue-200/80"
                  >
                    Open execution log
                  </a>
                </div>
              </div>

              <label className="mt-3 block space-y-1">
                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Approved keyword list</span>
                <textarea
                  value={keywordState.keywordText}
                  onChange={(event) => actions.setTargetKeywordText(event.target.value)}
                  rows={8}
                  className="min-h-[180px] w-full rounded-xl border border-white/10 bg-slate-950/35 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-blue-400/40"
                  placeholder="Generate suggestions, then edit one keyword per line."
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
              <div className="text-xs font-semibold text-slate-200">Google Trends recency</div>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                After you suggest keywords, we show how the selected day window applies to Google Trends only.
              </p>
              <div className="mt-3 space-y-2">
                {filters.sources.includes("google_trends") ? (
                  (() => {
                    const googleOnly = keywordState.recencySupport.filter((item) => item.source === "google_trends");
                    return googleOnly.length > 0 ? (
                      googleOnly.map((item) => (
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
                        Generate suggestions to see recency guidance for Google Trends.
                      </div>
                    );
                  })()
                ) : (
                  <div className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-xs text-slate-500">
                    Enable Google Trends to use the recency window for search signals.
                  </div>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
