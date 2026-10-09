"use client";
import { AsOf, Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { useApi } from "@/lib/api";

export default function Sources() {
  const live = useApi<any>("/api/py/sources");
  const m = useApi<any>("/api/py/market");
  const bctc = useApi<any>("/api/py/bctc-coverage");
  const rows = live.data ? Object.entries(live.data.results).map(([k, v]: any) => ({ name: k, ...v })) : [];
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Dữ liệu & nguồn</h1>
      <Card title="Kiểm tra nguồn trực tiếp từ máy chủ đang chạy" right={live.data && <span className="asof">Kiểm tra lúc {live.data.tested_at}</span>}>
        <ErrorBox error={live.error} />
        {live.loading && <Loading what="kiểm tra nguồn" />}
        <SortTable rows={rows} rowKey={(r) => r.name}
          cols={[{ key: "status", label: "KQ", render: (r) => <span className={r.ok ? "text-up font-semibold" : "text-down font-semibold"}>{r.status}</span> },
            { key: "name", label: "Nguồn" }, { key: "ms", label: "Độ trễ (ms)", num: true, render: (r) => r.ms == null ? "—" : r.ms },
            { key: "detail", label: "Chi tiết", render: (r) => <span className="whitespace-normal text-xs">{String(r.detail)}</span> }]} />
        <p className="text-xs text-slate-500 mt-2">Nguồn nào lỗi trên máy chủ (vd Vietcap chặn IP ngoài VN) thì hệ thống tự dùng bản chụp đóng gói và ghi rõ trên từng số.</p>
        <p className="text-xs text-slate-500">Độ trễ là thời gian máy chủ gọi tới nguồn và nhận phản hồi.</p>
      </Card>
      <Card title="Nguồn tin đang dùng">
        <p className="mb-2 text-sm">Audit {live.data?.news_quality?.audit_as_of || "—"}: {live.data?.news_quality?.sample_symbols ?? 0} mã mẫu; precision thủ công {live.data?.news_quality?.manual_precision == null ? "chưa đo" : `${(live.data.news_quality.manual_precision * 100).toFixed(0)}%`} ({live.data?.news_quality?.reviewed_titles ?? 0} tiêu đề đã đọc), mục tiêu ≥{((live.data?.news_quality?.precision_target ?? 0.9) * 100).toFixed(0)}%. {live.data?.news_quality?.coverage_note}</p>
        <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>Nguồn</th><th>URL</th><th>Loại</th><th>Số tin mẫu</th></tr></thead>
          <tbody>{(live.data?.news_sources || []).map((s: any) => <tr key={s.name}><td>{s.name}</td><td><a className="link" href={s.url} target="_blank" rel="noreferrer">{s.url}</a></td><td>{s.type}</td><td>{s.count ?? "—"}{s.note ? ` · ${s.note}` : ""}</td></tr>)}</tbody></table></div>
        <p className="mt-2 text-xs text-slate-500">Số tin là số bài nhận được trong lần kiểm tra nguồn; riêng CafeF trang mã dùng FPT làm mã đại diện.</p>
      </Card>
      <Card title="Bảng toàn thị trường (tính sẵn bằng scripts/build_market_universe.py)" right={<AsOf p={m.data?.provenance} />}>
        {m.data && (
          <div className="text-sm space-y-1">
            {Object.entries(m.data.checks || {}).map(([k, v]: any) => <div key={k}><b>{k}</b>: {typeof v === "object" ? JSON.stringify(v) : String(v)}</div>)}
            <div className="text-xs text-slate-500 mt-2">{m.data.provenance.source}</div>
          </div>
        )}
      </Card>
      <Card title="Độ phủ BCTC năm · vn-annual-report-miner" right={<span className="asof">{bctc.data?.listed_total?.toLocaleString("vi-VN")} mã toàn thị trường</span>}>
        <ErrorBox error={bctc.error} />
        {bctc.loading && <Loading what="độ phủ BCTC" />}
        {bctc.data?.by_exchange && <>
          <div className="overflow-x-auto"><table className="tbl"><thead><tr>{["Sàn", "Mã niêm yết", "Có BCTC", "Độ phủ", "Có FY2025", "FY2024 trở về trước", "Thiếu"].map((x) => <th key={x}>{x}</th>)}</tr></thead>
            <tbody>{Object.entries(bctc.data.by_exchange).map(([ex, r]: any) => <tr key={ex}><td>{ex}</td><td>{r.listed}</td><td>{r.with_bctc}</td><td>{r.coverage_pct}%</td><td>{r.with_fy2025}</td><td>{r.only_fy2024_or_older}</td><td>{r.missing_count}</td></tr>)}</tbody></table></div>
          <p className="mt-2 text-xs text-slate-500">Nguồn {bctc.data.source}; cập nhật {bctc.data.generated_at}. UPCOM không được nguồn này bao phủ.</p>
          {(["HOSE", "HNX", "UPCOM"] as const).map((ex) => <details key={ex} className="mt-2 text-sm"><summary className="cursor-pointer font-medium">Mã {ex} thiếu BCTC ({bctc.data.by_exchange[ex].missing_count})</summary><p className="mt-1 break-words text-xs text-slate-600">{(bctc.data.missing[ex] || []).join(", ")}</p></details>)}
          <details className="mt-2 text-sm"><summary className="cursor-pointer font-medium">Mã có trong nguồn nhưng không còn niêm yết ({bctc.data.delisted_count})</summary><p className="mt-1 break-words text-xs text-slate-600">{(bctc.data.delisted || []).join(", ")}</p></details>
        </>}
      </Card>
      <Card title="Quy ước">
        <ul className="list-disc pl-5 text-sm space-y-1">
          <li>BCTC năm: vn-annual-report-miner (Tumiqa, MIT) – HSX 409 mã, HNX 307 mã, FY2009–FY2025; không có UPCOM, không có quý → P/E theo FY gần nhất.</li>
          <li>Số CP: listedShare từ Vietcap getList; nếu thiếu, xấp xỉ = vốn góp / 10.000đ (gắn nhãn).</li>
          <li>Ngành: vnstock list_by_industry (ICB 1–4), bù fiinpro_icb_companies.csv; không có ở cả hai → “Chưa phân loại”.</li>
          <li>Thiếu số → “–” kèm lý do; không dùng dữ liệu giả lập cho mã thật.</li>
          <li>Lỗi nguồn đã phát hiện: SSI FY2025 trong arminer trùng khớp FY2024 → tự loại năm đó.</li>
        </ul>
      </Card>
    </div>
  );
}
