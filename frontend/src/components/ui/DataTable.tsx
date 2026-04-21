import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

export type DataColumn<Row> = {
  key: keyof Row | string;
  label: string;
  render?: (row: Row) => ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  headerClassName?: string;
  sortable?: boolean;
};

type Props<Row> = {
  columns: Array<DataColumn<Row>>;
  rows: Row[];
  rowKey: (row: Row, index: number) => string;
  onRowClick?: (row: Row) => void;
  emptyState?: ReactNode;
  loading?: boolean;
  sortColumn?: string | null;
  sortDirection?: "asc" | "desc";
  onSort?: (column: string) => void;
};

const alignmentClasses = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
} as const;

export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onRowClick,
  emptyState,
  loading,
  sortColumn,
  sortDirection = "desc",
  onSort,
}: Props<Row>) {
  const empty = emptyState ?? (
    <div className="rounded-3xl border border-dashed border-white/10 bg-white/3 px-6 py-12 text-center text-sm text-slate-400">
      No rows to display.
    </div>
  );

  if (!loading && rows.length === 0) {
    return <>{empty}</>;
  }

  return (
    <div className="overflow-hidden rounded-[24px] border border-white/10 bg-slate-950/35">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead className="bg-white/4 text-slate-400">
            <tr>
              {columns.map((column) => {
                const isSorted = sortColumn === String(column.key);
                const Icon = !column.sortable
                  ? null
                  : isSorted
                    ? sortDirection === "asc"
                      ? ArrowUp
                      : ArrowDown
                    : ChevronsUpDown;

                return (
                  <th
                    key={String(column.key)}
                    className={cn(
                      "border-b border-white/10 px-4 py-3 font-medium",
                      alignmentClasses[column.align ?? "left"],
                      column.headerClassName,
                    )}
                  >
                    {column.sortable ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-2 rounded-full px-2 py-1 transition hover:bg-white/5"
                        onClick={() => onSort?.(String(column.key))}
                      >
                        <span>{column.label}</span>
                        {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
                      </button>
                    ) : (
                      column.label
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 5 }).map((_, rowIndex) => (
                  <tr key={`skeleton-${rowIndex}`} className="border-b border-white/5 last:border-b-0">
                    {columns.map((column) => (
                      <td key={`${String(column.key)}-${rowIndex}`} className="px-4 py-3">
                        <div className="h-4 animate-pulse rounded-full bg-white/8" />
                      </td>
                    ))}
                  </tr>
                ))
              : rows.map((row, index) => (
                  <tr
                    key={rowKey(row, index)}
                    className={cn(
                      "border-b border-white/5 last:border-b-0",
                      onRowClick ? "cursor-pointer transition hover:bg-white/4" : "",
                    )}
                    onClick={() => onRowClick?.(row)}
                  >
                    {columns.map((column) => (
                      <td
                        key={String(column.key)}
                        className={cn(
                          "px-4 py-3 align-top text-slate-100",
                          alignmentClasses[column.align ?? "left"],
                          column.className,
                        )}
                      >
                        {column.render ? column.render(row) : String((row as Record<string, unknown>)[String(column.key)] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
