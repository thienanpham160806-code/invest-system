"use client";
import { useMemo, useState } from "react";
import { AsOf, Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { useApi } from "@/lib/api";
import { bnLabel, cls, num, pct, times } from "@/lib/fmt";

export default function Nganh() {
  const [level, setLevel] = useState(2);
  const [minSymbols, setMinSymbols] = useState(0);
  const [minCap, setMinCap] = useState(0);
  const [minLiquid, setMinLiquid] = useState(0);
  const [parent, setParent] = useState("");
  const { data, error, loading } = useApi<any>(`/api/py/sectors?level=${level}`);
  const rows = useMemo(() => (data?.items || []).filter((r: any) =>
    r.n_symbols >= minSymbols && r.market_cap >= minCap * 1e12 && r.n_liquid >= minLiquid && (!parent || r.icb1 === parent)), [data, minSymbols, minCap, minLiquid, parent]);
  const parents = useMemo(() => Array.from(new Set((data?.items || []).map((r: any) => r.icb1).filter(Boolean))) as string[], [data]);
  const b = data?.benchmark || {};
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">Phân tích ngành – toàn thị trường</h1>
          <p className="text-sm text-slate-600">Mọi nút ICB cấp 1–4, tổng hợp từ <b>tất cả</b> mã trong ngành (không chỉ vài mã đại diện).</p>
        </div>
        <AsOf p={data?.provenance} />
      </div>
      <Card>
        <div className="flex flex-wrap gap-3 items-center text-sm">
          <label>Cấp ICB{" "}
            <select className="sel" value={level} onChange={(e) => setLevel(+e.target.value)}>
              {[1, 2, 3, 4].map((l) => <option key={l} value={l}>Cấp {l}</option>)}
            </select>
          </label>
          {level > 1 && (
            <label>Thuộc ngành cấp 1{" "}
              <select className="sel" value={parent} onChange={(e) => setParent(e.target.value)}>
                <option value="">Tất cả</option>
                {parents.map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
          )}
          <label>Số mã ≥ <input className="sel w-16" type="number" value={minSymbols} onChange={(e) => setMinSymbols(+e.target.value)} /></label>
          <label>Vốn hoá ≥ <input className="sel w-20" type="number" value={minCap} onChange={(e) => setMinCap(+e.target.value)} /> nghìn tỷ</label>
          <label>Mã đủ thanh khoản ≥ <input className="sel w-16" type="number" value={minLiquid} onChange={(e) => setMinLiquid(+e.target.value)} /></label>
        </div>
        {data && (
          <div className="mt-3 text-xs text-slate-600 space-y-0.5">
            <div>
              Phủ ngành: <b>{num(data.coverage.n_classified)}/{num(data.coverage.n_symbols)}</b> mã đã phân ngành ({pct(data.coverage.n_classified / data.coverage.n_symbols, 1)}),
              tổng số mã các nút = {num(data.coverage.sum_nodes)} · nguồn ICB: {Object.entries(data.coverage.industry_source).map(([k, v]) => `${k} ${v}`).join(", ")}
            </div>
            <div>VN-Index: 1T <span className={cls(b.ret_1m)}>{pct(b.ret_1m)}</span> · 3T <span className={cls(b.ret_3m)}>{pct(b.ret_3m)}</span> · YTD <span className={cls(b.ret_ytd)}>{pct(b.ret_ytd)}</span> · 1N <span className={cls(b.ret_1y)}>{pct(b.ret_1y)}</span></div>
            {Object.values(data.method).map((m: any) => <div key={m}>• {m}</div>)}
          </div>
        )}
      </Card>
      <Card title={`${rows.length} ngành cấp ${level}`}>
        <ErrorBox error={error} />
        {loading && <Loading what="ngành" />}
        {data && (
          <SortTable rows={rows} rowKey={(r) => r.slug} initialSort="market_cap" onRow={(r) => `/nganh/${r.slug}`}
            cols={[
              { key: "name", label: "Ngành" },
              ...(level > 1 ? [{ key: "icb1", label: "Cấp 1" }] : []),
              { key: "n_symbols", label: "Số mã", num: true },
              { key: "n_liquid", label: "Đủ TK", num: true, title: "GTGD TB 20 phiên ≥ 1 tỷ" },
              { key: "market_cap", label: "Vốn hoá", num: true, render: (r: any) => bnLabel(r.market_cap) },
              { key: "market_weight", label: "Tỷ trọng", num: true, render: (r: any) => pct(r.market_weight, 2) },
              { key: "avg_value_20d", label: "GTGD TB20", num: true, render: (r: any) => num(r.avg_value_20d / 1e9, 0) + " tỷ" },
              { key: "ret_1m", label: "1T", num: true, render: (r: any) => <span className={cls(r.ret_1m)}>{pct(r.ret_1m)}</span> },
              { key: "ret_3m", label: "3T", num: true, render: (r: any) => <span className={cls(r.ret_3m)}>{pct(r.ret_3m)}</span> },
              { key: "ret_ytd", label: "YTD", num: true, render: (r: any) => <span className={cls(r.ret_ytd)}>{pct(r.ret_ytd)}</span> },
              { key: "ret_1y", label: "1N", num: true, render: (r: any) => <span className={cls(r.ret_1y)}>{pct(r.ret_1y)}</span> },
              { key: "ret_3m_vs_index", label: "3T vs VNI", num: true, render: (r: any) => <span className={cls(r.ret_3m_vs_index)}>{pct(r.ret_3m_vs_index, 1, true)}</span> },
              { key: "pe", label: "P/E TV", num: true, sortValue: (r: any) => r.pe?.median, render: (r: any) => times(r.pe?.median) },
              { key: "pe_aggregate", label: "P/E gộp", num: true, render: (r: any) => times(r.pe_aggregate) },
              { key: "pb", label: "P/B TV", num: true, sortValue: (r: any) => r.pb?.median, render: (r: any) => times(r.pb?.median, 2) },
              { key: "roe", label: "ROE TV", num: true, sortValue: (r: any) => r.roe?.median, render: (r: any) => pct(r.roe?.median) },
              { key: "score", label: "Điểm", num: true, render: (r: any) => num(r.score, 0) },
              { key: "rank_score", label: "Hạng", num: true },
            ]} />
        )}
      </Card>
    </div>
  );
}
