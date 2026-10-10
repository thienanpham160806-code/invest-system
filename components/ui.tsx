"use client";
import DataTable, { type DataTableProps } from "@/components/DataTable";
import type { ReactNode } from "react";
import type { Prov } from "@/lib/api";
import { dmy } from "@/lib/fmt";

export function AsOf({ p, label = "Dữ liệu đến" }: { p?: Prov | null; label?: string }) {
  if (!p) return null;
  return (
    <span className="asof" title={[p.source, p.note, p.origin, p.fetched_at && `lấy lúc ${dmy(p.fetched_at)}`].filter(Boolean).join(" · ")}>
      {label} {dmy(p.as_of) } – nguồn {shortSource(p.source)}{p.note ? " ⚠" : ""}
    </span>
  );
}
function shortSource(s: string) { return s && s.length > 70 ? s.slice(0, 67) + "…" : s; }

export function Card({ title, right, children, className = "" }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && <div className="flex flex-wrap items-center justify-between gap-2 mb-3"><h2 className="card-title">{title}</h2>{right}</div>}
      {children}
    </section>
  );
}

export function Loading({ what = "dữ liệu" }: { what?: string }) {
  return <div className="text-sm text-slate-500 py-6 animate-pulse">Đang tải {what}…</div>;
}
export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded border border-red-200 bg-red-50 text-red-700 text-sm p-3">Lỗi: {error}</div>;
}
export function Stat({ label, value, sub, className = "" }: { label: string; value: ReactNode; sub?: ReactNode; className?: string }) {
  return (
    <div className={`stat ${className}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export type { Col } from "@/components/DataTable";

/** Bảng sắp xếp được - giữ nguyên API cũ, chạy trên DataTable (TanStack) để mọi bảng có cùng tính năng. */
export function SortTable<T extends Record<string, any>>(props: DataTableProps<T>) {
  return <DataTable {...props} />;
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200 no-print" role="tablist">
      {tabs.map((t, i) => (
        <button key={t.key} role="tab" aria-selected={active === t.key} data-tab={t.key} onClick={() => onChange(t.key)}
          className={`tab ${active === t.key ? "tab-active" : ""}`} title={i < 9 ? `Phím ${i + 1}` : undefined}>{t.label}</button>
      ))}
    </div>
  );
}
