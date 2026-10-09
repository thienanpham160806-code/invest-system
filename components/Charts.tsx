"use client";
import { useEffect, useRef } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
  BarChart, Bar, Cell, ReferenceLine,
} from "recharts";
import { num, pct } from "@/lib/fmt";

export function CompareLine({ data, lines, height = 260 }: { data: any[]; lines: { key: string; name: string; color: string }[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
        <XAxis dataKey="time" tickFormatter={(t) => String(t).slice(5, 10)} minTickGap={40} fontSize={11} />
        <YAxis domain={["auto", "auto"]} fontSize={11} width={45} tickFormatter={(v) => num(v, 0)} />
        <Tooltip formatter={(v: any) => num(v, 1)} labelFormatter={(l) => String(l).slice(0, 10)} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {lines.map((l) => <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} dot={false} strokeWidth={l.key === "sector" || l.key === "stock" ? 2 : 1.5} isAnimationActive={false} />)}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function PbRoeScatter({ rows, highlight, height = 320 }: { rows: any[]; highlight?: string; height?: number }) {
  const pts = rows.filter((r) => r.pb > 0 && r.pb < 10 && r.roe !== null && r.roe > -0.5 && r.roe < 0.8)
    .map((r) => ({ x: r.roe * 100, y: r.pb, z: Math.max(r.market_cap || 0, 1), symbol: r.symbol }));
  const me = pts.filter((p) => p.symbol === highlight);
  const others = pts.filter((p) => p.symbol !== highlight);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 0 }}>
        <CartesianGrid stroke="#e2e8f0" />
        <XAxis type="number" dataKey="x" name="ROE" unit="%" fontSize={11} label={{ value: "ROE (%)", position: "insideBottom", offset: -10, fontSize: 11 }} />
        <YAxis type="number" dataKey="y" name="P/B" fontSize={11} width={40} />
        <ZAxis type="number" dataKey="z" range={[20, 400]} />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => payload?.[0] ? (
          <div className="bg-white border rounded px-2 py-1 text-xs shadow">{payload[0].payload.symbol}: ROE {num(payload[0].payload.x, 1)}%, P/B {num(payload[0].payload.y, 2)}</div>) : null} />
        <Scatter data={others} fill="#94a3b8" fillOpacity={0.6} isAnimationActive={false} />
        <Scatter data={me} fill="#dc2626" isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function Histogram({ values, highlight, label, bins = 12, height = 200 }: { values: number[]; highlight?: number | null; label: string; bins?: number; height?: number }) {
  const v = values.filter((x) => Number.isFinite(x));
  if (v.length < 3) return <div className="text-sm text-slate-500">Không đủ dữ liệu {label}</div>;
  const lo = Math.min(...v), hi = Math.max(...v), w = (hi - lo) / bins || 1;
  const data = Array.from({ length: bins }, (_, i) => ({ x: lo + w * (i + 0.5), n: 0, from: lo + w * i, to: lo + w * (i + 1) }));
  v.forEach((x) => { data[Math.min(bins - 1, Math.floor((x - lo) / w))].n++; });
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
        <XAxis dataKey="x" tickFormatter={(x) => num(x, 1)} fontSize={10} />
        <YAxis allowDecimals={false} fontSize={10} width={28} />
        <Tooltip formatter={(n: any) => [n, "số mã"]} labelFormatter={(_, p: any) => p?.[0] ? `${label} ${num(p[0].payload.from, 1)}–${num(p[0].payload.to, 1)}` : ""} />
        <Bar dataKey="n" isAnimationActive={false}>
          {data.map((d, i) => <Cell key={i} fill={highlight !== undefined && highlight !== null && highlight >= d.from && highlight <= d.to ? "#dc2626" : "#0b3b6f"} />)}
        </Bar>
        {highlight !== undefined && highlight !== null && <ReferenceLine x={highlight} stroke="#dc2626" />}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ScoreBars({ scores, labels }: { scores: Record<string, number | null>; labels: Record<string, string> }) {
  return (
    <div className="space-y-1.5">
      {Object.entries(labels).map(([k, l]) => {
        const v = scores?.[k];
        return (
          <div key={k} className="flex items-center gap-2 text-sm">
            <div className="w-28 shrink-0 text-slate-600">{l}</div>
            <div className="flex-1 h-2.5 rounded bg-slate-100 overflow-hidden">
              {v !== null && v !== undefined && <div className="h-full rounded" style={{ width: `${v}%`, background: v >= 60 ? "#059669" : v >= 40 ? "#f59e0b" : "#dc2626" }} />}
            </div>
            <div className="w-10 text-right tabular-nums">{v === null || v === undefined ? "–" : num(v, 0)}</div>
          </div>);
      })}
    </div>
  );
}

export function Candles({ bars, height = 380 }: { bars: any[]; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current || !bars?.length) return;
    let chart: any;
    let cancelled = false;
    import("lightweight-charts").then((lw: any) => {
      if (cancelled || !ref.current) return;
      chart = lw.createChart(ref.current, { height, layout: { textColor: "#334155", background: { color: "#ffffff" } }, grid: { vertLines: { color: "#f1f5f9" }, horzLines: { color: "#f1f5f9" } }, timeScale: { borderColor: "#cbd5e1" }, rightPriceScale: { borderColor: "#cbd5e1" } });
      const opts = { upColor: "#16a34a", downColor: "#dc2626", borderVisible: false, wickUpColor: "#16a34a", wickDownColor: "#dc2626" };
      const series = lw.CandlestickSeries ? chart.addSeries(lw.CandlestickSeries, opts) : chart.addCandlestickSeries(opts);
      const seen = new Set<string>();
      const data = bars.map((b) => ({ time: String(b.time).slice(0, 10), open: b.open, high: b.high, low: b.low, close: b.close }))
        .filter((b) => b.close && !seen.has(b.time) && seen.add(b.time));
      series.setData(data);
      const vopts = { priceScaleId: "", color: "#94a3b8", priceFormat: { type: "volume" } };
      const vol = lw.HistogramSeries ? chart.addSeries(lw.HistogramSeries, vopts) : chart.addHistogramSeries(vopts);
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      const vs = new Set<string>();
      vol.setData(bars.map((b) => ({ time: String(b.time).slice(0, 10), value: b.volume || 0, color: b.close >= b.open ? "#86efac" : "#fca5a5" })).filter((b) => !vs.has(b.time) && vs.add(b.time)));
      chart.timeScale().fitContent();
    });
    return () => { cancelled = true; chart?.remove(); };
  }, [bars, height]);
  return <div ref={ref} className="w-full" />;
}

export function pctTick(v: number) { return pct(v, 0); }
