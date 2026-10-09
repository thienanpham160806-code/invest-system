"use client";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { CompareLine, PbRoeScatter, ScoreBars } from "@/components/Charts";
import { getJSON } from "@/lib/api";
import { bnLabel, cls, dmy, fmtKind, num, pct, price, RATING_COLOR, times } from "@/lib/fmt";

const SECTIONS: Record<string, string> = {
  macro: "Tổng quan vĩ mô", sector: "Phân tích ngành", company: "Phân tích doanh nghiệp",
  valuation: "Định giá", technical: "Phân tích kỹ thuật", news: "Tin tức & cảm xúc", appendix: "Phụ lục dữ liệu",
};
const SCORE_LABELS: Record<string, string> = {
  macro: "Vĩ mô", sector: "Ngành", quality: "Chất lượng", growth: "Tăng trưởng",
  valuation: "Định giá", technical: "Kỹ thuật", sentiment: "Tin tức",
};
const KEY_IS = ["is_doanh_so_thuan", "is_tong_thu_nhap_hoat_dong", "is_doanh_thu_hoat_dong", "is_lai_gop", "is_thu_nhap_lai_thuan", "is_chi_phi_du_phong_rui_ro_tin_dung",
  "is_lai_lo_rong_truoc_thue", "is_tong_loi_nhuan_truoc_thue", "is_tong_loi_nhuan_ke_toan_truoc_thue", "is_lai_lo_thuan_sau_thue", "is_loi_nhuan_sau_thue",
  "is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_co_dong_cua_cong_ty_me", "is_lai_co_ban_tren_co_phieu"];
const KEY_BS = ["bs_tai_san_ngan_han", "bs_tien_va_tuong_duong_tien", "bs_hang_ton_kho", "bs_cho_vay_khach_hang", "bs_tong_tai_san", "bs_tong_cong_tai_san",
  "bs_no_phai_tra", "bs_tong_no_phai_tra", "bs_vay_ngan_han", "bs_vay_dai_han", "bs_tien_gui_cua_khach_hang", "bs_von_gop", "bs_von_dieu_le"];

declare global { interface Window { __REPORT_READY__?: boolean } }

export default function ReportPage() {
  return <Suspense fallback={<div>Đang tải…</div>}><Report /></Suspense>;
}

function Report() {
  const { ticker } = useParams<{ ticker: string }>();
  const t = String(ticker).toUpperCase();
  const sp = useSearchParams();
  const router = useRouter();
  const sections = (sp.get("sections") || Object.keys(SECTIONS).join(",")).split(",").filter((s) => s in SECTIONS);
  const years = +(sp.get("years") || 5);
  const template = sp.get("template") === "summary" ? "summary" : "full";
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);

  useEffect(() => {
    window.__REPORT_READY__ = false;
    const want = (s: string) => sections.includes(s);
    Promise.all([
      getJSON(`/api/py/stock/${t}/analysis?years=${years}&news=${want("news")}`),
      getJSON(`/api/py/stock/${t}/financials?statement=is&years=${years}`),
      getJSON(`/api/py/stock/${t}/financials?statement=bs&years=${years}`),
      getJSON(`/api/py/stock/${t}/ratios?years=${years}`),
      want("macro") ? getJSON(`/api/py/macro?world_bank=false`) : Promise.resolve(null),
      getJSON(`/api/py/stock/${t}/price?days=260`),
    ]).then(([a, is, bs, ra, mac, px]) => setData({ a, is, bs, ra, mac, px }))
      .catch((e) => setErr(String(e.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, years, sp.get("sections")]);

  useEffect(() => { if (data) setTimeout(() => { window.__REPORT_READY__ = true; }, 800); }, [data]);

  const setParam = (k: string, v: string) => {
    const q = new URLSearchParams(sp.toString()); q.set(k, v); router.replace(`/report/${t}?${q.toString()}`);
  };
  const toggle = (s: string) => setParam("sections", (sections.includes(s) ? sections.filter((x) => x !== s) : [...sections, s]).join(","));

  const exportServer = async () => {
    setPdfBusy(true);
    try {
      const r = await fetch(`/api/pdf?ticker=${t}&${sp.toString()}`);
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = `${t}_${new Date().toISOString().slice(0, 10).replace(/-/g, "")}.pdf`; a.click();
    } catch (e) {
      alert("Máy chủ chưa xuất được PDF – chuyển sang in từ trình duyệt (chọn 'Lưu dưới dạng PDF').");
      window.print();
    } finally { setPdfBusy(false); }
  };

  return (
    <div>
      <div className="no-print card mb-4 flex flex-wrap gap-3 items-center text-sm">
        <b>Báo cáo {t}</b>
        {Object.entries(SECTIONS).map(([k, l]) => (
          <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={sections.includes(k)} onChange={() => toggle(k)} />{l}</label>
        ))}
        <select className="sel" value={years} onChange={(e) => setParam("years", e.target.value)}>{[3, 5, 7].map((n) => <option key={n} value={n}>{n} năm</option>)}</select>
        <select className="sel" value={template} onChange={(e) => setParam("template", e.target.value)}><option value="full">Mẫu đầy đủ</option><option value="summary">Mẫu tóm tắt</option></select>
        <button className="btn" onClick={() => window.print()} disabled={!data}>Xuất PDF (in trình duyệt)</button>
        <button className="btn-ghost" onClick={exportServer} disabled={!data || pdfBusy}>{pdfBusy ? "Đang tạo…" : "Tải PDF từ máy chủ"}</button>
      </div>
      {err && <div className="text-red-600">Lỗi: {err}</div>}
      {!data && !err && <div className="animate-pulse">Đang dựng báo cáo {t}…</div>}
      {data && <ReportBody d={data} sections={sections} template={template} years={years} />}
    </div>
  );
}

function H({ children }: { children: React.ReactNode }) {
  return <h2 className="rp-h2">{children}</h2>;
}

function FinTable({ fin, keys, years }: { fin: any; keys: string[]; years: number }) {
  const ys: number[] = (fin?.years || []).slice(-years);
  const rows = (fin?.rows || []).filter((r: any) => keys.some((k) => r.item_code === k || r.item_code.startsWith(k + "_")));
  const seen = new Set<string>();
  const uniq = rows.filter((r: any) => { const k = r.item_name.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
  if (!uniq.length) return <p className="text-xs">Chưa có nguồn BCTC.</p>;
  return (
    <table className="rp-tbl"><thead><tr><th>Tỷ đồng</th>{ys.map((y) => <th key={y}>FY{y}</th>)}</tr></thead>
      <tbody>{uniq.map((r: any) => <tr key={r.item_code}><td>{r.item_name}</td>{ys.map((y) => <td key={y}>{r.item_code.includes("tren_co_phieu") ? num(r.values[y]) : num(r.values[y] / 1e9, 0)}</td>)}</tr>)}</tbody>
    </table>
  );
}

function ReportBody({ d, sections, template, years }: { d: any; sections: string[]; template: string; years: number }) {
  const a = d.a;
  const r = a.recommendation;
  const has = (s: string) => sections.includes(s);
  const full = template === "full";
  const priceSeries = useMemo(() => {
    const bars = d.px?.bars || []; const vni = d.px?.vnindex || [];
    if (!bars.length) return [];
    const m = new Map(vni.map((v: any) => [String(v.time).slice(0, 10), v.close]));
    const b0 = bars[0].close; const v0: any = m.get(String(bars[0].time).slice(0, 10)) || (vni[0]?.close);
    return bars.map((b: any) => { const vv: any = m.get(String(b.time).slice(0, 10)); return { time: String(b.time).slice(0, 10), stock: (b.close / b0) * 100, vnindex: vv && v0 ? (vv / v0) * 100 : undefined }; });
  }, [d.px]);
  const ratioRows = (d.ra?.groups || []).flatMap((g: any) => g.items);
  const ys: number[] = d.ra?.years || [];
  const priceProv = a.sources?.find((s: any) => s.item?.startsWith("Giá"));
  const finProv = a.sources?.find((s: any) => s.item?.startsWith("BCTC"));
  return (
    <article className="report">
      {/* ---------------- Trang 1 kieu SSI/VCSC ---------------- */}
      <section className="rp-page">
        <div className="rp-head">
          <div>
            <div className="text-[10px] uppercase tracking-wider opacity-80">Báo cáo phân tích cổ phiếu · {dmy(a.generated_at)}</div>
            <div className="text-2xl font-bold">{a.symbol} – {a.name}</div>
            <div className="text-xs opacity-90">{a.exchange} · {a.icb.icb1} › {a.icb.icb2} › {a.icb.icb4} · {a.company_type_label}</div>
          </div>
          {r.rating && <div className={`rp-rating ${RATING_COLOR[r.rating]}`}>{r.rating}</div>}
        </div>
        <div className="rp-grid">
          <div className="rp-main">
            <div className="rp-kpis">
              <div><span>Giá hiện tại</span><b>{price(a.price)}</b></div>
              <div><span>Giá mục tiêu</span><b>{price(r.target_price)}</b></div>
              <div><span>Upside</span><b className={cls(r.upside)}>{pct(r.upside, 1, true)}</b></div>
              <div><span>Điểm tổng hợp</span><b>{num(r.total_score, 0)}/100</b></div>
            </div>
            <h3 className="rp-h3">Luận điểm đầu tư</h3>
            <ul className="rp-ul">{a.thesis.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <h3 className="rp-h3">Rủi ro</h3>
            <ul className="rp-ul">{a.risks.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <h3 className="rp-h3">Diễn biến giá 12 tháng so với VN-Index (=100)</h3>
            <CompareLine data={priceSeries} lines={[{ key: "stock", name: a.symbol, color: "#dc2626" }, { key: "vnindex", name: "VN-Index", color: "#0b3b6f" }]} height={170} />
          </div>
          <aside className="rp-side">
            <table className="rp-tbl rp-tbl-side"><tbody>
              <tr><td>Vốn hoá</td><td>{bnLabel(a.market_cap)}</td></tr>
              <tr><td>Số CP</td><td>{num(a.shares)}</td></tr>
              <tr><td>P/E ({a.metrics.fin_year ? `FY${a.metrics.fin_year}` : "–"})</td><td>{times(a.metrics.pe)}</td></tr>
              {a.metrics.pe_ttm && <tr><td>P/E ({a.metrics.ttm_label})</td><td>{times(a.metrics.pe_ttm)}</td></tr>}
              <tr><td>P/B</td><td>{times(a.metrics.pb, 2)}</td></tr>
              <tr><td>EV/EBITDA</td><td>{times(a.metrics.ev_ebitda)}</td></tr>
              <tr><td>ROE</td><td>{pct(a.metrics.roe)}</td></tr>
              <tr><td>Biên ròng</td><td>{pct(a.metrics.net_margin)}</td></tr>
              <tr><td>Tăng trưởng LN</td><td>{pct(a.metrics.ni_growth)}</td></tr>
              <tr><td>GTGD TB20</td><td>{num(a.metrics.avg_value_20d / 1e9, 1)} tỷ</td></tr>
              <tr><td>Giá 1 năm</td><td>{pct(a.metrics.ret_1y)}</td></tr>
              <tr><td>P/E TV ngành</td><td>{times(a.sector.quantiles?.pe?.[1])}</td></tr>
              <tr><td>P/B TV ngành</td><td>{times(a.sector.quantiles?.pb?.[1], 2)}</td></tr>
            </tbody></table>
            <h3 className="rp-h3">Điểm 7 nhóm</h3>
            <ScoreBars scores={r.scores} labels={SCORE_LABELS} />
            <p className="rp-src">Dữ liệu giá đến {dmy(priceProv?.as_of)} – nguồn {priceProv?.source}. BCTC: {finProv?.as_of || "–"} – {finProv?.source}. Ngành: {a.sector.note}.</p>
          </aside>
        </div>
      </section>

      {has("macro") && d.mac && (
        <section className="rp-section">
          <H>1. Tổng quan vĩ mô</H>
          <div className="rp-conclusion"><b>Kết luận.</b> {a.macro.commentary.slice(0, 2).join(" ")}</div>
          <table className="rp-tbl"><thead><tr><th>Chỉ tiêu</th><th>Kỳ</th><th>Giá trị</th><th>Nguồn</th></tr></thead>
            <tbody>{d.mac.table.filter((x: any) => full || String(x.period).startsWith("2026")).map((x: any) => (
              <tr key={x.key + x.period}><td>{x.label}</td><td>{x.period}</td><td>{x.unit === "VND" ? num(x.value) : num(x.value, 2) + x.unit}</td><td className="rp-small">{String(x.source).replace(/\(https?:[^)]+\)/, "")} ({dmy(x.as_of)})</td></tr>))}</tbody></table>
          <ul className="rp-ul">{a.macro.commentary.map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
        </section>
      )}

      {has("sector") && (
        <section className="rp-section">
          <H>2. Phân tích ngành</H>
          <div className="rp-conclusion"><b>Kết luận.</b> {a.sector.note}</div>
          <p className="rp-p">So sánh ở <b>ICB cấp {a.sector.level} – {a.sector.name}</b>: {a.sector.n_peers} mã, {a.sector.n_liquid} mã đủ thanh khoản; dữ liệu lúc {dmy(d.a.sources?.[0]?.built_at || d.a.sources?.[0]?.as_of)}.
            Hiệu suất ngành 3T {pct(a.sector.stats.ret_3m)} (VN-Index {pct(a.sector.stats.ret_3m - (a.sector.stats.ret_3m_vs_index ?? 0))}), 1 năm {pct(a.sector.stats.ret_1y)}.
            Trung vị P/E {times(a.sector.quantiles?.pe?.[1])} (P25–P75 {times(a.sector.quantiles?.pe?.[0])}–{times(a.sector.quantiles?.pe?.[2])}), P/B {times(a.sector.quantiles?.pb?.[1], 2)}, ROE {pct(a.sector.quantiles?.roe?.[1])}. Điểm ngành {num(a.sector.score?.score, 0)}/100.</p>
          <p className="rp-p">Vị thế {a.symbol} (phân vị trong ngành): ROE {pct(a.sector.position?.roe, 0)}, P/E {pct(a.sector.position?.pe, 0)}, P/B {pct(a.sector.position?.pb, 0)}, vốn hoá {pct(a.sector.position?.market_cap, 0)}.</p>
          {full && <div className="rp-avoid"><PbRoeScatter rows={a.sector.peers} highlight={a.symbol} height={220} /></div>}
          <table className="rp-tbl"><thead><tr><th>Mã</th><th>Vốn hoá</th><th>P/E</th><th>P/B</th><th>ROE</th><th>Tăng LN</th><th>Giá 1N</th></tr></thead>
            <tbody>{a.sector.peers.slice(0, full ? 12 : 6).map((p: any) => <tr key={p.symbol} className={p.symbol === a.symbol ? "font-bold" : ""}><td>{p.symbol}</td><td>{bnLabel(p.market_cap)}</td><td>{times(p.pe)}</td><td>{times(p.pb, 2)}</td><td>{pct(p.roe)}</td><td>{pct(p.ni_growth)}</td><td>{pct(p.ret_1y)}</td></tr>)}</tbody></table>
        </section>
      )}

      {has("company") && (
        <section className="rp-section">
          <H>3. Phân tích doanh nghiệp</H>
          <div className="rp-conclusion"><b>Kết luận.</b> {a.thesis?.[0] || "Chưa đủ dữ liệu để kết luận về doanh nghiệp."}</div>
          <h3 className="rp-h3">Kết quả kinh doanh</h3>
          <FinTable fin={d.is} keys={KEY_IS} years={years} />
          {full && <><h3 className="rp-h3">Cân đối kế toán</h3><FinTable fin={d.bs} keys={KEY_BS} years={years} /></>}
          <h3 className="rp-h3">Chỉ số tài chính</h3>
          <table className="rp-tbl"><thead><tr><th>Chỉ số</th>{ys.map((y) => <th key={y}>FY{y}</th>)}</tr></thead>
            <tbody>{ratioRows.slice(0, full ? 30 : 8).map((it: any) => <tr key={it.key}><td>{it.label}</td>{ys.map((y) => <td key={y}>{fmtKind(it.values[y], it.kind)}</td>)}</tr>)}</tbody></table>
        </section>
      )}

      {has("valuation") && (
        <section className="rp-section">
          <H>4. Định giá</H>
          <div className="rp-conclusion"><b>Kết luận.</b> {r.reason || `Giá mục tiêu cơ sở ${price(r.target_price)}; upside ${pct(r.upside, 1, true)}.`}</div>
          <table className="rp-tbl"><thead><tr><th>Phương pháp</th><th>Bi quan</th><th>Cơ sở</th><th>Lạc quan</th><th>Trọng số</th></tr></thead>
            <tbody>{a.valuation.methods.map((m: any) => <tr key={m.key}><td>{m.label}{m.note ? ` (${m.note})` : ""}</td><td>{price(m.values.bear)}</td><td>{price(m.values.base)}</td><td>{price(m.values.bull)}</td><td>{pct(m.weight, 0)}</td></tr>)}
              <tr className="font-bold"><td>Giá mục tiêu</td><td>{price(r.targets?.bear)}</td><td>{price(r.targets?.base)}</td><td>{price(r.targets?.bull)}</td><td>100%</td></tr></tbody></table>
          <p className="rp-p rp-small">Giả định: rf {pct(a.valuation.assumptions.rf, 2)} (TPCP 10N), ERP {pct(a.valuation.assumptions.erp, 1)}, beta {num(a.valuation.assumptions.beta, 2)}, Ke {pct(a.valuation.assumptions.ke, 2)}, g dài hạn {pct(a.valuation.assumptions.terminal_growth, 1)}, tăng trưởng LN {pct(a.valuation.assumptions.growth, 1)}. {a.valuation.multiples_source}. {a.valuation.skipped.join(" ")}</p>
        </section>
      )}

      {has("technical") && a.technical && (
        <section className="rp-section">
          <H>5. Phân tích kỹ thuật</H>
          <div className="rp-conclusion"><b>Kết luận.</b> {a.technical.reasons.slice(0, 2).join(" ")}</div>
          <p className="rp-p">Tín hiệu <b>{a.technical.action}</b> (điểm hợp lưu {num(a.technical.total_score, 0)}, độ tin cậy {a.technical.confidence}). Vùng mua {price(a.technical.entry[0])}–{price(a.technical.entry[1])}, cắt lỗ {price(a.technical.stop_loss)}, mục tiêu {price(a.technical.target)}.</p>
          <ul className="rp-ul">{a.technical.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
        </section>
      )}

      {has("news") && a.news && (
        <section className="rp-section">
          <H>6. Tin tức & cảm xúc</H>
          <div className="rp-conclusion"><b>Kết luận.</b> Điểm cảm xúc {num(a.news.sentiment.score_100, 0)}/100 ({a.news.sentiment.n_pos} tích cực, {a.news.sentiment.n_neg} tiêu cực).</div>
          <p className="rp-p">Điểm cảm xúc {num(a.news.sentiment.score_100, 0)}/100 ({a.news.sentiment.n_pos} tích cực, {a.news.sentiment.n_neg} tiêu cực). Nguồn: {a.news.provenance.source}, lấy lúc {dmy(a.news.provenance.fetched_at)}.</p>
          <ul className="rp-ul rp-small">{a.news.items.slice(0, full ? 12 : 5).map((n: any) => <li key={n.link}>{n.published_at ? dmy(n.published_at) + " – " : ""}{n.title} <i>({n.source})</i></li>)}</ul>
        </section>
      )}

      {has("appendix") && full && (
        <section className="rp-section">
          <H>Phụ lục – Dữ liệu & nguồn</H>
          <h3 className="rp-h3">A. Ánh xạ chỉ tiêu</h3>
          <table className="rp-tbl rp-small"><tbody>{Object.entries(a.financial_mapping).map(([k, v]: any) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
          <h3 className="rp-h3">B. Kiểm tra dữ liệu</h3>
          <table className="rp-tbl rp-small"><tbody>{a.checks.map((c: any) => <tr key={c.name}><td>{c.status}</td><td>{c.name}</td><td>{c.detail}</td></tr>)}</tbody></table>
          <h3 className="rp-h3">C. Nhật ký nguồn</h3>
          <table className="rp-tbl rp-small"><tbody>{a.sources.map((s: any) => <tr key={s.item}><td>{s.item}</td><td>{s.source}</td><td>{dmy(s.as_of)}</td><td>{dmy(s.fetched_at)}</td></tr>)}</tbody></table>
        </section>
      )}
      <p className="rp-src mt-4">Báo cáo tạo tự động lúc {dmy(a.generated_at)} bởi invest-system. Mọi số liệu có nguồn và thời điểm; số thiếu ghi "–". Không phải lời khuyên đầu tư.</p>
    </article>
  );
}
