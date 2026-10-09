"use client";
import Link from "next/link";
import Search from "@/components/Search";
import { AsOf, Card, ErrorBox, Loading, SortTable, Stat } from "@/components/ui";
import { CompareLine, MarketTreemap } from "@/components/Charts";
import { useRouter } from "next/navigation";
import { useApi } from "@/lib/api";
import { bnLabel, cls, dmy, num, pct, times } from "@/lib/fmt";

const urlOf = (s: string) => (s.match(/https?:[^)\s]+/) || [])[0];
const industryView = (items: any[] = []) => [...items].filter((r) => r.score != null).sort((a, b) => b.score - a.score);

export default function Home() {
  const m = useApi<any>("/api/py/market");
  const mac = useApi<any>("/api/py/macro?world_bank=false");
  const sec = useApi<any>("/api/py/sectors?level=1");
  const vn = m.data?.vnindex;
  const router = useRouter();
  const sec2 = useApi<any>("/api/py/sectors?level=2");
  return (
    <div className="space-y-5">
      <div className="card bg-gradient-to-r from-[#0b3b6f] to-[#14598f] text-white">
        <h1 className="text-xl md:text-2xl font-bold">Hệ thống phân tích cơ hội đầu tư cổ phiếu</h1>
        <p className="text-sky-100 text-sm mb-3">Vĩ mô → Ngành (ICB 4 cấp, toàn bộ ~1.500 mã HOSE/HNX/UPCOM) → Doanh nghiệp → Định giá theo loại DN → Khuyến nghị → Báo cáo PDF</p>
        <Search big />
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <Card title="VN-Index" right={<AsOf p={m.data?.vnindex_provenance} />} className="md:col-span-2">
          <ErrorBox error={m.error} />
          {m.loading && <Loading />}
          {vn && (
            <>
              <div className="flex flex-wrap gap-3 mb-2">
                <Stat label="Đóng cửa" value={num(vn.close, 2)} sub={<span className={cls(vn.change_1d)}>{pct(vn.change_1d, 2, true)}</span>} />
                <Stat label="1 tháng" value={<span className={cls(vn.ret_1m)}>{pct(vn.ret_1m, 1, true)}</span>} />
                <Stat label="3 tháng" value={<span className={cls(vn.ret_3m)}>{pct(vn.ret_3m, 1, true)}</span>} />
                <Stat label="Từ đầu năm" value={<span className={cls(vn.ret_ytd)}>{pct(vn.ret_ytd, 1, true)}</span>} />
                <Stat label="P/E gộp thị trường" value={times(m.data.stats.pe_aggregate)} sub="vốn hoá / LNST FY gần nhất" />
              </div>
              <CompareLine data={vn.series} lines={[{ key: "close", name: "VN-Index", color: "#0b3b6f" }]} height={200} />
            </>
          )}
        </Card>
        <Card title="Thị trường" right={<AsOf p={m.data?.provenance} />}>
          {m.data && (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <Stat label="Số mã" value={num(m.data.stats.n_symbols)} sub={Object.entries(m.data.stats.by_exchange).map(([k, v]) => `${k} ${v}`).join(" · ")} />
              <Stat label="Tổng vốn hoá" value={bnLabel(m.data.stats.market_cap)} />
              <Stat label="Tăng / Giảm" value={<><span className="text-up">{m.data.stats.advancers}</span> / <span className="text-down">{m.data.stats.decliners}</span></>} sub={`${m.data.stats.unchanged} đứng giá/không GD`} />
              <Stat label="Phủ ngành ICB" value={pct(m.data.stats.industry_coverage, 1)} sub={`${m.data.stats.n_unclassified} mã chưa phân loại`} />
              <Stat label="Có BCTC" value={num(m.data.stats.n_with_bctc)} sub="HSX/HNX (arminer)" />
              <Stat label="Đủ thanh khoản" value={num(m.data.stats.n_liquid)} sub="GTGD TB20 ≥ 1 tỷ" />
            </div>
          )}
        </Card>
      </div>

      <Card title="Vĩ mô Việt Nam – số mới nhất đã công bố" right={<AsOf p={mac.data?.provenance} label="Cập nhật" />}>
        <ErrorBox error={mac.error} />
        {mac.data && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {mac.data.table.filter((r: any) => String(r.period).startsWith("2026")).map((r: any) => (
              <div key={r.key + r.period} className="stat">
                <div className="text-xs text-slate-500">{r.label} <span className="text-slate-400">({r.period})</span></div>
                <div className="text-lg font-semibold">{r.unit === "VND" ? num(r.value) : num(r.value, 2) + r.unit}</div>
                <div className="text-[11px] text-slate-500" title={r.source}>
                  {String(r.source).replace(/\(https?:[^)]+\)/, "").slice(0, 60)} · {dmy(r.as_of)}
                  {urlOf(r.source) && <> · <a className="link" target="_blank" rel="noreferrer" href={urlOf(r.source)}>nguồn</a></>}
                </div>
              </div>
            ))}
          </div>
        )}
        {mac.data && <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
          <p className="text-sm"><b>{mac.data.score >= 60 ? "THUẬN LỢI" : mac.data.score < 40 ? "BẤT LỢI" : "TRUNG TÍNH"}</b> · Điểm vĩ mô {num(mac.data.score, 0)}/100</p>
          <details className="mt-1 text-sm text-slate-600"><summary className="cursor-pointer font-medium">Vì sao?</summary><ul className="mt-1 list-disc space-y-1 pl-5">{mac.data.commentary?.slice(0, 3).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>
        </div>}
      </Card>

      {sec.data && <Card title="Ngành: ưu tiên và thận trọng theo điểm có sẵn">
        {(() => {
          const ranked = industryView(sec.data.items);
          const priority = ranked.slice(0, 5), cautious = ranked.slice(-3).reverse();
          const row = (r: any, label: string) => <div key={r.slug} className="flex items-start justify-between gap-3 border-b py-2 last:border-0">
            <div><Link className="link font-semibold" href={`/nganh/${r.slug}`}>{r.name}</Link><details className="text-xs text-slate-500"><summary className="cursor-pointer">Vì sao?</summary><span>{Object.entries(r.score_components || {}).map(([k, v]) => `${k}: ${num(v, 0)}/100`).join(" · ") || "Thiếu thành phần điểm để giải thích."}</span></details></div>
            <span className="text-right text-xs"><b>{label}</b><br />{num(r.score, 0)}/100</span>
          </div>;
          return <div className="grid gap-4 md:grid-cols-2"><div><h3 className="font-semibold text-emerald-700">Top 5 ưu tiên</h3>{priority.map((r: any) => row(r, "ƯU TIÊN"))}</div><div><h3 className="font-semibold text-amber-700">3 ngành cần thận trọng</h3>{cautious.map((r: any) => row(r, "THẬN TRỌNG"))}</div></div>;
        })()}
      </Card>}
      <Card title="Cơ hội đầu tư">
        <p className="text-sm text-slate-600">Bảng universe hiện chưa có upside tính sẵn nên không xếp hạng 10 mã tại trang chủ. Mở hồ sơ từng mã để xem định giá, kịch bản và upside đã tính.</p>
        <Link className="link mt-2 inline-block" href="/thi-truong">Mở toàn bộ mã cổ phiếu →</Link>
      </Card>

      <Card title="Bản đồ thị trường theo ngành cấp 2 (ô = vốn hoá, màu = hiệu suất 1 tháng)" right={<AsOf p={sec2.data?.provenance} />}>
        {sec2.loading && <Loading what="bản đồ ngành" />}
        {sec2.data && <MarketTreemap items={sec2.data.items} onClick={(slug) => router.push(`/nganh/${slug}`)} />}
      </Card>

      <Card title="Ngành cấp 1 (ICB) – toàn thị trường" right={<span><AsOf p={sec.data?.provenance} /> <Link className="link text-sm ml-2" href="/nganh">Xem tất cả cấp →</Link></span>}>
        <ErrorBox error={sec.error} />
        {sec.loading && <Loading what="ngành" />}
        {sec.data && (
          <SortTable rows={sec.data.items} rowKey={(r) => r.slug} initialSort="market_cap" onRow={(r) => `/nganh/${r.slug}`}
            cols={[
              { key: "name", label: "Ngành" },
              { key: "rank_score", label: "Đánh giá", sortValue: (r) => r.rank_score, render: (r) => r.rank_score <= 5 ? "ƯU TIÊN" : r.rank_score > sec.data.items.length - 3 ? "THẬN TRỌNG" : "TRUNG LẬP" },
              { key: "n_symbols", label: "Số mã", num: true },
              { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
              { key: "market_weight", label: "Tỷ trọng", num: true, render: (r) => pct(r.market_weight) },
              { key: "ret_1m", label: "1T", num: true, render: (r) => <span className={cls(r.ret_1m)}>{pct(r.ret_1m)}</span> },
              { key: "ret_ytd", label: "YTD", num: true, render: (r) => <span className={cls(r.ret_ytd)}>{pct(r.ret_ytd)}</span> },
              { key: "pe", label: "P/E trung vị ngành", num: true, sortValue: (r) => r.pe?.median, render: (r) => times(r.pe?.median) },
              { key: "pb", label: "P/B trung vị ngành", num: true, sortValue: (r) => r.pb?.median, render: (r) => times(r.pb?.median, 2) },
              { key: "roe", label: "ROE TV", num: true, sortValue: (r) => r.roe?.median, render: (r) => pct(r.roe?.median) },
              { key: "score", label: "Điểm", num: true, render: (r) => num(r.score, 0) },
            ]} />
        )}
      </Card>
    </div>
  );
}
