"use client";
// So sánh nhiều mã (lệnh CMP FPT CMG ELC). Danh sách mã đồng bộ với ?ma= để chia sẻ được.
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CompareLine } from "@/components/Charts";
import { Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { getJSON } from "@/lib/api";
import { bnLabel, cls, num, pct, price, RATING_COLOR, times } from "@/lib/fmt";
import { MAX_COMPARE } from "@/lib/terminal/commands";

const COLORS = ["#0b3b6f", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#4b5563"];
const GROUPS: Record<string, string> = { macro: "Vĩ mô", sector: "Ngành", quality: "Chất lượng", growth: "Tăng trưởng",
  valuation: "Định giá", technical: "Kỹ thuật", sentiment: "Tin tức" };

function parseList(raw: string | null): string[] {
  return [...new Set((raw || "").toUpperCase().split(/[\s,;]+/).filter((s) => /^[A-Z0-9]{3}$/.test(s)))].slice(0, MAX_COMPARE);
}

export default function ComparePage() {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [data, setData] = useState<Record<string, any>>({});
  const [prices, setPrices] = useState<Record<string, any[]>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [ready, setReady] = useState(false);

  useEffect(() => { setSymbols(parseList(new URLSearchParams(window.location.search).get("ma"))); setReady(true); }, []);
  useEffect(() => {
    if (!ready) return;
    try { const u = new URL(window.location.href); u.searchParams.set("ma", symbols.join(",")); window.history.replaceState(null, "", u); } catch { /* bỏ qua */ }
    for (const s of symbols) {
      if (data[s] || errors[s]) continue;
      getJSON(`/api/py/stock/${s}/analysis?news=false`).then((d) => setData((x) => ({ ...x, [s]: d })))
        .catch((e) => setErrors((x) => ({ ...x, [s]: String(e.message || e) })));
      getJSON(`/api/py/stock/${s}/price`).then((d) => setPrices((x) => ({ ...x, [s]: d.bars || [] }))).catch(() => undefined);
    }
  }, [symbols, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = () => {
    const next = parseList([...symbols, ...parseList(draft)].join(","));
    setSymbols(next); setDraft("");
  };
  const rows = symbols.filter((s) => data[s]).map((s) => {
    const d = data[s], m = d.metrics || {}, r = d.recommendation || {};
    return { symbol: s, name: d.name, exchange: d.exchange, price: d.price, market_cap: d.market_cap, pe: m.pe, pe_ttm: m.pe_ttm,
      pb: m.pb, roe: m.roe, net_margin: m.net_margin, ni_growth: m.ni_growth, ret_1m: m.ret_1m, ret_3m: m.ret_3m, ret_1y: m.ret_1y,
      rating: r.rating, score: r.total_score, upside: r.upside, ...Object.fromEntries(Object.keys(GROUPS).map((g) => [`g_${g}`, r.scores?.[g]])) };
  });
  const chart = useMemo(() => {
    const cutoff = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
    const byDate: Record<string, any> = {};
    for (const s of symbols) {
      const bars = (prices[s] || []).filter((b) => String(b.time).slice(0, 10) >= cutoff);
      const base = bars[0]?.close;
      if (!base) continue;
      for (const b of bars) { const t = String(b.time).slice(0, 10); (byDate[t] ||= { time: t })[s] = (b.close / base) * 100; }
    }
    return Object.values(byDate).sort((a: any, b: any) => a.time.localeCompare(b.time));
  }, [symbols, prices]);
  const loading = symbols.some((s) => !data[s] && !errors[s]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">So sánh cổ phiếu</h1>
        <p className="text-sm text-slate-600">Lệnh <code>CMP FPT CMG ELC</code> trong thanh lệnh (<kbd>/</kbd>) mở trang này. Tối đa {MAX_COMPARE} mã.</p>
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          {symbols.map((s, i) => (
            <span key={s} className="inline-flex items-center gap-1 rounded-full border border-slate-300 px-2 py-0.5 text-sm">
              <span className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} aria-hidden />
              <Link className="link font-semibold" href={`/stock/${s}`}>{s}</Link>
              <button type="button" aria-label={`Bỏ ${s}`} className="text-slate-500 hover:text-red-700" onClick={() => setSymbols(symbols.filter((x) => x !== s))}>×</button>
            </span>))}
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add(); }}>
            <input className="sel w-40" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Thêm mã: HPG, VNM" aria-label="Thêm mã để so sánh" disabled={symbols.length >= MAX_COMPARE} />
            <button className="btn-ghost" type="submit" disabled={symbols.length >= MAX_COMPARE}>Thêm</button>
          </form>
        </div>
        {Object.entries(errors).filter(([s]) => symbols.includes(s)).map(([s, e]) => <ErrorBox key={s} error={`${s}: ${e}`} />)}
      </Card>
      {symbols.length < 2 && <p className="text-sm text-slate-500">Chọn ít nhất 2 mã để so sánh.</p>}
      {loading && <Loading what="dữ liệu so sánh" />}
      {rows.length > 0 && (
        <Card title="Chỉ số chính">
          <SortTable rows={rows} rowKey={(r) => r.symbol} onRow={(r) => `/stock/${r.symbol}`} tableId="so-sanh" toolbar csvName="so-sanh"
            cols={[
              { key: "symbol", label: "Mã" },
              { key: "price", label: "Giá", num: true, render: (r) => price(r.price) },
              { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
              { key: "pe", label: "P/E FY", num: true, render: (r) => times(r.pe) },
              { key: "pe_ttm", label: "P/E TTM", num: true, render: (r) => times(r.pe_ttm) },
              { key: "pb", label: "P/B", num: true, render: (r) => times(r.pb, 2) },
              { key: "roe", label: "ROE", num: true, render: (r) => pct(r.roe) },
              { key: "net_margin", label: "Biên LN", num: true, render: (r) => pct(r.net_margin) },
              { key: "ni_growth", label: "Tăng LN", num: true, render: (r) => <span className={cls(r.ni_growth)}>{pct(r.ni_growth)}</span> },
              { key: "ret_1m", label: "1T", num: true, render: (r) => <span className={cls(r.ret_1m)}>{pct(r.ret_1m)}</span> },
              { key: "ret_3m", label: "3T", num: true, render: (r) => <span className={cls(r.ret_3m)}>{pct(r.ret_3m)}</span> },
              { key: "ret_1y", label: "1N", num: true, render: (r) => <span className={cls(r.ret_1y)}>{pct(r.ret_1y)}</span> },
              { key: "rating", label: "Khuyến nghị", render: (r) => r.rating ? <span className={`rounded px-1.5 py-0.5 text-xs text-white ${RATING_COLOR[r.rating] || "bg-slate-500"}`}>{r.rating}</span> : "–" },
              { key: "score", label: "Điểm", num: true, render: (r) => num(r.score, 0) },
              { key: "upside", label: "Upside", num: true, render: (r) => <span className={cls(r.upside)}>{pct(r.upside)}</span> },
              ...Object.entries(GROUPS).map(([g, label]) => ({ key: `g_${g}`, label, num: true, render: (r: any) => num(r[`g_${g}`], 0) })),
            ]} />
        </Card>)}
      {chart.length > 0 && (
        <Card title="Giá 1 năm (gốc = 100)">
          <CompareLine data={chart} lines={symbols.map((s, i) => ({ key: s, name: s, color: COLORS[i % COLORS.length] }))} height={300} />
        </Card>)}
    </div>
  );
}
