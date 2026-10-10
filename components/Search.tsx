"use client";
// Thanh lệnh kiêm chọn mã (mở bằng "/" hoặc Ctrl+K). Gõ tên/mã để tìm cổ phiếu; gõ lệnh kiểu terminal
// (FPT FA, CMP FPT CMG, SECT Ngân hàng, TOP, MACRO, ? …) — xem lib/terminal/commands.ts.
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJSON } from "@/lib/api";
import { completeCommand, parseCommand, type ParseResult, TICKER_VIEWS, GLOBAL_ROUTES } from "@/lib/terminal/commands";

type SymbolRow = { symbol: string; name: string; brand?: string; exchange: string; icb1: string; has_bctc: boolean; market_cap?: number };
type Sector = { slug: string; name: string };
const exchanges = ["ALL", "HOSE", "HNX", "UPCOM"];
const labels: Record<string, string> = { ALL: "Tất cả", HOSE: "HOSE", HNX: "HNX", UPCOM: "UPCOM" };
const legalWords = new Set(["cong", "ty", "co", "phan", "tap", "doan", "ctcp", "jsc", "joint", "stock"]);
const HISTORY_KEY = "terminal-history";
const HISTORY_MAX = 20;
function norm(s: string) { return s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
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

export function readHistory(): string[] {
  try { const v = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); return Array.isArray(v) ? v.filter((x) => typeof x === "string") : []; } catch { return []; }
}
function pushHistory(cmd: string) {
  try {
    const next = [cmd, ...readHistory().filter((x) => x !== cmd)].slice(0, HISTORY_MAX);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  } catch { /* storage có thể bị tắt */ }
}
function describe(r: Extract<ParseResult, { ok: true }>): string {
  const c = r.command;
  if (c.kind === "ticker") return `${c.symbol} – ${TICKER_VIEWS[c.view].label}`;
  if (c.kind === "compare") return `So sánh ${c.symbols.join(", ")}`;
  if (c.kind === "sector") return `Ngành “${c.query}”${c.slug ? "" : " (tìm trong danh sách ngành)"}`;
  if (c.kind === "global") return GLOBAL_ROUTES[c.keyword].label;
  return "Bảng lệnh & phím tắt";
}
/** Ô nhập "trông như lệnh": có từ khoá lệnh hoặc nhiều từ viết hoa - khi đó mới hiện lỗi/gợi ý lệnh. */
function looksLikeCommand(q: string) {
  const head = q.trim().split(/\s+/)[0]?.toUpperCase() || "";
  return ["CMP", "SECT", "HELP", "?", "TOP", "MAP", "MACRO", "BT", "SRC"].includes(head) || /^[A-Za-z0-9]{3}\s+\S+/.test(q.trim());
}

export default function Search({ big = false, globalHotkeys = false, current = "" }: { big?: boolean; globalHotkeys?: boolean; current?: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [exchange, setExchange] = useState("ALL");
  const [items, setItems] = useState<SymbolRow[]>([]), [counts, setCounts] = useState<Record<string, number>>({});
  const [sectors, setSectors] = useState<Sector[]>([]), [history, setHistory] = useState<string[]>([]);
  const [scrollTop, setScrollTop] = useState(0), [idx, setIdx] = useState(0), [histIdx, setHistIdx] = useState(-1);
  const input = useRef<HTMLInputElement>(null), viewport = useRef<HTMLDivElement>(null);
  const openPicker = useCallback(() => {
    try { setExchange(localStorage.getItem("ticker-picker-exchange") || "ALL"); } catch { setExchange("ALL"); }
    setHistory(readHistory()); setHistIdx(-1);
    setOpen(true);
    void getJSON("/api/py/symbols?exchange=ALL").then((d) => { setItems(d.items); setCounts(d.counts || {}); }).catch(() => setItems([]));
    void Promise.all([1, 2].map((l) => getJSON(`/api/py/sectors?level=${l}`).then((d) => d.items as Sector[]).catch(() => [])))
      .then((lists) => setSectors(lists.flat()));
    setTimeout(() => input.current?.focus(), 0);
  }, []);
  useEffect(() => {
    if (!globalHotkeys) return;
    const handler = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(el?.tagName) || el?.isContentEditable;
      if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey || (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openPicker(); }
    };
    const external = () => openPicker();
    document.addEventListener("keydown", handler);
    window.addEventListener("open-command-bar", external);
    return () => { document.removeEventListener("keydown", handler); window.removeEventListener("open-command-bar", external); };
  }, [globalHotkeys, openPicker]);

  const symbolSet = useMemo(() => new Set(items.map((r) => r.symbol)), [items]);
  const symbols = useMemo(() => items.map((r) => r.symbol), [items]);
  const resolveSector = useCallback((query: string) => {
    const n = norm(query);
    const exact = sectors.find((s) => norm(s.name) === n);
    const starts = sectors.find((s) => norm(s.name).startsWith(n));
    const inside = sectors.find((s) => norm(s.name).includes(n));
    return (exact || starts || inside)?.slug ?? null;
  }, [sectors]);
  const opts = useMemo(() => ({ isSymbol: items.length ? (s: string) => symbolSet.has(s) : undefined, symbols, resolveSector }),
    [items.length, symbolSet, symbols, resolveSector]);
  const cmd = useMemo(() => (q.trim() ? parseCommand(q, opts) : null), [q, opts]);
  const completions = useMemo(() => (q.trim() ? completeCommand(q, opts, 6).filter((c) => c !== q.trim().toUpperCase()) : []), [q, opts]);
  type Ok = Extract<ParseResult, { ok: true }>;
  type Bad = Extract<ParseResult, { ok: false }>;
  const okCmd: Ok | null = cmd && cmd.ok ? (cmd as Ok) : null;
  const badCmd: Bad | null = cmd && !cmd.ok && looksLikeCommand(q) ? (cmd as Bad) : null;

  const rows = useMemo(() => {
    const filtered = items.filter((r) => exchange === "ALL" || r.exchange === exchange);
    const ranked = filtered.map((row) => ({ row, tier: rankRow(row, q.trim()) })).filter((x) => x.tier !== null) as { row: SymbolRow; tier: number }[];
    const query = norm(q.trim()).replace(/\s/g, "");
    const hasShortSymbolMatch = query.length > 0 && query.length <= 3 && ranked.some((x) => x.tier <= 2);
    return ranked.filter((x) => !hasShortSymbolMatch || x.tier <= 2)
      .sort((a, b) => a.tier - b.tier || (b.row.market_cap || 0) - (a.row.market_cap || 0) || a.row.symbol.localeCompare(b.row.symbol))
      .map((x) => x.row);
  }, [items, exchange, q]);
  // -1 = dòng lệnh; mặc định chọn dòng lệnh khi lệnh hợp lệ và không chỉ là một mã (khi đó dòng mã đầu tiên trùng kết quả)
  useEffect(() => { setIdx(cmd?.ok && !(cmd.command.kind === "ticker" && cmd.command.view === "DES" && rows[0]?.symbol === cmd.command.symbol) ? -1 : 0); },
    [cmd, rows]);
  const countsBy = useMemo(() => ({ ALL: Object.values(counts).reduce((a, b) => a + b, 0), ...counts }), [counts]);
  const close = () => { setOpen(false); setQ(""); };
  const go = (href: string | null, text: string, help = false) => {
    pushHistory(text.trim().toUpperCase().replace(/\s+/g, " "));
    close();
    if (help) window.dispatchEvent(new Event("open-shortcuts"));
    else if (href) router.push(href);
  };
  const choose = (s: string) => go(`/stock/${s}`, s);
  const runCommand = (text: string) => {
    const r = parseCommand(text, opts);
    if (r.ok) go(r.href, text, r.command.kind === "help");
    else { setQ(text); input.current?.focus(); }
  };
  const rowHeight = 58, viewportHeight = 390, start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3), end = Math.min(rows.length, start + Math.ceil(viewportHeight / rowHeight) + 6);
  useEffect(() => {
    if (!open || !viewport.current || idx < 0 || idx >= rows.length) return;
    const top = idx * rowHeight, bottom = top + rowHeight, view = viewport.current;
    if (top < view.scrollTop) view.scrollTop = top;
    else if (bottom > view.scrollTop + view.clientHeight) view.scrollTop = bottom - view.clientHeight;
  }, [idx, open, rows.length]);
  return <>
    <button className={`flex w-full min-w-0 items-center justify-between gap-2 whitespace-nowrap truncate rounded-md border border-slate-300 bg-white text-left text-slate-700 px-3 ${big ? "py-3 text-lg" : "py-1.5 text-sm"}`} onClick={openPicker} aria-haspopup="dialog" data-testid="command-bar-trigger">
      <span className="truncate">Tìm mã, tên công ty hoặc gõ lệnh</span><span className="shrink-0 rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 text-xs font-mono">/</span>
    </button>
    {open && <div className="fixed inset-0 z-50 bg-slate-950/50 p-0 sm:p-8" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <section className="mx-auto flex h-full w-full max-w-2xl flex-col overflow-hidden bg-white text-slate-900 shadow-2xl sm:mt-10 sm:h-[min(640px,85vh)] sm:rounded-xl" role="dialog" aria-modal="true" aria-label="Thanh lệnh và chọn mã cổ phiếu">
        <div className="border-b p-4">
          <div className="flex gap-2"><input ref={input} value={q} data-testid="command-input" role="combobox" aria-expanded aria-controls="command-results" aria-autocomplete="list"
            onChange={(e) => { setQ(e.target.value); setHistIdx(-1); }} onKeyDown={(e) => {
            if (e.key === "Escape") close();
            if (e.key === "Tab" && completions[0]) { e.preventDefault(); setQ(completions[0] + (completions[0].split(" ").length === 1 ? " " : "")); }
            if (e.key === "ArrowUp" && !q && history.length) { e.preventDefault(); const h = Math.min(history.length - 1, histIdx + 1); setHistIdx(h); setQ(history[h]); return; }
            if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(rows.length - 1, i + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(cmd?.ok ? -1 : 0, i - 1)); }
            if (e.key === "Enter") {
              if (idx === -1 && cmd) runCommand(q);
              else if (rows[idx]) choose(rows[idx].symbol);
              else if (cmd) runCommand(q);
            }
          }} className="sel min-w-0 flex-1 text-slate-900 placeholder:text-slate-400" placeholder="FPT · FPT FA · CMP FPT CMG · SECT Ngân hàng · TOP · ?" />
            <button className="btn-ghost text-slate-700" onClick={close}>Đóng</button></div>
          <div className="mt-3 flex flex-wrap gap-2">{exchanges.map((ex) => <button key={ex} className={`rounded-full border px-3 py-1 text-xs ${exchange === ex ? "border-sky-700 bg-sky-50 font-semibold text-sky-800" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`} onClick={() => {
            setExchange(ex); setScrollTop(0); setIdx(0); try { localStorage.setItem("ticker-picker-exchange", ex); } catch { /* storage can be disabled */ }
          }}>{labels[ex]} <span className="text-slate-500">{countsBy[ex] || 0}</span></button>)}</div>
          <p className="mt-2 text-xs text-slate-500">{rows.length.toLocaleString("vi-VN")} mã · ↑ ↓ di chuyển · Enter chọn · Tab hoàn thành lệnh · Esc đóng · gõ <b>?</b> xem bảng lệnh</p>
        </div>
        <div id="command-results" className="border-b empty:hidden">
          {okCmd && <button type="button" data-testid="command-row" onClick={() => runCommand(q)} onMouseEnter={() => setIdx(-1)}
                className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm ${idx === -1 ? "bg-sky-50" : ""}`}>
                <span><span className="mr-2 rounded bg-slate-900 px-1.5 py-0.5 font-mono text-xs text-white">↵</span>{describe(okCmd)}</span>
                {okCmd.note && <span className="text-xs text-amber-700">{okCmd.note}</span>}
                <span className="font-mono text-xs text-slate-500">{okCmd.href || ""}</span>
              </button>}
          {badCmd && <div className="px-4 py-2.5 text-sm" data-testid="command-error">
                <span className="text-red-700">{badCmd.error}</span>
                {badCmd.suggestions.length > 0 && <span className="ml-2 text-slate-600">Ý bạn là: {badCmd.suggestions.map((s) => (
                  <button key={s} type="button" className="link mr-2 font-mono" onClick={() => runCommand(s)}>{s}</button>))}</span>}
              </div>}
          {completions.length > 0 && <div className="flex flex-wrap gap-1.5 px-4 pb-2.5 pt-1" aria-label="Gợi ý hoàn thành">{completions.map((c) => (
            <button key={c} type="button" className="rounded border border-slate-300 px-2 py-0.5 font-mono text-xs text-slate-700 hover:bg-slate-50" onClick={() => { setQ(c + " "); input.current?.focus(); }}>{c}</button>))}</div>}
          {!q.trim() && history.length > 0 && <div className="px-4 py-2.5 text-xs" data-testid="command-history"><span className="mr-2 text-slate-500">Gần đây:</span>{history.slice(0, 8).map((h) => (
            <button key={h} type="button" className="link mr-2 font-mono" onClick={() => runCommand(h)}>{h}</button>))}</div>}
        </div>
        <div ref={viewport} className="flex-1 overflow-auto" style={{ maxHeight: viewportHeight }} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
          {rows.length ? <div style={{ height: rows.length * rowHeight, position: "relative" }}>{rows.slice(start, end).map((r, off) => {
            const i = start + off;
            return <button key={r.symbol} onClick={() => choose(r.symbol)} className={`absolute left-0 flex w-full items-center gap-3 border-b border-slate-100 px-4 text-left text-slate-900 hover:bg-sky-50 ${i === idx ? "bg-sky-50" : ""}`} style={{ height: rowHeight, top: i * rowHeight }}>
              <b className={`w-14 shrink-0 ${r.symbol === current.toUpperCase() ? "text-sky-800" : "text-slate-900"}`}><Highlight text={r.symbol} query={q} /></b>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-700" title={r.name}><Highlight text={r.name} query={q} /></span><span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{r.exchange}</span>
              <span className="hidden max-w-40 truncate text-xs text-slate-500 md:block" title={r.icb1}>{r.icb1}</span>{!r.has_bctc && <span title="Chưa có BCTC" className="text-amber-700">○</span>}
            </button>;
          })}</div> : <p className="p-5 text-sm text-slate-500">{q.trim() ? "Không tìm thấy mã phù hợp." : "Gõ mã, tên công ty hoặc lệnh."}</p>}
        </div>
      </section>
    </div>}
  </>;
}
