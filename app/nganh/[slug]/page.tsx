"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { CompareLine, Histogram, PbRoeScatter } from "@/components/Charts";
import { AsOf, Card, ErrorBox, Loading, SortTable, Stat } from "@/components/ui";
import { downloadCSV, toCSV, useApi } from "@/lib/api";
import { bnLabel, cls, num, pct, price, times } from "@/lib/fmt";

const CSV_COLS = [
  { key: "symbol", label: "Mã" }, { key: "name", label: "Tên" }, { key: "exchange", label: "Sàn" }, { key: "icb4", label: "ICB4" },
  { key: "price", label: "Giá" }, { key: "market_cap", label: "Vốn hoá (VND)" }, { key: "pe", label: "P/E" }, { key: "pb", label: "P/B" },
  { key: "roe", label: "ROE" }, { key: "net_margin", label: "Biên ròng" }, { key: "ni_growth", label: "Tăng trưởng LN" },
  { key: "ret_1m", label: "1T" }, { key: "ret_ytd", label: "YTD" }, { key: "ret_1y", label: "1N" }, { key: "avg_value_20d", label: "GTGD TB20 (VND)" },
  { key: "fin_year", label: "Năm BCTC" }, { key: "as_of_price", label: "Ngày giá" },
];

export default function SectorPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data, error, loading } = useApi<any>(`/api/py/sectors/${slug}`);
  const [exch, setExch] = useState("");
  const [liquidOnly, setLiquidOnly] = useState(false);
  const members = useMemo(() => (data?.members || []).filter((r: any) => (!exch || r.exchange === exch) && (!liquidOnly || r.liquidity_flag)), [data, exch, liquidOnly]);
  if (loading) return <Loading what="ngành" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const s = data.stats;
  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-500">
        <Link className="link" href="/nganh">Ngành</Link>
        {data.parents.map((p: any) => <span key={p.slug}> / <Link className="link" href={`/nganh/${p.slug}`}>{p.name}</Link></span>)} / <b>{data.name}</b>
      </div>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-xl font-bold">{data.name} <span className="text-sm font-normal text-slate-500">ICB cấp {data.level} · {s.n_symbols} mã</span></h1>
        <AsOf p={data.provenance} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="Vốn hoá" value={bnLabel(s.market_cap)} sub={`${pct(s.market_weight, 2)} thị trường`} />
        <Stat label="GTGD TB20" value={num(s.avg_value_20d / 1e9, 0) + " tỷ"} sub={`${s.n_liquid} mã đủ thanh khoản`} />
        <Stat label="P/E trung vị" value={times(s.pe?.median)} sub={`P25–P75: ${times(s.pe?.p25)}–${times(s.pe?.p75)}`} />
        <Stat label="P/E gộp" value={times(s.pe_aggregate)} sub="Σ vốn hoá / Σ LNST" />
        <Stat label="P/B trung vị" value={times(s.pb?.median, 2)} sub={`ROE TV ${pct(s.roe?.median)}`} />
        <Stat label="Điểm ngành" value={num(data.score?.score, 0) + "/100"} sub={Object.entries(data.score?.components || {}).map(([k, v]: any) => `${k} ${num(v, 0)}`).join(" · ")} />
      </div>
      <div className="grid md:grid-cols-3 gap-4">
        <Card title="Chỉ số ngành (cap-weighted, =100) vs VN-Index" className="md:col-span-2">
          <CompareLine data={data.index_series} lines={[{ key: "sector", name: data.name, color: "#dc2626" }, { key: "vnindex", name: "VN-Index", color: "#0b3b6f" }]} />
          <div className="text-sm flex flex-wrap gap-4 mt-2">
            {["ret_1m", "ret_3m", "ret_ytd", "ret_1y"].map((k) => (
              <span key={k}>{({ ret_1m: "1T", ret_3m: "3T", ret_ytd: "YTD", ret_1y: "1N" } as any)[k]}: <b className={cls(s[k])}>{pct(s[k])}</b> <span className="text-slate-500">(VNI {pct(data.benchmark[k])})</span></span>
            ))}
          </div>
        </Card>
        <Card title="Phân phối P/E & P/B (mã đủ thanh khoản)">
          <Histogram values={members.filter((r: any) => r.liquidity_flag && r.pe > 0 && r.pe <= 100).map((r: any) => r.pe)} label="P/E" height={140} />
          <Histogram values={members.filter((r: any) => r.liquidity_flag && r.pb > 0 && r.pb <= 20).map((r: any) => r.pb)} label="P/B" height={140} />
        </Card>
      </div>
      {data.children.length > 0 && (
        <Card title="Ngành con">
          <div className="flex flex-wrap gap-2">
            {data.children.map((c: any) => <Link key={c.slug} href={`/nganh/${c.slug}`} className="btn-ghost">{c.name} <span className="text-slate-500">({c.n_symbols})</span></Link>)}
          </div>
        </Card>
      )}
      <Card title="Định vị P/B – ROE toàn ngành">
        <PbRoeScatter rows={data.members} />
      </Card>
      <Card title={`Tất cả mã trong ngành (${members.length}/${data.members.length})`}
        right={<div className="flex gap-2 items-center text-sm">
          <select className="sel" value={exch} onChange={(e) => setExch(e.target.value)}>
            <option value="">Mọi sàn</option><option>HOSE</option><option>HNX</option><option>UPCOM</option>
          </select>
          <label><input type="checkbox" checked={liquidOnly} onChange={(e) => setLiquidOnly(e.target.checked)} /> Chỉ mã đủ thanh khoản</label>
          <button className="btn" onClick={() => downloadCSV(`nganh_${slug}.csv`, toCSV(members, CSV_COLS))}>Tải CSV</button>
        </div>}>
        <SortTable rows={members} rowKey={(r) => r.symbol} initialSort="market_cap" onRow={(r) => `/stock/${r.symbol}`}
          cols={[
            { key: "symbol", label: "Mã" },
            { key: "name", label: "Tên DN", render: (r) => <span className="inline-block max-w-56 truncate align-bottom" title={r.name}>{r.name}</span> },
            { key: "exchange", label: "Sàn" },
            { key: "icb4", label: "ICB4" },
            { key: "price", label: "Giá", num: true, render: (r) => price(r.price) },
            { key: "change_1d", label: "±1N", num: true, render: (r) => <span className={cls(r.change_1d)}>{pct(r.change_1d, 1)}</span> },
            { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
            { key: "pe", label: "P/E", num: true, render: (r) => times(r.pe) },
            { key: "pb", label: "P/B", num: true, render: (r) => times(r.pb, 2) },
            { key: "roe", label: "ROE", num: true, render: (r) => pct(r.roe) },
            { key: "net_margin", label: "Biên ròng", num: true, render: (r) => pct(r.net_margin) },
            { key: "ni_growth", label: "Tăng LN", num: true, render: (r) => <span className={cls(r.ni_growth)}>{pct(r.ni_growth)}</span> },
            { key: "ret_ytd", label: "YTD", num: true, render: (r) => <span className={cls(r.ret_ytd)}>{pct(r.ret_ytd)}</span> },
            { key: "avg_value_20d", label: "GTGD TB20", num: true, render: (r) => num(r.avg_value_20d / 1e9, 1) + " tỷ" },
            { key: "fin_year", label: "BCTC", render: (r) => r.fin_year ? `FY${r.fin_year}` : <span className="text-slate-400">chưa có</span> },
          ]} />
      </Card>
    </div>
  );
}
