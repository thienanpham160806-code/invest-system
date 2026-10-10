"use client";
// Bảng dữ liệu dùng chung (TanStack Table + Virtual). SortTable trong ui.tsx là lớp mỏng gọi bảng này,
// nên mọi bảng cũ có: header & cột đầu dính, kéo đổi độ rộng/thứ tự cột, ẩn/hiện cột, mật độ,
// sắp xếp nhiều cột (Shift+click), lọc theo cột, ảo hoá > 500 dòng, xuất CSV, lưu cấu hình cột.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  type ColumnDef, type ColumnFiltersState, type ColumnOrderState, type ColumnSizingState, type FilterFn,
  flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, type SortingState, useReactTable,
  type VisibilityState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { downloadCSV, toCSV } from "@/lib/api";

export type Col<T> = { key: string; label: string; render?: (r: T) => ReactNode; num?: boolean; sortValue?: (r: T) => any; title?: string };

export type DataTableProps<T> = {
  rows: T[]; cols: Col<T>[]; rowKey: (r: T) => string;
  initialSort?: string; desc?: boolean; highlight?: (r: T) => boolean; maxRows?: number;
  onRow?: (r: T) => string | undefined;
  /** Khoá lưu cấu hình cột (localStorage). Mặc định: đường dẫn trang + danh sách cột. */
  tableId?: string;
  /** Hiện thanh công cụ (cột, mật độ, lọc, CSV). Mặc định: khi có >= 15 dòng hoặc có tableId. */
  toolbar?: boolean;
  csvName?: string;
};

const VIRTUAL_THRESHOLD = 500;
type Density = "compact" | "normal";
type Saved = { order?: ColumnOrderState; visibility?: VisibilityState; sizing?: ColumnSizingState; density?: Density };

function load(key: string): Saved {
  try { return JSON.parse(localStorage.getItem(key) || "{}") as Saved; } catch { return {}; }
}
function save(key: string, value: Saved) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage có thể bị tắt */ }
}
function fold(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}

/** Lọc: số hỗ trợ ">10", ">=5", "<0", "<=1", "10..20", "=3" (so trên giá trị gốc, vd tỷ lệ 0,2 = 20%);
 *  còn lại tìm chuỗi không dấu. */
export function matchFilter(value: unknown, raw: string): boolean {
  const q = raw.trim();
  if (!q) return true;
  const n = typeof value === "number" && Number.isFinite(value) ? value : null;
  const num = (s: string) => Number(s.replace(/\s/g, "").replace(",", "."));
  const range = q.match(/^(-?[\d.,]+)\s*\.\.\s*(-?[\d.,]+)$/);
  const cmp = q.match(/^(>=|<=|>|<|=)\s*(-?[\d.,]+)$/);
  if (range || cmp) {
    if (n === null) return false;
    if (range) return n >= num(range[1]) && n <= num(range[2]);
    const v = num(cmp![2]);
    return cmp![1] === ">" ? n > v : cmp![1] === "<" ? n < v : cmp![1] === ">=" ? n >= v : cmp![1] === "<=" ? n <= v : Math.abs(n - v) < 1e-9;
  }
  return fold(String(value ?? "")).includes(fold(q));
}

const filterFn: FilterFn<any> = (row, id, value) => matchFilter(row.getValue(id), String(value ?? ""));

export default function DataTable<T extends Record<string, any>>({
  rows, cols, rowKey, initialSort, desc = true, highlight, maxRows, onRow, tableId, toolbar, csvName,
}: DataTableProps<T>) {
  const router = useRouter();
  const pathname = usePathname();
  const storageKey = `dt:${tableId || `${pathname}:${cols.map((c) => c.key).join(",")}`}`;
  const [sorting, setSorting] = useState<SortingState>(initialSort ? [{ id: initialSort, desc }] : []);
  const [filters, setFilters] = useState<ColumnFiltersState>([]);
  const [visibility, setVisibility] = useState<VisibilityState>({});
  const [order, setOrder] = useState<ColumnOrderState>([]);
  const [sizing, setSizing] = useState<ColumnSizingState>({});
  const [density, setDensity] = useState<Density>("normal");
  const [showFilters, setShowFilters] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [menu, setMenu] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const dragFrom = useRef<string | null>(null);

  useEffect(() => {                       // đọc cấu hình đã lưu sau khi mount (tránh lệch SSR)
    const s = load(storageKey);
    if (s.order) setOrder(s.order);
    if (s.visibility) setVisibility(s.visibility);
    if (s.sizing) setSizing(s.sizing);
    if (s.density) setDensity(s.density);
    setLoaded(true);
  }, [storageKey]);
  useEffect(() => { if (loaded) save(storageKey, { order, visibility, sizing, density }); },
    [loaded, storageKey, order, visibility, sizing, density]);

  const columns = useMemo<ColumnDef<T>[]>(() => cols.map((c) => ({
    id: c.key,
    accessorFn: (r: T) => {
      const v = c.sortValue ? c.sortValue(r) : r[c.key];
      return v === null || (typeof v === "number" && !Number.isFinite(v)) ? undefined : v;
    },
    header: c.label,
    cell: (ctx) => (c.render ? c.render(ctx.row.original) : (ctx.getValue() as ReactNode)),
    sortUndefined: "last",
    sortDescFirst: true,
    filterFn,
    meta: { num: c.num, title: c.title },
    size: 140, minSize: 60,
  })), [cols]);

  const table = useReactTable({
    data: rows, columns, getRowId: (r) => rowKey(r),
    state: { sorting, columnFilters: filters, columnVisibility: visibility, columnOrder: order, columnSizing: sizing },
    onSortingChange: setSorting, onColumnFiltersChange: setFilters, onColumnVisibilityChange: setVisibility,
    onColumnOrderChange: setOrder, onColumnSizingChange: setSizing,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(), getFilteredRowModel: getFilteredRowModel(),
    enableMultiSort: true, isMultiSortEvent: (e: any) => !!e?.shiftKey, enableColumnResizing: true, columnResizeMode: "onChange",
  });

  const all = table.getRowModel().rows;
  const limited = maxRows && !showAll ? all.slice(0, maxRows) : all;
  const virtual = limited.length > VIRTUAL_THRESHOLD;
  const scroller = useRef<HTMLDivElement>(null);
  const rowHeight = density === "compact" ? 28 : 36;
  const virtualizer = useVirtualizer({
    count: virtual ? limited.length : 0, getScrollElement: () => scroller.current, estimateSize: () => rowHeight, overscan: 12,
  });
  const items = virtual ? virtualizer.getVirtualItems() : [];
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? virtualizer.getTotalSize() - items[items.length - 1].end : 0;
  const visibleRows = virtual ? items.map((v) => limited[v.index]) : limited;
  const leaf = table.getVisibleLeafColumns();
  const hasToolbar = toolbar ?? (rows.length >= 15 || !!tableId);
  const tall = virtual || rows.length > 25;

  const exportCSV = () => {
    const vis = leaf.map((c) => ({ key: c.id, label: String(c.columnDef.header) }));
    const data = all.map((r) => Object.fromEntries(vis.map((c) => [c.key, r.getValue(c.key)])));
    downloadCSV(`${csvName || tableId || "bang-du-lieu"}.csv`, toCSV(data, vis));
  };
  const move = (id: string, delta: number) => {
    const current = order.length ? [...order] : table.getAllLeafColumns().map((c) => c.id);
    const i = current.indexOf(id), j = i + delta;
    if (i < 0 || j < 0 || j >= current.length) return;
    [current[i], current[j]] = [current[j], current[i]];
    setOrder(current);
  };
  const drop = (target: string) => {
    const from = dragFrom.current;
    dragFrom.current = null;
    if (!from || from === target) return;
    const current = order.length ? [...order] : table.getAllLeafColumns().map((c) => c.id);
    current.splice(current.indexOf(from), 1);
    current.splice(current.indexOf(target), 0, from);
    setOrder(current);
  };
  const reset = () => { setOrder([]); setVisibility({}); setSizing({}); setDensity("normal"); setSorting(initialSort ? [{ id: initialSort, desc }] : []); setFilters([]); };
  const cellPad = density === "compact" ? "!py-0.5" : "";

  return (
    <div className="dt" data-density={density}>
      {hasToolbar && (
        <div className="dt-toolbar mb-2 flex flex-wrap items-center gap-2 text-xs" role="toolbar" aria-label="Công cụ bảng">
          <div className="relative">
            <button type="button" className="btn-ghost" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>Cột ▾</button>
            {menu && (
              <div className="dt-menu absolute z-30 mt-1 w-64 rounded-md border border-slate-200 bg-white p-2 shadow-lg" role="menu">
                {table.getAllLeafColumns().map((c, i, arr) => (
                  <div key={c.id} className="flex items-center gap-1 py-0.5">
                    <label className="flex flex-1 items-center gap-2"><input type="checkbox" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()} disabled={c.getIsVisible() && leaf.length === 1} />{String(c.columnDef.header)}</label>
                    <button type="button" className="px-1 text-slate-500 disabled:opacity-30" aria-label={`Đưa cột ${String(c.columnDef.header)} lên`} disabled={i === 0} onClick={() => move(c.id, -1)}>↑</button>
                    <button type="button" className="px-1 text-slate-500 disabled:opacity-30" aria-label={`Đưa cột ${String(c.columnDef.header)} xuống`} disabled={i === arr.length - 1} onClick={() => move(c.id, 1)}>↓</button>
                  </div>))}
                <button type="button" className="link mt-1 text-xs" onClick={reset}>Khôi phục mặc định</button>
              </div>)}
          </div>
          <button type="button" className="btn-ghost" aria-pressed={density === "compact"} onClick={() => setDensity((d) => (d === "compact" ? "normal" : "compact"))}>
            Mật độ: {density === "compact" ? "gọn" : "thường"}</button>
          <button type="button" className="btn-ghost" aria-pressed={showFilters} onClick={() => setShowFilters((s) => !s)}>Lọc theo cột</button>
          <button type="button" className="btn-ghost" onClick={exportCSV}>Xuất CSV</button>
          <span className="text-slate-500">{all.length.toLocaleString("vi-VN")}{all.length !== rows.length ? `/${rows.length.toLocaleString("vi-VN")}` : ""} dòng
            {sorting.length > 1 ? ` · sắp xếp ${sorting.length} cột` : ""} · Shift+click để sắp xếp nhiều cột</span>
        </div>)}
      <div ref={scroller} className={`dt-scroll overflow-auto ${tall ? "max-h-[70vh]" : ""}`}>
        <table className="tbl dt-table" style={{ width: table.getTotalSize(), minWidth: "100%" }}>
          <thead className="dt-head">
            {table.getHeaderGroups().map((g) => (
              <tr key={g.id}>
                {g.headers.map((h, i) => {
                  const meta = h.column.columnDef.meta as { num?: boolean; title?: string } | undefined;
                  const sorted = h.column.getIsSorted();
                  const rank = sorting.length > 1 ? sorting.findIndex((s) => s.id === h.column.id) + 1 : 0;
                  return (
                    <th key={h.id} title={meta?.title} style={{ width: h.getSize() }}
                      aria-sort={sorted ? (sorted === "desc" ? "descending" : "ascending") : undefined}
                      className={`${meta?.num ? "text-right" : ""} ${i === 0 ? "dt-first" : ""} relative`}
                      draggable onDragStart={() => { dragFrom.current = h.column.id; }} onDragOver={(e) => e.preventDefault()} onDrop={() => drop(h.column.id)}>
                      <button type="button" className={`w-full text-inherit ${meta?.num ? "text-right" : "text-left"}`}
                        onClick={h.column.getToggleSortingHandler()} aria-label={`Sắp xếp theo ${String(h.column.columnDef.header)}`}>
                        {flexRender(h.column.columnDef.header, h.getContext())}{sorted ? (sorted === "desc" ? " ▼" : " ▲") : ""}{rank > 0 ? <sup>{rank}</sup> : null}
                      </button>
                      <span role="separator" aria-orientation="vertical" aria-label={`Đổi độ rộng cột ${String(h.column.columnDef.header)}`}
                        onMouseDown={h.getResizeHandler()} onTouchStart={h.getResizeHandler()} onDoubleClick={() => h.column.resetSize()}
                        className={`dt-resizer ${h.column.getIsResizing() ? "is-resizing" : ""}`} />
                    </th>);
                })}
              </tr>))}
            {showFilters && (
              <tr className="dt-filters">
                {leaf.map((c, i) => (
                  <th key={c.id} className={i === 0 ? "dt-first" : ""}>
                    <input className="sel w-full !py-0.5 text-xs font-normal" value={String(c.getFilterValue() ?? "")}
                      onChange={(e) => c.setFilterValue(e.target.value || undefined)}
                      placeholder={(c.columnDef.meta as any)?.num ? ">10, 5..20" : "chứa…"} aria-label={`Lọc ${String(c.columnDef.header)}`} />
                  </th>))}
              </tr>)}
          </thead>
          <tbody>
            {padTop > 0 && <tr aria-hidden style={{ height: padTop }} />}
            {visibleRows.map((r) => {
              const href = onRow?.(r.original);
              return (
                <tr key={r.id} style={virtual ? { height: rowHeight } : undefined}
                  className={`${highlight?.(r.original) ? "bg-amber-50 font-semibold" : ""}${href ? " cursor-pointer" : ""}`}
                  onClick={href ? () => router.push(href) : undefined}>
                  {r.getVisibleCells().map((cell, i) => {
                    const meta = cell.column.columnDef.meta as { num?: boolean } | undefined;
                    const content = flexRender(cell.column.columnDef.cell, cell.getContext());
                    return (
                      <td key={cell.id} style={{ width: cell.column.getSize() }} className={`${meta?.num ? "text-right tabular-nums" : ""} ${i === 0 ? "dt-first" : ""} ${cellPad}`}>
                        {i === 0 && href ? <Link className="link" href={href} onClick={(e) => e.stopPropagation()}>{content}</Link> : content}
                      </td>);
                  })}
                </tr>);
            })}
            {padBottom > 0 && <tr aria-hidden style={{ height: padBottom }} />}
          </tbody>
        </table>
      </div>
      {maxRows && all.length > maxRows && (
        <div className="mt-1 text-xs text-slate-500">
          Hiển thị {showAll ? all.length : maxRows}/{all.length} dòng{" "}
          <button type="button" className="link" onClick={() => setShowAll((s) => !s)}>{showAll ? "Thu gọn" : "Xem tất cả"}</button>
        </div>)}
    </div>
  );
}
