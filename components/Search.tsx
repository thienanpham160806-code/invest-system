"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJSON } from "@/lib/api";

type SymbolRow = { symbol: string; name: string; brand?: string; exchange: string; icb1: string; has_bctc: boolean; market_cap?: number };
const exchanges = ["ALL", "HOSE", "HNX", "UPCOM"];
const labels: Record<string, string> = { ALL: "Tất cả", HOSE: "HOSE", HNX: "HNX", UPCOM: "UPCOM" };
const legalWords = new Set(["cong", "ty", "co", "phan", "tap", "doan", "ctcp", "jsc", "joint", "stock"]);
function norm(s: string) { return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
function rankRow(r: SymbolRow, query: string): number | null {
  const q = norm(query), qCompact = q.replace(/\s/g, "");
  if (!q) return null;
  const symbol = norm(r.symbol).replace(/\s/g, "");
  if (symbol === qCompact) return 0;
  if (symbol.startsWith(qCompact)) return 1;
  if (symbol.includes(qCompact)) return 2;
  const brand = norm(r.brand || "");
  if (brand.replace(/\s/g, "").startsWith(qCompact)) return 3;
  const words = norm(r.name || "").split(/\s+/).filter((w) => !legalWords.has(w));
  if (words.some((w) => w.startsWith(q))) return 4;
  if (norm(r.name || "").includes(q) || brand.includes(q)) return 5;
  return null;
}
function Highlight({ text, query }: { text: string; query: string }) {
  const q = norm(query);
  if (!q) return <>{text}</>;
  // Build a normalized-index to original-text range map so accents still highlight correctly.
  let clean = ""; const starts: number[] = [], ends: number[] = [];
  for (let i = 0; i < text.length;) {
    const cp = String.fromCodePoint(text.codePointAt(i)!); const width = cp.length;
    let part = norm(cp);
    if (!part && /[\s\p{P}\p{S}]/u.test(cp)) part = " ";
    for (const c of part) { clean += c; starts.push(i); ends.push(i + width); }
    i += width;
  }
  const at = clean.indexOf(q);
  if (at < 0 || !starts.length) return <>{text}</>;
  const begin = starts[at], finish = ends[at + q.length - 1];
  return <>{text.slice(0, begin)}<mark className="rounded bg-amber-200 px-0.5 font-semibold text-slate-950">{text.slice(begin, finish)}</mark>{text.slice(finish)}</>;
}

export default function Search({ big = false, globalHotkeys = false, current = "" }: { big?: boolean; globalHotkeys?: boolean; current?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [exchange, setExchange] = useState("ALL");
  const [items, setItems] = useState<SymbolRow[]>([]), [counts, setCounts] = useState<Record<string, number>>({});
  const [scrollTop, setScrollTop] = useState(0), [idx, setIdx] = useState(0);
  const input = useRef<HTMLInputElement>(null), viewport = useRef<HTMLDivElement>(null);
  const openPicker = useCallback(() => {
    try { setExchange(localStorage.getItem("ticker-picker-exchange") || "ALL"); } catch { setExchange("ALL"); }
    setOpen(true);
    void getJSON("/api/py/symbols?exchange=ALL").then((d) => { setItems(d.items); setCounts(d.counts || {}); }).catch(() => setItems([]));
    setTimeout(() => input.current?.focus(), 0);
  }, []);
  useEffect(() => {
    if (!globalHotkeys) return;
    const handler = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(el?.tagName) || el?.isContentEditable;
      if (e.key === "/" && !typing || (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPicker(); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [globalHotkeys, openPicker]);
  const rows = useMemo(() => {
    const filtered = items.filter((r) => exchange === "ALL" || r.exchange === exchange);
    const ranked = filtered.map((row) => ({ row, tier: rankRow(row, q.trim()) })).filter((x) => x.tier !== null) as { row: SymbolRow; tier: number }[];
    const query = norm(q.trim()).replace(/\s/g, "");
    const hasShortSymbolMatch = query.length > 0 && query.length <= 3 && ranked.some((x) => x.tier <= 2);
    return ranked.filter((x) => !hasShortSymbolMatch || x.tier <= 2)
      .sort((a, b) => a.tier - b.tier || (b.row.market_cap || 0) - (a.row.market_cap || 0) || a.row.symbol.localeCompare(b.row.symbol))
      .map((x) => x.row);
  }, [items, exchange, q]);
  const countsBy = useMemo(() => ({ ALL: Object.values(counts).reduce((a, b) => a + b, 0), ...counts }), [counts]);
  const choose = (s: string) => { setOpen(false); setQ(""); router.push(`/stock/${s}`); };
  const rowHeight = 58, viewportHeight = 390, start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3), end = Math.min(rows.length, start + Math.ceil(viewportHeight / rowHeight) + 6);
  useEffect(() => {
    if (!open || !viewport.current || idx < 0 || idx >= rows.length) return;
    const top = idx * rowHeight, bottom = top + rowHeight, view = viewport.current;
    if (top < view.scrollTop) view.scrollTop = top;
    else if (bottom > view.scrollTop + view.clientHeight) view.scrollTop = bottom - view.clientHeight;
  }, [idx, open, rows.length]);
  return <>
    <button className={`flex w-full min-w-0 items-center justify-between gap-2 whitespace-nowrap truncate rounded-md border border-slate-300 bg-white text-left text-slate-700 px-3 ${big ? "py-3 text-lg" : "py-1.5 text-sm"}`} onClick={openPicker} aria-haspopup="dialog">
      <span className="truncate">Tìm mã hoặc tên công ty</span><span className="shrink-0 rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 text-xs font-mono">/</span>
    </button>
    {open && <div className="fixed inset-0 z-50 bg-slate-950/50 p-0 sm:p-8" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <section className="mx-auto flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white text-slate-900 shadow-2xl sm:mt-10 sm:h-[min(620px,85vh)] sm:rounded-xl" role="dialog" aria-modal="true" aria-label="Chọn mã cổ phiếu">
        <div className="border-b p-4">
          <div className="flex gap-2"><input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setIdx(0); }} onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(rows.length - 1, i + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
            if (e.key === "Enter" && rows[idx]) choose(rows[idx].symbol);
          }} className="sel min-w-0 flex-1 text-slate-900 placeholder:text-slate-400" placeholder="Tìm mã hoặc tên công ty" />
            <button className="btn-ghost text-slate-700" onClick={() => setOpen(false)}>Đóng</button></div>
          <div className="mt-3 flex flex-wrap gap-2">{exchanges.map((ex) => <button key={ex} className={`rounded-full border px-3 py-1 text-xs ${exchange === ex ? "border-sky-700 bg-sky-50 font-semibold text-sky-800" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`} onClick={() => {
            setExchange(ex); setScrollTop(0); setIdx(0); try { localStorage.setItem("ticker-picker-exchange", ex); } catch { /* storage can be disabled */ }
          }}>{labels[ex]} <span className="text-slate-500">{countsBy[ex] || 0}</span></button>)}</div>
          <p className="mt-2 text-xs text-slate-500">{rows.length.toLocaleString("vi-VN")} mã · ↑ ↓ di chuyển · Enter chọn · Esc đóng</p>
        </div>
        <div ref={viewport} className="flex-1 overflow-auto" style={{ maxHeight: viewportHeight }} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
          {rows.length ? <div style={{ height: rows.length * rowHeight, position: "relative" }}>{rows.slice(start, end).map((r, off) => {
            const i = start + off;
            return <button key={r.symbol} onClick={() => choose(r.symbol)} className={`absolute left-0 flex w-full items-center gap-3 border-b border-slate-100 px-4 text-left text-slate-900 hover:bg-sky-50 ${i === idx ? "bg-sky-50" : ""}`} style={{ height: rowHeight, top: i * rowHeight }}>
              <b className={`w-14 shrink-0 ${r.symbol === current.toUpperCase() ? "text-sky-800" : "text-slate-900"}`}><Highlight text={r.symbol} query={q} /></b>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-700" title={r.name}><Highlight text={r.name} query={q} /></span><span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{r.exchange}</span>
              <span className="hidden max-w-40 truncate text-xs text-slate-500 md:block" title={r.icb1}>{r.icb1}</span>{!r.has_bctc && <span title="Chưa có BCTC" className="text-amber-700">○</span>}
            </button>;
          })}</div> : <p className="p-5 text-sm text-slate-500">Không tìm thấy mã phù hợp.</p>}
        </div>
      </section>
    </div>}
  </>;
}
