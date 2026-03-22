"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, Table2 } from "lucide-react";

type TableInfo = {
  name: string;
  rowCount: number;
};

type TableData = {
  columns: string[];
  rows: Record<string, unknown>[];
  total: number;
};

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

export default function DatabasePage() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableData, setTableData] = useState<TableData | null>(null);
  const [loadingTables, setLoadingTables] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [offset, setOffset] = useState(0);
  const limit = 100;

  useEffect(() => {
    async function fetchTables() {
      setLoadingTables(true);
      try {
        const res = await fetch(`${BACKEND_URL}/api/database/tables`);
        const data: TableInfo[] = await res.json();
        setTables(data);
        if (data.length > 0) {
          setSelectedTable(data[0].name);
        }
      } catch {
        setTables([]);
      } finally {
        setLoadingTables(false);
      }
    }
    void fetchTables();
  }, []);

  const fetchTableData = useCallback(
    async (tableName: string, newOffset: number) => {
      setLoadingData(true);
      try {
        const res = await fetch(
          `${BACKEND_URL}/api/database/tables/${tableName}?limit=${limit}&offset=${newOffset}`
        );
        const data: TableData = await res.json();
        if (newOffset === 0) {
          setTableData(data);
        } else {
          setTableData((prev) =>
            prev
              ? { ...data, rows: [...prev.rows, ...data.rows] }
              : data
          );
        }
      } catch {
        if (newOffset === 0) setTableData(null);
      } finally {
        setLoadingData(false);
      }
    },
    []
  );

  useEffect(() => {
    if (selectedTable) {
      setOffset(0);
      void fetchTableData(selectedTable, 0);
    }
  }, [selectedTable, fetchTableData]);

  function handleLoadMore() {
    if (!selectedTable) return;
    const newOffset = offset + limit;
    setOffset(newOffset);
    void fetchTableData(selectedTable, newOffset);
  }

  const selectedInfo = tables.find((t) => t.name === selectedTable);
  const hasMore =
    tableData && selectedInfo
      ? tableData.rows.length < selectedInfo.rowCount
      : false;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b border-[var(--border)] px-6 py-4">
        <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[color:color-mix(in_srgb,var(--accent)_15%,transparent)] text-[var(--accent)]">
          <Database size={20} />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-[var(--foreground)]">
            Database Explorer
          </h1>
          <p className="text-xs text-[var(--muted)]">
            Browse the e-commerce database tables
          </p>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Table list panel */}
        <div className="flex w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--card)] md:w-64">
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
            <Table2 size={14} className="text-[var(--accent)]" />
            <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
              Tables
            </span>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {loadingTables
              ? Array.from({ length: 6 }, (_, i) => (
                  <div
                    key={i}
                    className="mb-1.5 h-10 animate-pulse rounded-xl bg-[color:color-mix(in_srgb,var(--foreground)_6%,transparent)]"
                  />
                ))
              : tables.map((table) => {
                  const isActive = selectedTable === table.name;
                  return (
                    <button
                      key={table.name}
                      type="button"
                      onClick={() => setSelectedTable(table.name)}
                      className={`mb-1 flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-sm transition ${
                        isActive
                          ? "bg-[color:color-mix(in_srgb,var(--accent)_15%,transparent)] font-medium text-[var(--accent)]"
                          : "text-[var(--muted)] hover:bg-[color:color-mix(in_srgb,var(--foreground)_5%,transparent)] hover:text-[var(--foreground)]"
                      }`}
                    >
                      <span className="truncate">{table.name}</span>
                      <span
                        className={`ml-2 shrink-0 rounded-lg px-2 py-0.5 text-[10px] font-semibold ${
                          isActive
                            ? "bg-[var(--accent)] text-white"
                            : "bg-[color:color-mix(in_srgb,var(--foreground)_8%,transparent)] text-[var(--muted)]"
                        }`}
                      >
                        {table.rowCount}
                      </span>
                    </button>
                  );
                })}
          </div>
        </div>

        {/* Main data area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {loadingData && !tableData ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2
                size={24}
                className="animate-spin text-[var(--accent)]"
              />
            </div>
          ) : tableData ? (
            <>
              <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-3">
                <h2 className="text-sm font-semibold text-[var(--foreground)]">
                  {selectedTable}
                </h2>
                <span className="text-xs text-[var(--muted)]">
                  {tableData.rows.length} of {selectedInfo?.rowCount ?? "?"}{" "}
                  rows
                </span>
              </div>
              <div className="flex-1 overflow-auto">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 z-10">
                    <tr>
                      {tableData.columns.map((col) => (
                        <th
                          key={col}
                          className="border-b border-[var(--border)] bg-[color:color-mix(in_srgb,var(--accent)_8%,var(--card))] px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-[var(--accent)]"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableData.rows.map((row, i) => (
                      <tr
                        key={i}
                        className="border-b border-[var(--border)] transition-colors last:border-0 hover:bg-[color:color-mix(in_srgb,var(--foreground)_3%,transparent)]"
                      >
                        {tableData.columns.map((col) => (
                          <td
                            key={col}
                            className="max-w-xs truncate px-4 py-2.5 text-sm text-[var(--foreground)]"
                          >
                            {row[col] == null
                              ? ""
                              : String(row[col])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {hasMore && (
                <div className="flex shrink-0 justify-center border-t border-[var(--border)] px-6 py-3">
                  <button
                    type="button"
                    onClick={handleLoadMore}
                    disabled={loadingData}
                    className="inline-flex items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] px-5 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-50"
                  >
                    {loadingData ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : null}
                    Load more
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-sm text-[var(--muted)]">
              Select a table to view its data.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
