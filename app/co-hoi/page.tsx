"use client";
import { useState } from "react";
import Link from "next/link";
import { AsOf, Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { downloadCSV, toCSV, useApi } from "@/lib/api";
import { bnLabel, num, pct, price } from "@/lib/fmt";

export default function Opportunities() {
  const [exchange, setExchange] = useState("");
  const [q, setQ] = useState("");
  const [minimum, setMinimum] = useState(0);
  const [marketCap, setMarketCap] = useState(0);
  const [industry, setIndustry] = useState("");
  const [rating, setRating] = useState("");
  const [confidence, setConfidence] = useState("");
  const [minimumUpside, setMinimumUpside] = useState("");
  const [showWatch, setShowWatch] = useState(false);
  const params = new URLSearchParams({ limit: "2000", eligible_only: String(!showWatch) });
  if (exchange) params.set("exchange", exchange);
  if (q.trim()) params.set("q", q.trim());
  if (minimum) params.set("min_value", String(minimum * 1e9));
  if (industry.trim()) params.set("industry", industry.trim());
  if (rating) params.set("rating", rating);
  if (confidence) params.set("confidence", confidence);
  if (minimumUpside) params.set("min_upside", String(Number(minimumUpside) / 100));
  if (marketCap) params.set("min_market_cap", String(marketCap * 1e9));
  const { data, error, loading } = useApi<any>(`/api/py/opportunities?${params}`);
  const rows = data?.items || [];
  const exportRows = () => downloadCSV("co-hoi-dau-tu.csv", toCSV(rows, [
    { key: "symbol", label: "Mã" }, { key: "name", label: "Doanh nghiệp" }, { key: "exchange", label: "Sàn" },
    { key: "industry", label: "Ngành" }, { key: "price", label: "Giá" }, { key: "target_price", label: "Giá trị cơ sở" },
    { key: "upside", label: "Upside" }, { key: "confidence", label: "Độ tin cậy" }, { key: "rating", label: "Đánh giá" },
    { key: "score", label: "Điểm" }, { key: "avg_value_20d", label: "GTGD TB20" },
  ]));
  return <div className="space-y-4">
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl font-bold">Cơ hội đầu tư</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">Điểm cơ hội dùng điểm tổng hợp; hòa điểm xét upside rồi thanh khoản. Mã đủ điều kiện có BCTC, không có kiểm tra dữ liệu FAIL, độ tin cậy từ trung bình, GTGD TB20 từ 5 tỷ và upside dương dưới 150%. Đây là tham khảo, không phải khuyến nghị mua.</p>
      </div><AsOf p={data?.provenance} label="Snapshot" />
    </header>
    <Card>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input className="sel" placeholder="Lọc mã hoặc tên" aria-label="Lọc mã hoặc tên" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="sel" aria-label="Lọc theo sàn" value={exchange} onChange={(e) => setExchange(e.target.value)}>
          <option value="">Mọi sàn</option><option>HOSE</option><option>HNX</option><option>UPCOM</option>
        </select>
        <label>Lọc GTGD TB20 từ <input className="sel w-24" type="number" min="0" value={minimum} onChange={(e) => setMinimum(Math.max(0, +e.target.value))} /> tỷ</label>
        <input className="sel" placeholder="Ngành ICB" aria-label="Lọc theo ngành" value={industry} onChange={(e) => setIndustry(e.target.value)} />
        <select className="sel" aria-label="Lọc theo khuyến nghị" value={rating} onChange={(e) => setRating(e.target.value)}>
          <option value="">Mọi đánh giá</option><option>MUA</option><option>KHẢ QUAN</option><option>NẮM GIỮ</option><option>KÉM KHẢ QUAN</option><option>BÁN</option><option>THEO DÕI</option>
        </select>
        <select className="sel" aria-label="Lọc theo độ tin cậy" value={confidence} onChange={(e) => setConfidence(e.target.value)}>
          <option value="">Mọi độ tin cậy</option><option>CAO</option><option>TRUNG BÌNH</option><option>THẤP</option>
        </select>
        <label>Upside tối thiểu % <input className="sel w-24" type="number" value={minimumUpside} onChange={(e) => setMinimumUpside(e.target.value)} /></label>
        <label>Vốn hoá tối thiểu, tỷ <input className="sel w-24" type="number" min="0" value={marketCap} onChange={(e) => setMarketCap(Math.max(0, +e.target.value))} /></label>
        <div className="flex rounded border border-slate-200 p-1" role="tablist" aria-label="Nhóm xếp hạng">
          <button className={`rounded px-2 py-1 ${!showWatch ? "bg-blue-900 text-white" : ""}`} onClick={() => setShowWatch(false)} role="tab" aria-selected={!showWatch}>Đủ điều kiện</button>
          <button className={`rounded px-2 py-1 ${showWatch ? "bg-blue-900 text-white" : ""}`} onClick={() => setShowWatch(true)} role="tab" aria-selected={showWatch}>Theo dõi</button>
        </div>
        <button className="btn-ghost" onClick={() => { setExchange(""); setQ(""); setMinimum(0); setMarketCap(0); setIndustry(""); setRating(""); setConfidence(""); setMinimumUpside(""); }}>Xóa bộ lọc</button>
        <button className="btn" disabled={!rows.length} onClick={exportRows}>Tải CSV</button>
        {data && <span className="text-slate-600">{num(data.total)} mã đạt bộ lọc · {num(data.analyzed_count)} / {num(data.universe_count)} mã đã phân tích</span>}
      </div>
    </Card>
    <Card>
      <ErrorBox error={error} />{loading && <Loading what="xếp hạng cơ hội" />}
      {data && !data.ready && <p className="text-sm text-slate-600">{data.note}</p>}
      {data?.ready && rows.length === 0 && <p className="text-sm text-slate-600">Chưa có mã đáp ứng bộ lọc trong snapshot hiện tại.</p>}
      {!!rows.length && <SortTable rows={rows} rowKey={(r) => r.symbol} initialSort="rank" onRow={(r) => `/stock/${r.symbol}`}
        cols={[
          { key: "rank", label: "Hạng", num: true },
          { key: "symbol", label: "Mã" }, { key: "name", label: "Doanh nghiệp" }, { key: "exchange", label: "Sàn" },
          { key: "industry", label: "Ngành" }, { key: "price", label: "Giá", num: true, render: (r) => price(r.price) },
          { key: "target_price", label: "Giá trị cơ sở", num: true, render: (r) => price(r.target_price) },
          { key: "upside", label: "Upside", num: true, sortValue: (r) => r.upside, render: (r) => pct(r.upside, 1, true) },
          { key: "confidence", label: "Độ tin cậy" }, { key: "rating", label: "Đánh giá" },
          { key: "score", label: "Điểm", num: true, render: (r) => num(r.score, 0) },
          { key: "avg_value_20d", label: "GTGD TB20", num: true, render: (r) => bnLabel(r.avg_value_20d) },
          { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
          { key: "reason", label: "Luận điểm", render: (r) => <span title={(r.tracking_reasons || []).join("; ")}>{showWatch ? (r.tracking_reasons || []).join("; ") : r.reason}</span> },
        ]} />}
      {data?.generated_at && <p className="mt-3 text-xs text-slate-500">Tạo lúc {data.generated_at}. Snapshot có {num(data.errors)} lỗi phân tích; xem ngày giá và độ tin cậy trên hồ sơ từng mã.</p>}
    </Card>
    <p className="text-sm"><Link className="link" href="/thi-truong">Xem toàn bộ universe →</Link></p>
  </div>;
}
