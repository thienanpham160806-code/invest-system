"use client";
// Kết quả backtest point-in-time của bảng cơ hội (lệnh BT). Đọc gói do scripts/run_backtest_opportunity.py ghi ra.
import Link from "next/link";
import type { ReactNode } from "react";
import bundle from "@/webdata/backtest/opportunity.json";
import { CompareLine } from "@/components/Charts";
import { Card, Stat } from "@/components/ui";
import { cls, dmy, num, pct } from "@/lib/fmt";

const bt = bundle as any;
// 3 màu đầu tách được nhau ở mọi cặp (các đường cắt nhau liên tục); chỉ số tham chiếu dùng xám nét đứt
const HUES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
const GROUPS: Record<string, string> = { "tổng hợp": "Tổng hợp", valuation: "Định giá", quality: "Chất lượng", sector: "Ngành",
  growth: "Tăng trưởng", technical: "Kỹ thuật" };
const my = (s: string) => `${String(s).slice(5, 7)}/${String(s).slice(0, 4)}`;

type Col = { key: string; label: string; num?: boolean; render?: (r: any) => ReactNode };

function Table({ rows, cols, rowKey }: { rows: any[]; cols: Col[]; rowKey: (r: any) => string }) {
  return (
    <div className="overflow-x-auto">
      <table className="tbl">
        <thead><tr>{cols.map((c) => <th key={c.key} scope="col" style={{ cursor: "default", textAlign: c.num ? "right" : "left" }}>{c.label}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {cols.map((c) => <td key={c.key} className={c.num ? "text-right tabular-nums" : ""}>{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

const signed = (key: string, label: string, digits?: number): Col =>
  ({ key, label, num: true, render: (r) => <span className={cls(r[key])}>{digits === undefined ? pct(r[key]) : num(r[key], digits)}</span> });
const plain = (key: string, label: string, fmt: (v: any) => string): Col => ({ key, label, num: true, render: (r) => fmt(r[key]) });
const n2 = (v: any) => num(v, 2);

function metricCols(first: string, extra: string[] = []): Col[] {
  return [
    { key: "name", label: first },
    signed("CAGR", "CAGR"),
    plain("Sharpe", "Sharpe", n2),
    plain("Sụt giảm tối đa", "Sụt giảm tối đa", pct),
    ...(extra.includes("months") ? [plain("Tỷ lệ tháng dương", "Tháng dương", pct), plain("Tỷ lệ tháng thắng VN-Index", "Tháng thắng VN-Index", pct)] : []),
    ...(extra.includes("turnover") ? [plain("Vòng quay (lần/năm)", "Vòng quay (lần/năm)", n2)] : []),
    ...(extra.includes("psr") ? [plain("PSR(0)", "PSR(0)", n2)] : []),
    ...(extra.includes("dsr") ? [plain("DSR", "DSR", n2)] : []),
  ];
}

export default function BacktestPage() {
  const s = bt.summary, v = s.verdict;
  const strat = bt.benchmarks[0], vni = bt.benchmarks.find((b: any) => String(b.name).startsWith("VN-Index")) || {};
  const hues = [...HUES];
  const lines = (bt.equity_series as string[]).map((name, i) => name === "VN-Index"
    ? { key: name, name: "VN-Index (chỉ số giá)", color: "var(--series-ref)", dash: true }
    : { key: name, name, color: hues.shift() || "var(--series-ref)", bold: i === 0 });
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Backtest bảng cơ hội</h1>
        <p className="text-sm text-slate-600">
          Chấm lại điểm bảng <Link className="link" href="/co-hoi">Cơ hội</Link> tại {s.signals} ngày cuối tháng chỉ với dữ liệu đã công bố lúc đó, rồi mua top mã theo walk-forward.
          Out-of-sample {dmy(s.oos_start)} – {dmy(s.oos_end)}; {s.symbols_scored} mã từng đủ điều kiện; phí hai chiều {pct(s.fee_rate_round_trip, 2)}, thuế bán {pct(s.sell_tax, 1)}, T+{s.settlement_days}.
        </p>
        <span className="asof">Chạy lúc {dmy(s.generated_at)} – commit {s.commit}</span>
      </div>

      <Card title="Kết luận theo tiêu chí chốt trước khi chạy">
        <p className="font-semibold">{v.text}</p>
        <ul className="mt-2 space-y-1 text-sm">
          {Object.entries(v.checks as Record<string, boolean>).map(([name, ok]) => (
            <li key={name} className="flex items-start gap-2">
              <span aria-hidden className={ok ? "text-up" : "text-down"}>{ok ? "✓" : "✗"}</span>
              <span>{name} – <span className="font-medium">{ok ? "đạt" : "không đạt"}</span></span>
            </li>))}
        </ul>
        <p className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">⚠ {s.caveat}</p>
      </Card>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="CAGR chiến lược" value={pct(strat.CAGR)} sub={`VN-Index ${pct(vni.CAGR)}`} />
        <Stat label="Sharpe" value={num(strat.Sharpe, 2)} sub={`VN-Index ${num(vni.Sharpe, 2)}`} />
        <Stat label="Sụt giảm tối đa" value={pct(strat["Sụt giảm tối đa"])} sub={`VN-Index ${pct(vni["Sụt giảm tối đa"])}`} />
        <Stat label="DSR" value={num(strat.DSR, 2)} sub={`ngưỡng 0,95 · ${s.sharpe_report.n_trials} cấu hình thử`} />
      </div>

      <Card title="Đường vốn out-of-sample (gốc = 100, cuối tuần)">
        <CompareLine data={bt.equity} lines={lines} height={340} tick={my} />
        <p className="mt-2 text-xs text-slate-500">VN-Index là chỉ số giá, không gồm cổ tức; ba danh mục dùng giá đã điều chỉnh nên đã gồm cổ tức. Số liệu từng danh mục ở bảng dưới.</p>
      </Card>

      <Card title="Chiến lược so với benchmark">
        <Table rows={bt.benchmarks} rowKey={(r) => r.name} cols={metricCols("Danh mục", ["months", "turnover", "psr", "dsr"])} />
      </Card>

      <Card title="Năng lực xếp hạng của điểm (IC Spearman theo tháng)">
        <Table rows={bt.ic} rowKey={(r) => `${r["nhóm"]}-${r["kỳ hạn (tháng)"]}`}
          cols={[
            { key: "nhóm", label: "Nhóm điểm", render: (r) => GROUPS[r["nhóm"]] || r["nhóm"] },
            plain("kỳ hạn (tháng)", "Kỳ hạn", (m) => `${m} tháng`),
            signed("IC trung binh", "IC trung bình", 3),
            plain("ICIR", "ICIR", n2),
            plain("t-stat Newey-West", "t Newey–West", n2),
            plain("Ti le thang IC>0", "Tháng IC > 0", pct),
            plain("So thang", "Số tháng", (m) => num(m, 0)),
          ]} />
        <p className="mt-2 text-xs text-slate-500">IC: tương quan hạng giữa điểm cuối tháng và lợi suất kỳ sau trên các mã đủ điều kiện. t Newey–West ≥ 2 mới coi là khác 0. Backtest dùng 5/7 nhóm điểm; vĩ mô và tin tức không có lịch sử theo ngày công bố.</p>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="Độ nhạy (giữ nguyên lựa chọn walk-forward)" className="min-w-0">
          <Table rows={bt.sensitivity} rowKey={(r) => r.name} cols={metricCols("Kịch bản", ["psr"])} />
        </Card>
        <Card title="Bốn cấu hình trên cả giai đoạn (không dùng để chọn)" className="min-w-0">
          <Table rows={bt.configs} rowKey={(r) => r.name} cols={metricCols("Cấu hình", ["turnover"])} />
        </Card>
      </div>

      <Card title="Các lát walk-forward (train 24 tháng, test 6 tháng)">
        <Table rows={bt.slices} rowKey={(r) => r.test_start}
          cols={[
            { key: "train_start", label: "Train từ", render: (r) => my(r.train_start) },
            { key: "test_start", label: "Test", render: (r) => `${my(r.test_start)} – ${my(r.test_end)}` },
            { key: "cấu hình", label: "Cấu hình chọn" },
            plain("Sharpe train", "Sharpe train", n2),
            signed("Lợi suất tích luỹ", "Lợi suất test"),
            plain("Sụt giảm tối đa", "Sụt giảm tối đa", pct),
          ]} />
      </Card>

      <Card title="Giới hạn">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Universe chỉ gồm mã đang niêm yết hôm nay (survivorship), nên kết quả là cận trên.</li>
          <li>Số cổ phiếu, ngành ICB, sàn và lãi suất phi rủi ro lấy giá trị hiện tại. BCTC năm coi như công bố ngày 01/04 năm sau; BCTC quý dùng ngày công bố của VCI.</li>
          <li>UPCOM gần như không có BCTC năm trong nguồn nên ít khi đủ điều kiện.</li>
          <li>Kho giá Vietcap có nến giá bằng 0 (chủ yếu UPCOM, 2015–2018) đã bị bỏ, coi như phiên không giao dịch.</li>
          <li>Thiết kế, tiêu chí và nhật ký thay đổi: <code>docs/phase2/backtest-design.md</code>; báo cáo đầy đủ: <code>docs/backtest-opportunity.md</code>.</li>
        </ul>
      </Card>
    </div>
  );
}
