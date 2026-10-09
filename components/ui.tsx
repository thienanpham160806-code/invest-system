"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
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

export type Col<T> = { key: string; label: string; render?: (r: T) => ReactNode; num?: boolean; sortValue?: (r: T) => any; title?: string };

export function SortTable<T extends Record<string, any>>({ rows, cols, initialSort, desc = true, rowKey, highlight, maxRows, onRow }: {
  rows: T[]; cols: Col<T>[]; initialSort?: string; desc?: boolean; rowKey: (r: T) => string; highlight?: (r: T) => boolean; maxRows?: number; onRow?: (r: T) => string | undefined;
}) {
  const router = useRouter();
  const [sort, setSort] = useState<{ key?: string; desc: boolean }>({ key: initialSort, desc });
  const sorted = useMemo(() => {
    if (!sort.key) return rows;
    const col = cols.find((c) => c.key === sort.key);
    const val = (r: T) => (col?.sortValue ? col.sortValue(r) : r[sort.key!]);
    return [...rows].sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      const c = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb), "vi");
      return sort.desc ? -c : c;
    });
  }, [rows, sort, cols]);
  const shown = maxRows ? sorted.slice(0, maxRows) : sorted;
  return (
    <div className="overflow-x-auto">
      <table className="tbl">
        <thead>
          <tr>{cols.map((c) => (
            <th key={c.key} title={c.title} aria-sort={sort.key === c.key ? (sort.desc ? "descending" : "ascending") : undefined} className={c.num ? "text-right" : ""}>
              <button type="button" className={`w-full text-inherit ${c.num ? "text-right" : "text-left"}`} onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))} aria-label={`Sắp xếp theo ${c.label}`}>
                {c.label}{sort.key === c.key ? (sort.desc ? " ▼" : " ▲") : ""}
              </button>
            </th>))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => {
            const href = onRow?.(r);
            return (
              <tr key={rowKey(r)} className={`${highlight?.(r) ? "bg-amber-50 font-semibold" : ""}${href ? " cursor-pointer" : ""}`} onClick={href ? () => router.push(href) : undefined}>
                {cols.map((c, i) => (
                  <td key={c.key} className={c.num ? "text-right tabular-nums" : ""}>
                    {i === 0 && href ? <Link className="link" href={href} onClick={(e) => e.stopPropagation()}>{c.render ? c.render(r) : r[c.key]}</Link> : c.render ? c.render(r) : r[c.key]}
                  </td>))}
              </tr>);
          })}
        </tbody>
      </table>
      {maxRows && sorted.length > maxRows && <div className="text-xs text-slate-500 mt-1">Hiển thị {maxRows}/{sorted.length} dòng</div>}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }: { tabs: { key: string; label: string }[]; active: string; onChange: (k: string) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200 no-print">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} className={`tab ${active === t.key ? "tab-active" : ""}`}>{t.label}</button>
      ))}
    </div>
  );
}
