"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useState } from "react";
import { Candles, CompareLine, Histogram, PbRoeScatter, ScoreBars } from "@/components/Charts";
import { AsOf, Card, ErrorBox, Loading, SortTable, Stat, Tabs } from "@/components/ui";
import Sensitivity from "@/components/Sensitivity";
import { downloadCSV, toCSV, useApi } from "@/lib/api";
import { bnLabel, cls, dmy, fmtKind, num, pct, price, RATING_COLOR, times } from "@/lib/fmt";

const SCORE_LABELS: Record<string, string> = {
  macro: "Vĩ mô", sector: "Ngành", quality: "Chất lượng", growth: "Tăng trưởng",
  valuation: "Định giá", technical: "Kỹ thuật", sentiment: "Tin tức",
};
const TABS = [
  { key: "overview", label: "Tổng quan" }, { key: "macro", label: "Vĩ mô" }, { key: "sector", label: "Ngành" },
  { key: "bctc", label: "BCTC" }, { key: "ratios", label: "Chỉ số tài chính" }, { key: "valuation", label: "Định giá" },
  { key: "technical", label: "Kỹ thuật" }, { key: "news", label: "Tin tức" }, { key: "docs", label: "Tài liệu BCTN" },
  { key: "data", label: "Dữ liệu & nguồn" },
];

export default function StockPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const t = String(ticker).toUpperCase();
  const [tab, setTab] = useState("overview");
  const a = useApi<any>(`/api/py/stock/${t}/analysis?news=false`);
  const d = a.data;
  return (
    <div className="space-y-4">
      <ErrorBox error={a.error} />
      {a.loading && <Loading what={`phân tích ${t}`} />}
      {d && (
        <>
          <div className="card">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h1 className="text-2xl font-bold">{d.symbol} <span className="text-base font-normal text-slate-600">{d.name}</span></h1>
                <div className="text-sm text-slate-600">
                  {d.exchange} · {d.company_type_label} · ICB:{" "}
                  {[1, 2, 3, 4].map((l) => <span key={l}>{l > 1 && " › "}<Link className="link" href={`/nganh/${d.icb_slugs["icb" + l]}`}>{d.icb["icb" + l]}</Link></span>)}
                </div>
                <div className="mt-1"><AsOf p={d.sources?.[1]} label="Giá đến" /> {d.bctc_available ? <AsOf p={d.sources?.[3]} label="BCTC" /> : <span className="asof !bg-amber-50 !border-amber-200 !text-amber-800">BCTC: chưa có nguồn cho mã này (arminer chỉ phủ HSX/HNX)</span>}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-3xl font-bold tabular-nums">{price(d.price)}</div>
                  <div className={`text-sm ${cls(d.metrics.ret_1m)}`}>1T {pct(d.metrics.ret_1m, 1, true)} · YTD {pct(d.metrics.ret_ytd, 1, true)}</div>
                </div>
                {d.recommendation.rating && (
                  <div className={`rounded-md text-white px-4 py-2 text-center ${RATING_COLOR[d.recommendation.rating] || "bg-slate-500"}`}>
                    <div className="text-xs opacity-80">Khuyến nghị</div>
                    <div className="text-lg font-bold">{d.recommendation.rating}</div>
                  </div>
                )}
                <Link href={`/report/${d.symbol}`} className="btn">Báo cáo PDF</Link>
              </div>
            </div>
          </div>
          <Tabs tabs={TABS} active={tab} onChange={setTab} />
          {tab === "overview" && <Overview d={d} />}
          {tab === "macro" && <MacroTab ctype={d.company_type} />}
          {tab === "sector" && <SectorTab d={d} />}
          {tab === "bctc" && <BctcTab t={t} />}
          {tab === "ratios" && <RatiosTab t={t} />}
          {tab === "valuation" && <><ValuationTab d={d} /><Sensitivity d={d} /></>}
          {tab === "technical" && <TechTab d={d} t={t} />}
          {tab === "news" && <NewsTab t={t} />}
          {tab === "docs" && <DocsTab t={t} />}
          {tab === "data" && <DataTab d={d} />}
        </>
      )}
    </div>
  );
}

function Overview({ d }: { d: any }) {
  const r = d.recommendation;
  const m = d.metrics;
  return (
    <div className="grid md:grid-cols-3 gap-4">
      <Card title="Khuyến nghị & định giá" className="md:col-span-2">
        {!d.bctc_available && <div className="rounded bg-amber-50 border border-amber-200 text-amber-800 text-sm p-2 mb-3">Chưa có nguồn BCTC cho mã này (bộ BCTC arminer chỉ phủ HSX/HNX) → chưa định giá cơ bản. Giá và ngành vẫn có đầy đủ.</div>}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Stat label="Giá mục tiêu (cơ sở)" value={price(r.target_price)} sub={`Bi quan ${price(r.targets?.bear)} · Lạc quan ${price(r.targets?.bull)}`} />
          <Stat label="Upside" value={<span className={cls(r.upside)}>{pct(r.upside, 1, true)}</span>} />
          <Stat label="Điểm tổng hợp" value={num(r.total_score, 0) + "/100"} sub={r.base_rating && r.base_rating !== r.rating ? `Theo upside: ${r.base_rating}` : undefined} />
          <Stat label="Vốn hoá" value={bnLabel(d.market_cap)} sub={d.shares_source} />
          <Stat label={`P/E FY${m.fin_year || ""}${m.pe_ttm ? " · " + m.ttm_label : ""}`} value={<>{times(m.pe)}{m.pe_ttm ? <span className="text-slate-500"> · {times(m.pe_ttm)}</span> : null}</>} sub={d.eps_basis} />
          <Stat label="P/B" value={times(m.pb, 2)} />
          <Stat label="ROE" value={pct(m.roe)} />
          <Stat label="Tăng trưởng LN" value={<span className={cls(m.ni_growth)}>{pct(m.ni_growth, 1, true)}</span>} sub={m.fin_year ? `FY${m.fin_year} vs FY${m.fin_year - 1}` : ""} />
        </div>
        {r.reason && <p className="text-sm text-slate-600 mt-3">{r.reason}</p>}
        <div className="grid md:grid-cols-2 gap-4 mt-4">
          <div>
            <h3 className="font-semibold text-emerald-700 mb-1">Luận điểm đầu tư</h3>
            <ul className="list-disc pl-5 text-sm space-y-1">{d.thesis.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
          </div>
          <div>
            <h3 className="font-semibold text-red-700 mb-1">Rủi ro</h3>
            <ul className="list-disc pl-5 text-sm space-y-1">{d.risks.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
          </div>
        </div>
      </Card>
      <Card title="Điểm 7 nhóm (0–100)">
        <ScoreBars scores={r.scores} labels={SCORE_LABELS} />
        <p className="text-xs text-slate-500 mt-3">Trọng số dùng: {Object.entries(r.weights || {}).map(([k, v]: any) => `${SCORE_LABELS[k]} ${pct(v, 0)}`).join(", ")}. Nhóm thiếu dữ liệu được loại và chuẩn hoá lại trọng số. Điểm tin tức chỉ tính ở tab Tin tức/PDF.</p>
        <p className="text-xs text-slate-500 mt-2">{d.sector.note}</p>
      </Card>
    </div>
  );
}

function MacroTab({ ctype }: { ctype: string }) {
  const { data, error, loading } = useApi<any>(`/api/py/macro?company_type=${ctype}`);
  if (loading) return <Loading what="vĩ mô" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const hist = data.history || {};
  const series = (k: string) => (hist[k] || []).map((x: any) => ({ time: String(x.year), v: x.value }));
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card title="Chỉ tiêu vĩ mô (kèm nguồn)" right={<AsOf p={data.provenance} label="Cập nhật" />} className="md:col-span-2">
        <SortTable rows={data.table} rowKey={(r) => r.key + r.period}
          cols={[
            { key: "label", label: "Chỉ tiêu" }, { key: "period", label: "Kỳ" },
            { key: "value", label: "Giá trị", num: true, render: (r) => (r.unit === "VND" ? num(r.value) : num(r.value, 2)) + " " + r.unit },
            { key: "as_of", label: "Công bố", render: (r) => dmy(r.as_of) },
            { key: "source", label: "Nguồn", render: (r) => { const u = (String(r.source).match(/https?:[^)\s]+/) || [])[0]; return <span className="whitespace-normal text-xs">{String(r.source).replace(/\(https?:[^)]+\)/, "")} {u && <a className="link" href={u} target="_blank" rel="noreferrer">[link]</a>}</span>; } },
          ]} />
      </Card>
      <Card title="Đánh giá & tác động lên ngành">
        <div className="flex gap-2 mb-2"><Stat label="Điểm vĩ mô chung" value={num(data.score, 0)} /><Stat label="Tác động lên nhóm DN này" value={num(data.sector_score, 0)} /></div>
        <ul className="list-disc pl-5 text-sm space-y-1">{data.commentary.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
        <div className="text-xs text-slate-500 mt-2">Tác động theo loại DN: {Object.entries(data.sector_impact).map(([k, v]: any) => `${k} ${num(v, 0)}`).join(" · ")} (ma trận độ nhạy config/sector_map.yaml)</div>
      </Card>
      <Card title="Chuỗi lịch sử (World Bank + số nhập tay theo năm)">
        <CompareLine data={series("gdp_growth").map((g: any) => ({ time: g.time, gdp: g.v, cpi: series("cpi").find((c: any) => c.time === g.time)?.v }))}
          lines={[{ key: "gdp", name: "GDP %", color: "#0b3b6f" }, { key: "cpi", name: "CPI %", color: "#dc2626" }]} height={220} />
      </Card>
    </div>
  );
}

function SectorTab({ d }: { d: any }) {
  const s = d.sector;
  const peers = s.peers || [];
  const me = peers.find((p: any) => p.symbol === d.symbol) || {};
  return (
    <div className="space-y-4">
      <Card title={`So sánh trong ngành – ICB cấp ${s.level}: ${s.name}`} right={<Link className="link text-sm" href={`/nganh/${s.slug}`}>Trang ngành →</Link>}>
        <p className="text-sm text-slate-600 mb-3">{s.note}. Peers = toàn bộ mã cùng ICB4; dưới 5 mã đủ thanh khoản thì lùi lên ICB3 → ICB2 → ICB1.</p>
        <div className="grid grid-cols-2 md:grid-cols-7 gap-2">
          {["pe", "pb", "roe", "net_margin", "ni_growth", "ret_1y", "market_cap"].map((k) => (
            <Stat key={k} label={`Phân vị ${({ pe: "P/E", pb: "P/B", roe: "ROE", net_margin: "Biên ròng", ni_growth: "Tăng LN", ret_1y: "Giá 1N", market_cap: "Vốn hoá" } as any)[k]}`}
              value={s.position?.[k] !== undefined ? pct(s.position[k], 0) : "–"}
              sub={k === "market_cap" ? bnLabel(me[k]) : ["pe", "pb"].includes(k) ? times(me[k], 2) : pct(me[k])} />
          ))}
        </div>
        <div className="text-xs text-slate-500 mt-2">Trung vị ngành (mã đủ thanh khoản): P/E {times(s.quantiles?.pe?.[1])}, P/B {times(s.quantiles?.pb?.[1], 2)}, ROE {pct(s.quantiles?.roe?.[1])}, EV/EBITDA {times(s.quantiles?.ev_ebitda?.[1])}</div>
      </Card>
      <div className="grid md:grid-cols-2 gap-4">
        <Card title="P/B – ROE cả ngành (đỏ = mã đang xem)"><PbRoeScatter rows={peers} highlight={d.symbol} /></Card>
        <Card title="Phân phối P/E ngành (đỏ = mã đang xem)">
          <Histogram values={peers.filter((r: any) => r.liquidity_flag && r.pe > 0 && r.pe <= 100).map((r: any) => r.pe)} highlight={me.pe} label="P/E" height={280} />
        </Card>
      </div>
      <Card title={`Toàn bộ ${peers.length} mã so sánh`}>
        <SortTable rows={peers} rowKey={(r) => r.symbol} initialSort="market_cap" onRow={(r) => `/stock/${r.symbol}`} highlight={(r) => r.symbol === d.symbol} maxRows={200}
          cols={[
            { key: "symbol", label: "Mã" }, { key: "exchange", label: "Sàn" }, { key: "icb4", label: "ICB4" },
            { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
            { key: "pe", label: "P/E", num: true, render: (r) => times(r.pe) }, { key: "pb", label: "P/B", num: true, render: (r) => times(r.pb, 2) },
            { key: "ev_ebitda", label: "EV/EBITDA", num: true, render: (r) => times(r.ev_ebitda) },
            { key: "roe", label: "ROE", num: true, render: (r) => pct(r.roe) }, { key: "ni_growth", label: "Tăng LN", num: true, render: (r) => pct(r.ni_growth) },
            { key: "ret_1y", label: "Giá 1N", num: true, render: (r) => <span className={cls(r.ret_1y)}>{pct(r.ret_1y)}</span> },
            { key: "liquidity_flag", label: "Đủ TK", render: (r) => (r.liquidity_flag ? "✓" : "") },
          ]} />
      </Card>
    </div>
  );
}

function BctcTab({ t, years: y0 = 5 }: { t: string; years?: number }) {
  const [st, setSt] = useState("is");
  const [years, setYears] = useState(y0);
  const [mode, setMode] = useState<"values" | "common" | "yoy">("values");
  const { data, error, loading } = useApi<any>(`/api/py/stock/${t}/financials?statement=${st}&years=${years}`);
  const ys: number[] = data?.years || [];
  const csv = () => downloadCSV(`${t}_${st}.csv`, toCSV(data.rows.map((r: any) => ({ item_code: r.item_code, item_name: r.item_name, ...Object.fromEntries(ys.map((y) => [y, r.values[y]])) })),
    [{ key: "item_code", label: "item_code" }, { key: "item_name", label: "Chỉ tiêu" }, ...ys.map((y) => ({ key: String(y), label: `FY${y} (VND)` }))]));
  return (
    <Card title="Báo cáo tài chính năm (hợp nhất)" right={<span className="flex flex-wrap gap-2 items-center">
      <select className="sel" value={st} onChange={(e) => setSt(e.target.value)}><option value="is">Kết quả kinh doanh</option><option value="bs">Cân đối kế toán</option><option value="cf">Lưu chuyển tiền tệ</option></select>
      <select className="sel" value={years} onChange={(e) => setYears(+e.target.value)}>{[3, 5, 8, 10].map((n) => <option key={n} value={n}>{n} năm</option>)}</select>
      <select className="sel" value={mode} onChange={(e) => setMode(e.target.value as any)}><option value="values">Giá trị (tỷ đồng)</option><option value="common">% theo quy mô</option><option value="yoy">YoY</option></select>
      {data?.rows?.length > 0 && <button className="btn" onClick={csv}>Tải CSV</button>}
      <AsOf p={data?.provenance} />
    </span>}>
      <ErrorBox error={error} />
      {loading && <Loading what="BCTC" />}
      {data && !data.rows.length && <div className="text-sm text-amber-700">{data.note}</div>}
      {data?.rows?.length > 0 && (
        <>
          <div className="text-xs text-slate-500 mb-2">Đơn vị: tỷ đồng. Tên chỉ tiêu tiếng Việt gốc của nguồn. {mode === "common" && `% theo quy mô: chia cho "${data.common_size_base || "–"}".`} Ẩn các dòng = 0 ở mọi năm (mẫu biểu chung của nguồn).</div>
          <div className="overflow-x-auto max-h-[70vh]">
            <table className="tbl">
              <thead className="sticky top-0"><tr><th>Chỉ tiêu</th>{ys.map((y) => <th key={y} className="text-right">FY{y}</th>)}</tr></thead>
              <tbody>
                {data.rows.map((r: any, i: number) => (
                  <Fragment key={r.item_code}>
                    {(i === 0 || data.rows[i - 1].group !== r.group) && (
                      <tr><td colSpan={ys.length + 1} className="bg-sky-50 font-semibold text-[#0b3b6f]">{r.group === "key" ? "Chỉ tiêu chính (trình tự chuẩn)" : "Chi tiết khác (theo tên chỉ tiêu của nguồn)"}</td></tr>
                    )}
                    <tr className={r.group === "key" ? "font-medium" : ""}>
                      <td title={`${r.item_code}${r.std_label ? " → " + r.std_label : ""}`} className="whitespace-normal min-w-64">{r.item_name}</td>
                      {ys.map((y) => {
                        const v = mode === "values" ? r.values[y] : mode === "common" ? r.common_size[y] : r.yoy[y];
                        return <td key={y} className={`text-right tabular-nums ${mode === "yoy" ? cls(v) : ""}`}>{mode === "values" ? (r.unit === "VND/cp" ? num(v) : num(v / 1e9, 0)) : pct(v, 1)}</td>;
                      })}
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

function RatiosTab({ t }: { t: string }) {
  const { data, error, loading } = useApi<any>(`/api/py/stock/${t}/ratios?years=6`);
  if (loading) return <Loading what="chỉ số" />;
  if (error) return <ErrorBox error={error} />;
  if (!data?.groups?.length) return <div className="card text-sm text-amber-700">{data?.note || "Không có dữ liệu"}</div>;
  return (
    <div className="space-y-4">
      {data.groups.map((g: any) => (
        <Card key={g.title} title={g.title} right={<AsOf p={data.provenance} label="BCTC" />}>
          <div className="overflow-x-auto"><table className="tbl">
            <thead><tr><th>Chỉ số (rê chuột xem công thức)</th>{data.years.map((y: number) => <th key={y} className="text-right">FY{y}</th>)}</tr></thead>
            <tbody>{g.items.map((it: any) => (
              <tr key={it.key}><td title={it.formula} className="cursor-help underline decoration-dotted decoration-slate-300">{it.label}</td>
                {data.years.map((y: number) => <td key={y} className="text-right tabular-nums">{fmtKind(it.values[y], it.kind)}</td>)}</tr>
            ))}</tbody>
          </table></div>
        </Card>
      ))}
      <div className="text-xs text-slate-500">{data.notes?.join(" · ")}</div>
    </div>
  );
}

const METHOD_FALLBACK: Record<string, string> = { pe_relative: "P/E tương đối", pb_relative: "P/B tương đối", ev_ebitda: "EV/EBITDA", dcf_fcff: "DCF FCFF", justified_pb: "P/B hợp lý (Gordon)" };

function ValuationTab({ d }: { d: any }) {
  const v = d.valuation;
  const a = v.assumptions || {};
  return (
    <div className="grid md:grid-cols-3 gap-4">
      <Card title="Các phương pháp định giá" className="md:col-span-2">
        <div className="overflow-x-auto"><table className="tbl">
          <thead><tr><th>Phương pháp</th><th className="text-right">Bi quan</th><th className="text-right">Cơ sở</th><th className="text-right">Lạc quan</th><th className="text-right">Trọng số</th><th>Đầu vào</th></tr></thead>
          <tbody>
            {v.methods.map((m: any) => (
              <tr key={m.key} className={m.weight === 0 ? "text-slate-400" : ""}>
                <td>{m.label || METHOD_FALLBACK[m.key]}{m.note && <div className="text-[11px] text-amber-700 whitespace-normal">{m.note}</div>}</td>
                <td className="text-right tabular-nums">{price(m.values.bear)}</td><td className="text-right tabular-nums font-semibold">{price(m.values.base)}</td><td className="text-right tabular-nums">{price(m.values.bull)}</td>
                <td className="text-right">{pct(m.weight, 0)}</td>
                <td className="text-xs whitespace-normal">{Object.entries(m.inputs || {}).map(([k, x]: any) => `${k}: ${typeof x === "number" ? (Math.abs(x) < 5 ? num(x, 2) : num(x, 0)) : x}`).join(" · ")}</td>
              </tr>
            ))}
            <tr className="font-bold bg-slate-50"><td>Giá mục tiêu (bình quân gia quyền)</td><td className="text-right">{price(v.targets?.bear)}</td><td className="text-right">{price(v.targets?.base)}</td><td className="text-right">{price(v.targets?.bull)}</td><td className="text-right">100%</td><td>Upside cơ sở: <span className={cls(v.upside)}>{pct(v.upside, 1, true)}</span></td></tr>
          </tbody>
        </table></div>
        {v.skipped?.length > 0 && <ul className="text-xs text-amber-700 mt-2 list-disc pl-5">{v.skipped.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>}
        <p className="text-xs text-slate-500 mt-2">{v.multiples_source}. Phương pháp theo loại DN ({d.company_type_label}): ngân hàng không dùng DCF/EV-EBITDA; CTCK/BĐS/bảo hiểm dùng P/B–P/E tương đối.</p>
      </Card>
      <Card title="Giả định">
        <table className="tbl"><tbody>
          <tr><td>Lãi suất phi rủi ro (TPCP 10N)</td><td className="text-right">{pct(a.rf, 2)}</td></tr>
          <tr><td>Phần bù rủi ro (ERP)</td><td className="text-right">{pct(a.erp, 1)}</td></tr>
          <tr><td>Beta (2 năm, tuần, vs VN-Index)</td><td className="text-right">{num(a.beta, 2)} <span className="text-slate-400">(thô {num(a.beta_raw, 2)})</span></td></tr>
          <tr><td>Chi phí vốn CSH Ke</td><td className="text-right">{pct(a.ke, 2)}</td></tr>
          <tr><td>Tăng trưởng LN dùng</td><td className="text-right">{pct(a.growth, 1)}</td></tr>
          <tr><td>Tăng trưởng dài hạn g</td><td className="text-right">{pct(a.terminal_growth, 1)}</td></tr>
          {a.wacc !== undefined && <tr><td>WACC</td><td className="text-right">{pct(a.wacc, 2)}</td></tr>}
          <tr><td>EPS (LNST CĐ mẹ / số CP)</td><td className="text-right">{num(v.per_share?.eps, 0)}</td></tr>
          <tr><td>BVPS</td><td className="text-right">{num(v.per_share?.bvps, 0)}</td></tr>
        </tbody></table>
        <p className="text-xs text-slate-500 mt-2">3 kịch bản: bội số P25/P50/P75 của ngành, WACC ±1%, tăng trưởng ±2%, ROE ±2 điểm %. Tham số: config/settings.yaml.</p>
      </Card>
    </div>
  );
}

function TechTab({ d, t }: { d: any; t: string }) {
  const p = useApi<any>(`/api/py/stock/${t}/price?days=500`);
  const tech = d.technical;
  return (
    <div className="space-y-4">
      <Card title="Biểu đồ nến (ngày)" right={<AsOf p={p.data?.provenance} />}>
        {p.loading && <Loading what="giá" />}
        <ErrorBox error={p.error} />
        {p.data && <Candles bars={p.data.bars} />}
      </Card>
      <Card title="Tín hiệu kỹ thuật (MACD + RSI thích ứng + Ichimoku)">
        {!tech && <div className="text-sm text-slate-500">Không đủ 120 phiên để tính.</div>}
        {tech && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
              <Stat label="Tín hiệu" value={tech.action} sub={`Độ tin cậy ${tech.confidence}`} />
              <Stat label="Điểm hợp lưu" value={num(tech.total_score, 0)} sub="-100…+100" />
              <Stat label="Vùng mua" value={`${price(tech.entry[0])}–${price(tech.entry[1])}`} />
              <Stat label="Cắt lỗ" value={price(tech.stop_loss)} />
              <Stat label="Mục tiêu KT" value={price(tech.target)} />
              <Stat label="R/R" value={num(tech.risk_reward, 2)} />
            </div>
            <ul className="list-disc pl-5 text-sm mt-3">{tech.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            <p className="text-xs text-slate-500 mt-2">Bộ chỉ báo kế thừa từ bot-phan-tich; backtest walk-forward cho thấy không có lợi thế rõ rệt nên chỉ chiếm 10% điểm tổng hợp.</p>
          </>
        )}
      </Card>
    </div>
  );
}

function NewsTab({ t }: { t: string }) {
  const { data, error, loading } = useApi<any>(`/api/py/stock/${t}/news`);
  if (loading) return <Loading what="tin tức (CafeF, RSS)" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  return (
    <div className="grid md:grid-cols-3 gap-4">
      <Card title={`Tin về ${t}`} right={<AsOf p={data.provenance} label="Lấy lúc" />} className="md:col-span-2">
        {!data.items.length && <div className="text-sm text-slate-500">Không tìm thấy tin ({JSON.stringify(data.status)}).</div>}
        <ul className="divide-y divide-slate-100">
          {data.items.map((n: any) => (
            <li key={n.link} className="py-2 text-sm flex gap-2">
              <span className={`shrink-0 w-14 text-center rounded text-xs py-0.5 ${n.sentiment > 0 ? "bg-emerald-100 text-emerald-800" : n.sentiment < 0 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"}`}>{n.sentiment > 0 ? "Tích cực" : n.sentiment < 0 ? "Tiêu cực" : "Trung tính"}</span>
              <div><a className="link" href={n.link} target="_blank" rel="noreferrer">{n.title}</a><div className="text-xs text-slate-500">{n.source} · {n.published_at ? dmy(n.published_at) : "không rõ ngày"}</div></div>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Cảm xúc tin tức">
        <Stat label="Điểm (0–100)" value={num(data.sentiment.score_100, 0)} sub={`${data.sentiment.n_pos} tích cực · ${data.sentiment.n_neg} tiêu cực`} />
        <p className="text-xs text-slate-500 mt-2">Từ điển tài chính tiếng Việt, trọng số giảm nửa sau 30 ngày. Trạng thái nguồn: {Object.entries(data.status).map(([k, v]) => `${k}: ${v}`).join("; ")}</p>
        <h3 className="font-semibold mt-3 mb-1 text-sm">Tin vĩ mô/thị trường</h3>
        <ul className="text-xs space-y-1">{data.macro_headlines.map((n: any) => <li key={n.link}><a className="link" href={n.link} target="_blank" rel="noreferrer">{n.title}</a></li>)}</ul>
      </Card>
    </div>
  );
}

function DocsTab({ t }: { t: string }) {
  const { data, error, loading } = useApi<any>(`/api/py/stock/${t}/documents`);
  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  return (
    <Card title="Báo cáo thường niên (BCTN) gốc" right={<AsOf p={data?.provenance} label="Chỉ mục" />}>
      {!data?.items?.length && <div className="text-sm text-slate-500">Chỉ mục Zenodo không có BCTN của {t}.</div>}
      <SortTable rows={data?.items || []} rowKey={(r) => r.file_name} initialSort="year"
        cols={[
          { key: "year", label: "Năm" }, { key: "file_name", label: "File" }, { key: "size_mb", label: "MB", num: true, render: (r) => num(r.size_mb, 1) },
          { key: "zenodo", label: "Tải", render: (r) => <span className="space-x-2"><a className="link" href={r.zenodo} target="_blank" rel="noreferrer">Zenodo (bộ dữ liệu)</a><a className="link" href={r.cafef_cdn} target="_blank" rel="noreferrer">CDN CafeF</a></span> },
        ]} />
      <p className="text-xs text-slate-500 mt-2">Ngô Phú Thạnh (2025), Vietnam Listed Companies Annual Reports PDF Dataset, DOI 10.5281/zenodo.20949551. Link CafeF theo mẫu tên file của zenodo_downloader.py (có thể không còn tồn tại).</p>
    </Card>
  );
}

function DataTab({ d }: { d: any }) {
  const m = useApi<any>("/api/py/market");
  const st = m.data?.stats;
  return (
    <div className="space-y-4">
      <Card title="Tỷ lệ phủ dữ liệu toàn thị trường" right={<AsOf p={m.data?.provenance} />}>
        {st && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <Stat label="Mã đã phân ngành ICB" value={`${num(st.n_symbols - st.n_unclassified)}/${num(st.n_symbols)}`} sub={pct(st.industry_coverage, 1)} />
            <Stat label="Nguồn ngành" value={Object.entries(st.industry_source).map(([k, v]: any) => `${k} ${v}`).join(" · ")} />
            <Stat label="Mã có BCTC năm" value={`${num(st.n_with_bctc)}/${num(st.n_symbols)}`} sub="HSX/HNX – arminer" />
            <Stat label="Mã đủ thanh khoản" value={num(st.n_liquid)} sub="GTGD TB20 ≥ 1 tỷ" />
            <Stat label="Mã này" value={d.bctc_available ? "Có BCTC" : "Chưa có BCTC"} sub={`Ngành từ ${d.sources?.[0]?.origin || "universe"}`} />
          </div>
        )}
      </Card>
      <Card title={`Kiểm tra dữ liệu (${Object.entries(d.checks_summary || {}).map(([k, v]) => `${k} ${v}`).join(", ")})`}>
        <SortTable rows={d.checks} rowKey={(r) => r.name}
          cols={[{ key: "status", label: "KQ", render: (r) => <span className={r.status === "PASS" ? "text-up font-semibold" : r.status === "FAIL" ? "text-down font-semibold" : "text-ref font-semibold"}>{r.status}</span> },
            { key: "name", label: "Kiểm tra" }, { key: "detail", label: "Chi tiết", render: (r) => <span className="whitespace-normal">{r.detail}</span> }]} />
      </Card>
      <Card title="Nhật ký nguồn">
        <SortTable rows={d.sources} rowKey={(r) => r.item}
          cols={[{ key: "item", label: "Dữ liệu" }, { key: "source", label: "Nguồn", render: (r) => <span className="whitespace-normal text-xs">{r.source}</span> },
            { key: "as_of", label: "Đến ngày/kỳ", render: (r) => dmy(r.as_of) }, { key: "fetched_at", label: "Lấy lúc", render: (r) => dmy(r.fetched_at) },
            { key: "note", label: "Ghi chú", render: (r) => <span className="whitespace-normal text-xs">{r.note || r.origin || ""}</span> }]} />
      </Card>
      <Card title="Ánh xạ chỉ tiêu chuẩn ↔ item_code gốc (arminer)">
        <SortTable rows={Object.entries(d.financial_mapping || {}).map(([k, v]: any) => ({ k, v: String(v) }))} rowKey={(r) => r.k}
          cols={[{ key: "k", label: "Chỉ tiêu chuẩn" }, { key: "v", label: "Dòng gốc", render: (r) => <span className="whitespace-normal text-xs">{r.v}</span> }]} />
        {d.financial_notes?.length > 0 && <ul className="text-xs text-amber-700 mt-2 list-disc pl-5">{d.financial_notes.map((n: string) => <li key={n}>{n}</li>)}</ul>}
      </Card>
    </div>
  );
}
