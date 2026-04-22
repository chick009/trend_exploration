import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { DbTableInfo } from "../../api/types";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, DataTable, JsonView, Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui";
import { formatDateTime, formatNumber } from "../../lib/utils";

/** Tables surfaced in the UI (fixed order). Backend may omit tables that do not exist yet. */
const WAREHOUSE_TABLE_ORDER = ["sales_data", "tiktok_photo_posts", "instagram_posts"] as const;

const PREVIEW_ROW_LIMIT = 5;
const FULL_PAGE_ROW_LIMIT = 100;

const SORTABLE_COLUMNS: Record<string, string[]> = {
  sales_data: ["sku", "brand", "category", "region", "week_start", "units_sold", "revenue", "wow_velocity"],
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
  const [showAllRows, setShowAllRows] = useState(false);

  const tablesQuery = useQuery({
    queryKey: ["db-tables"],
    queryFn: () => api.listTables(),
  });

  const warehouseTables = useMemo(() => {
    const all = tablesQuery.data?.tables ?? [];
    const byName = new Map(all.map((t) => [t.name, t]));
    return WAREHOUSE_TABLE_ORDER.map((name) => byName.get(name)).filter((t): t is DbTableInfo => Boolean(t));
  }, [tablesQuery.data?.tables]);

  useEffect(() => {
    if (warehouseTables.length && (!selectedTable || !warehouseTables.some((t) => t.name === selectedTable))) {
      setSelectedTable(warehouseTables[0].name);
    }
  }, [selectedTable, warehouseTables]);

  useEffect(() => {
    setOffset(0);
  }, [selectedTable, search, column, sortColumn, sortDirection, showAllRows]);

  useEffect(() => {
    setShowAllRows(false);
  }, [selectedTable]);

  const schemaQuery = useQuery({
    queryKey: ["db-schema", selectedTable],
    queryFn: () => api.getTableSchema(selectedTable),
    enabled: Boolean(selectedTable),
  });

  const rowLimit = showAllRows ? FULL_PAGE_ROW_LIMIT : PREVIEW_ROW_LIMIT;
  const rowOffset = showAllRows ? offset : 0;

  const rowsQuery = useQuery({
    queryKey: ["db-rows", selectedTable, search, column, sortColumn, sortDirection, rowOffset, rowLimit],
    queryFn: () =>
      api.getTableRows(selectedTable, {
        limit: rowLimit,
        offset: rowOffset,
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
          <CardDescription>Sales, TikTok photo posts, and Instagram posts stored in SQLite.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!tablesQuery.isLoading && warehouseTables.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-sm text-slate-500">
              None of the expected warehouse tables are present in this database yet.
            </p>
          ) : null}
          {warehouseTables.map((table) => (
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
            Preview five rows by default, then load the full result set (up to {FULL_PAGE_ROW_LIMIT} rows per request) when you need more detail.
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
                  {showAllRows ? (
                    (() => {
                      const slice = rowsQuery.data?.rows.length ?? 0;
                      const total = rowsQuery.data?.total ?? 0;
                      if (slice === 0) {
                        return <>No rows match the current filter.</>;
                      }
                      return (
                        <>
                          Showing {formatNumber(rowOffset + 1)}–{formatNumber(rowOffset + slice)} of {formatNumber(total)} rows
                        </>
                      );
                    })()
                  ) : (
                    <>
                      Preview: {formatNumber(rowsQuery.data?.rows.length ?? 0)} of {formatNumber(rowsQuery.data?.total ?? 0)} rows
                    </>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {!showAllRows && (rowsQuery.data?.total ?? 0) > PREVIEW_ROW_LIMIT ? (
                    <Button variant="primary" size="sm" onClick={() => setShowAllRows(true)}>
                      Show all ({formatNumber(rowsQuery.data?.total ?? 0)})
                    </Button>
                  ) : null}
                  {showAllRows ? (
                    <>
                      <Button variant="ghost" size="sm" onClick={() => setShowAllRows(false)}>
                        Back to preview
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={rowOffset === 0}
                        onClick={() => setOffset((current) => Math.max(0, current - FULL_PAGE_ROW_LIMIT))}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={(rowsQuery.data?.rows.length ?? 0) < FULL_PAGE_ROW_LIMIT}
                        onClick={() => setOffset((current) => current + FULL_PAGE_ROW_LIMIT)}
                      >
                        Next
                      </Button>
                    </>
                  ) : null}
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
