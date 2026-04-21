import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, DataTable, JsonView, Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui";
import { formatDateTime, formatNumber } from "../../lib/utils";

const SORTABLE_COLUMNS: Record<string, string[]> = {
  entity_dictionary: ["canonical_term", "entity_type", "hb_category", "origin_market"],
  search_trends: ["keyword", "geo", "snapshot_date", "wow_delta", "index_value", "processed_at", "last_updated", "source_batch_id"],
  social_posts: ["id", "post_date", "liked_count", "comment_count", "share_count", "engagement_score", "positivity_score", "processed_at", "fetched_at", "source_batch_id"],
  sales_data: ["sku", "brand", "category", "region", "week_start", "units_sold", "revenue", "wow_velocity"],
  trend_exploration: ["trend_id", "canonical_term", "entity_type", "hb_category", "virality_score", "confidence_tier", "market", "analysis_date", "status"],
  ingestion_runs: ["id", "status", "market", "category", "recent_days", "started_at", "completed_at", "source_batch_id"],
  analysis_runs: ["id", "status", "market", "category", "recency_days", "analysis_mode", "started_at", "completed_at"],
  tiktok_photo_posts: ["id", "search_keyword", "create_time", "create_time_unix", "is_ad", "fetched_at", "source_batch_id"],
  instagram_posts: ["post_id", "search_keyword", "code", "username", "likes", "comments", "views", "created_at", "fetched_at", "source_batch_id"],
};

function looksLikeJson(value: unknown) {
  if (typeof value !== "string") {
    return false;
  }
  const trimmed = value.trim();
  return (trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"));
}

export function SqlDatabaseTab() {
  const [selectedTable, setSelectedTable] = useState<string>("");
  const [search, setSearch] = useState("");
  const [column, setColumn] = useState("");
  const [sortColumn, setSortColumn] = useState<string>("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  const tablesQuery = useQuery({
    queryKey: ["db-tables"],
    queryFn: () => api.listTables(),
  });

  useEffect(() => {
    if (!selectedTable && tablesQuery.data?.tables.length) {
      setSelectedTable(tablesQuery.data.tables[0].name);
    }
  }, [selectedTable, tablesQuery.data?.tables]);

  useEffect(() => {
    setOffset(0);
  }, [selectedTable, search, column, sortColumn, sortDirection]);

  const schemaQuery = useQuery({
    queryKey: ["db-schema", selectedTable],
    queryFn: () => api.getTableSchema(selectedTable),
    enabled: Boolean(selectedTable),
  });

  const rowsQuery = useQuery({
    queryKey: ["db-rows", selectedTable, search, column, sortColumn, sortDirection, offset],
    queryFn: () =>
      api.getTableRows(selectedTable, {
        limit: 25,
        offset,
        search: search || undefined,
        column: column || undefined,
        order_by: sortColumn || undefined,
        order_dir: sortDirection,
      }),
    enabled: Boolean(selectedTable),
  });

  const schemaColumns = schemaQuery.data?.columns ?? [];
  const searchableColumns = schemaColumns.map((item) => item.name);
  const sortableColumns = SORTABLE_COLUMNS[selectedTable] ?? [];

  const tableColumns = useMemo(
    () =>
      (rowsQuery.data?.columns ?? []).map((name) => ({
        key: name,
        label: name,
        sortable: sortableColumns.includes(name),
        render: (row: Record<string, unknown>) => {
          const value = row[name];
          if (looksLikeJson(value)) {
            return <JsonView title={`${selectedTable}.${name}`} value={JSON.parse(String(value))} triggerLabel="View JSON" />;
          }
          if (typeof value === "string" && value.length > 120) {
            return <div className="max-w-[360px] truncate">{value}</div>;
          }
          return <span>{String(value ?? "")}</span>;
        },
      })),
    [rowsQuery.data?.columns, selectedTable, sortableColumns],
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="h-fit xl:sticky xl:top-28">
        <CardHeader>
          <CardTitle>Warehouse tables</CardTitle>
          <CardDescription>Browse the read-only SQLite tables backing the dashboard and extraction views.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {tablesQuery.data?.tables.map((table) => (
            <button
              key={table.name}
              type="button"
              onClick={() => {
                setSelectedTable(table.name);
                setColumn("");
                setSortColumn("");
              }}
              className={[
                "w-full rounded-3xl border p-4 text-left transition",
                selectedTable === table.name
                  ? "border-blue-400/30 bg-blue-500/12"
                  : "border-white/10 bg-white/3 hover:bg-white/6",
              ].join(" ")}
            >
              <div className="text-sm font-semibold text-slate-100">{table.name}</div>
              <div className="mt-1 text-sm leading-6 text-slate-400">{table.description}</div>
              <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-500">
                <span>{formatNumber(table.row_count)} rows</span>
                <span>{formatDateTime(table.last_updated)}</span>
              </div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-3">
          <CardTitle>{selectedTable || "Select a table"}</CardTitle>
          <CardDescription>
            Inspect schema metadata and query paginated rows through the backend whitelist-protected DB browser API.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="rows" className="space-y-6">
            <TabsList className="max-w-sm">
              <TabsTrigger value="rows">Rows</TabsTrigger>
              <TabsTrigger value="schema">Schema</TabsTrigger>
            </TabsList>

            <TabsContent value="rows" className="space-y-5">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_200px_160px]">
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Search</span>
                  <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search rows..." />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Column scope</span>
                  <select value={column} onChange={(event) => setColumn(event.target.value)}>
                    <option value="">All searchable columns</option>
                    {searchableColumns.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-[0.14em] text-slate-500">Sort</span>
                  <select
                    value={sortColumn}
                    onChange={(event) => {
                      setSortColumn(event.target.value);
                      setSortDirection("desc");
                    }}
                  >
                    <option value="">Default</option>
                    {sortableColumns.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <DataTable
                loading={rowsQuery.isLoading}
                rows={rowsQuery.data?.rows ?? []}
                rowKey={(row, index) => String(row.id ?? row.post_id ?? `${selectedTable}-${index}`)}
                columns={tableColumns}
                emptyState={
                  <div className="rounded-3xl border border-dashed border-white/10 px-6 py-12 text-center text-sm text-slate-500">
                    No rows match the current filter.
                  </div>
                }
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onSort={(key) => {
                  if (!sortableColumns.includes(key)) {
                    return;
                  }
                  if (sortColumn === key) {
                    setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
                    return;
                  }
                  setSortColumn(key);
                  setSortDirection("desc");
                }}
              />

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-slate-400">
                  Showing {formatNumber((rowsQuery.data?.rows.length ?? 0) + offset)} of {formatNumber(rowsQuery.data?.total ?? 0)} rows
                </div>
                <div className="flex gap-3">
                  <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset((current) => Math.max(0, current - 25))}>
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={(rowsQuery.data?.rows.length ?? 0) < 25}
                    onClick={() => setOffset((current) => current + 25)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="schema">
              <DataTable
                loading={schemaQuery.isLoading}
                rows={schemaColumns}
                rowKey={(row) => row.name}
                columns={[
                  { key: "name", label: "Column" },
                  { key: "data_type", label: "Type" },
                  {
                    key: "nullable",
                    label: "Nullable",
                    render: (row) => (row.nullable ? "Yes" : "No"),
                  },
                  {
                    key: "is_primary_key",
                    label: "Primary key",
                    render: (row) => (row.is_primary_key ? "Yes" : "No"),
                  },
                  {
                    key: "is_indexed",
                    label: "Indexed",
                    render: (row) => (row.is_indexed ? "Yes" : "No"),
                  },
                ]}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
