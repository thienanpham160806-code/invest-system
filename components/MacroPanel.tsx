"use client";
// Vĩ mô trong nước + bối cảnh quốc tế (FRED). Dùng chung cho /vi-mo và tab Vĩ mô của trang cổ phiếu.
import { Line, LineChart, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { CompareLine } from "@/components/Charts";
import { AsOf, Card, ErrorBox, Loading, SortTable, Stat } from "@/components/ui";
import { useApi } from "@/lib/api";
import { cls, dmy, isNum, num, pct } from "@/lib/fmt";

type IntlRow = {
  key: string; label: string; unit: string; value: number; date: string; change_unit: string;
  chg_1m: number | null; chg_3m: number | null; chg_1y: number | null; spark: { t: string; v: number }[];
  reading: string; series_id: string; url: string; source: string; stale?: boolean; note?: string; z?: number;
};

const CTYPE_LABEL: Record<string, string> = {
  BANK: "Ngân hàng", SECURITIES: "Chứng khoán", INSURANCE: "Bảo hiểm", REAL_ESTATE: "Bất động sản", NON_FINANCIAL: "Phi tài chính",
};

function change(v: number | null, unit: string) {
  if (!isNum(v)) return <span className="text-slate-400">–</span>;
  const text = unit === "%" ? pct(v, 1, true) : `${v > 0 ? "+" : ""}${num(v, 2)} đ.%`;
  return <span className={cls(v)}>{text}</span>;
}

function Spark({ data }: { data: { t: string; v: number }[] }) {
  if (!data?.length) return null;
  return (
    <div className="h-12" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 2, left: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Tooltip formatter={(v: any) => num(v, 2)} labelFormatter={(_, p: any) => dmy(p?.[0]?.payload?.t)} />
          <Line type="monotone" dataKey="v" dot={false} strokeWidth={1.6} stroke="#0284c7" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function IntlCards({ rows }: { rows: IntlRow[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map((r) => (
        <div key={r.key} className="rounded border border-slate-200 p-3" data-testid={`intl-${r.key}`}>
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-sm font-medium">{r.label}</div>
            <a className="link text-xs" href={r.url} target="_blank" rel="noreferrer">{r.series_id}</a>
          </div>
          <div className="text-xl font-semibold tabular-nums">{num(r.value, 2)} <span className="text-xs font-normal text-slate-500">{r.unit}</span></div>
          <div className="grid grid-cols-3 gap-1 text-xs tabular-nums mt-1">
            <div><span className="text-slate-500">1T </span>{change(r.chg_1m, r.change_unit)}</div>
            <div><span className="text-slate-500">3T </span>{change(r.chg_3m, r.change_unit)}</div>
            <div><span className="text-slate-500">1N </span>{change(r.chg_1y, r.change_unit)}</div>
          </div>
          <Spark data={r.spark} />
          <p className="text-xs text-slate-600 mt-1">{r.reading}</p>
          <div className="text-[11px] text-slate-500 mt-1">
            {r.source}{r.stale ? " · dữ liệu cũ (lỗi mạng)" : ""} · đến {dmy(r.date)}{r.note ? ` · ${r.note}` : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScoreSplit({ data }: { data: any }) {
  const parts = data.parts || {};
  const dom = parts.domestic || {}, intl = parts.international || {};
  const w = (x: any) => (isNum(x?.weight) ? ` (${pct(x.weight, 0)})` : "");
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
      <Stat label="Điểm vĩ mô tổng hợp" value={num(data.score, 0)} sub={`Tác động lên nhóm ${CTYPE_LABEL[data.company_type] || ""}: ${num(data.sector_score, 0)}`} />
      <Stat label={`Trong nước${w(dom)}`} value={num(dom.score, 0)} sub={`Tác động nhóm: ${num(dom.sector_score, 0)}`} />
      <Stat label={`Quốc tế${w(intl)}`} value={num(intl.score, 0)} sub={`Tác động nhóm: ${num(intl.sector_score, 0)}`} />
    </div>
  );
}

export default function MacroPanel({ ctype, withHistory = true }: { ctype: string; withHistory?: boolean }) {
  const { data, error, loading } = useApi<any>(`/api/py/macro?company_type=${ctype}`);
  if (loading && !data) return <Loading what="vĩ mô" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;
  const hist = data.history || {};
  const series = (k: string) => (hist[k] || []).map((x: any) => ({ time: String(x.year), v: x.value }));
  const intl = data.international;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card title="Điểm vĩ mô" className="md:col-span-2">
        <ScoreSplit data={data} />
        <p className="text-xs text-slate-500 mt-2">
          Điểm = 70% trong nước + 30% quốc tế (cấu hình <code>macro.intl_weight</code>); thiếu một phần thì dùng phần còn lại.
          Tác động theo loại DN: {Object.entries(data.sector_impact || {}).map(([k, v]: any) => `${CTYPE_LABEL[k] || k} ${num(v, 0)}`).join(" · ")}.
          Ma trận độ nhạy trong <code>config/sector_map.yaml</code> là giả định định tính.
        </p>
      </Card>
      <Card title="Chỉ tiêu vĩ mô trong nước (kèm nguồn)" right={<AsOf p={data.provenance} label="Cập nhật" />} className="md:col-span-2">
        <SortTable rows={data.table} rowKey={(r) => r.key + r.period}
          cols={[
            { key: "label", label: "Chỉ tiêu" }, { key: "period", label: "Kỳ" },
            { key: "value", label: "Giá trị", num: true, render: (r) => (r.unit === "VND" ? num(r.value) : num(r.value, 2)) + " " + r.unit },
            { key: "as_of", label: "Công bố", render: (r) => dmy(r.as_of) },
            { key: "source", label: "Nguồn", render: (r) => { const u = (String(r.source).match(/https?:[^)\s]+/) || [])[0]; return <span className="whitespace-normal text-xs">{String(r.source).replace(/\(https?:[^)]+\)/, "")} {u && <a className="link" href={u} target="_blank" rel="noreferrer">[link]</a>}</span>; } },
          ]} />
      </Card>
      <Card title="Bối cảnh quốc tế" className="md:col-span-2"
        right={<span className="text-xs text-slate-500">FRED – Federal Reserve Bank of St. Louis · cache 1 ngày</span>}>
        {intl?.rows?.length ? <IntlCards rows={intl.rows} /> :
          <p className="text-sm text-slate-500">Chưa lấy được dữ liệu FRED — điểm vĩ mô hiện chỉ gồm phần trong nước.</p>}
        {intl?.notes?.length > 0 && <ul className="text-xs text-amber-700 mt-2 list-disc pl-5">{intl.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul>}
      </Card>
      <Card title="Nhận định trong nước">
        <ul className="list-disc pl-5 text-sm space-y-1">{(data.domestic_commentary || data.commentary || []).map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
      </Card>
      <Card title="Nhận định quốc tế (theo quy tắc)">
        <ul className="list-disc pl-5 text-sm space-y-1">{(intl?.commentary || ["Không có dữ liệu."]).map((c: string, i: number) => <li key={i}>{c}</li>)}</ul>
      </Card>
      {withHistory && (
        <Card title="Chuỗi lịch sử (World Bank + số nhập tay theo năm)" className="md:col-span-2">
          <CompareLine data={series("gdp_growth").map((g: any) => ({ time: g.time, gdp: g.v, cpi: series("cpi").find((c: any) => c.time === g.time)?.v }))}
            lines={[{ key: "gdp", name: "GDP %", color: "#0b3b6f" }, { key: "cpi", name: "CPI %", color: "#dc2626" }]} height={220} />
        </Card>
      )}
    </div>
  );
}
