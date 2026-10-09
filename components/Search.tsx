"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJSON } from "@/lib/api";

type SymbolRow = { symbol: string; name: string; brand?: string; exchange: string; icb1: string; has_bctc: boolean };
const exchanges = ["ALL", "HOSE", "HNX", "UPCOM"];
const labels: Record<string, string> = { ALL: "Tất cả", HOSE: "HOSE", HNX: "HNX", UPCOM: "UPCOM" };
function norm(s: string) { return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase(); }

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
    const query = norm(q.trim());
    return items.filter((r) => (exchange === "ALL" || r.exchange === exchange) && (!query || norm(`${r.symbol} ${r.name || ""} ${r.brand || ""}`).includes(query)));
  }, [items, exchange, q]);
  const countsBy = useMemo(() => ({ ALL: Object.values(counts).reduce((a, b) => a + b, 0), ...counts }), [counts]);
  const choose = (s: string) => { setOpen(false); setQ(""); router.push(`/stock/${s}`); };
  const rowHeight = 58, viewportHeight = 390, start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3), end = Math.min(rows.length, start + Math.ceil(viewportHeight / rowHeight) + 6);
  return <>
    <button className={`w-full text-left rounded-md border border-slate-300 bg-white text-slate-700 px-3 ${big ? "py-3 text-lg" : "py-1.5 text-sm"}`} onClick={openPicker} aria-haspopup="dialog">
      {big ? "Chọn sàn và tìm mã hoặc tên công ty…" : "⌕  Tìm mã / công ty ( / hoặc Ctrl+K )"}
    </button>
    {open && <div className="fixed inset-0 z-50 bg-slate-950/50 p-0 sm:p-8" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
      <section className="mx-auto flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white text-slate-900 shadow-2xl sm:mt-10 sm:h-[min(620px,85vh)] sm:rounded-xl" role="dialog" aria-modal="true" aria-label="Chọn mã cổ phiếu">
        <div className="border-b p-4">
          <div className="flex gap-2"><input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setIdx(0); }} onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(rows.length - 1, i + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
            if (e.key === "Enter" && rows[idx]) choose(rows[idx].symbol);
          }} className="sel min-w-0 flex-1 text-slate-900 placeholder:text-slate-400" placeholder="Gõ mã, tên công ty hoặc thương hiệu (không dấu cũng được)" />
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
              <b className={`w-14 shrink-0 ${r.symbol === current.toUpperCase() ? "text-sky-800" : "text-slate-900"}`}>{r.symbol}</b>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-700" title={r.name}>{r.name}</span><span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{r.exchange}</span>
              <span className="hidden max-w-40 truncate text-xs text-slate-500 md:block" title={r.icb1}>{r.icb1}</span>{!r.has_bctc && <span title="Chưa có BCTC" className="text-amber-700">○</span>}
            </button>;
          })}</div> : <p className="p-5 text-sm text-slate-500">Không tìm thấy mã phù hợp.</p>}
        </div>
      </section>
    </div>}
  </>;
}
