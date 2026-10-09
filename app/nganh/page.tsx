"use client";
import { useMemo, useState } from "react";
import { AsOf, Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { useApi } from "@/lib/api";
import { bnLabel, cls, num, pct, times } from "@/lib/fmt";

export default function Nganh() {
  const [level, setLevel] = useState(1);
  const [draft, setDraft] = useState({ minSymbols: 0, minCap: 0, minLiquid: 0, parent: "" });
  const [filters, setFilters] = useState(draft);
  const [exch, setExch] = useState("");
  const { data, error, loading } = useApi<any>(`/api/py/sectors?level=${level}${exch ? `&exchange=${exch}` : ""}`);
  const rows = useMemo(() => (data?.items || []).filter((r: any) =>
    r.n_symbols >= filters.minSymbols && r.market_cap >= filters.minCap * 1e9 &&
    r.n_liquid >= filters.minLiquid && (!filters.parent || r.icb1 === filters.parent)), [data, filters]);
  const parents = useMemo(() => Array.from(new Set((data?.items || []).map((r: any) => r.icb1).filter(Boolean))) as string[], [data]);
  const b = data?.benchmark || {};
  const apply = () => setFilters({ ...draft });
  const clear = () => {
    const empty = { minSymbols: 0, minCap: 0, minLiquid: 0, parent: "" };
    setDraft(empty);
    setFilters(empty);
  };
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
          <label>Sàn{" "}
            <select className="sel" value={exch} onChange={(e) => setExch(e.target.value)}>
              <option value="">Toàn thị trường</option><option>HOSE</option><option>HNX</option><option>UPCOM</option><option value="HOSE,HNX">HOSE + HNX</option>
            </select>
          </label>
          {level > 1 && (
            <label>Thuộc ngành cấp 1{" "}
              <select className="sel" value={draft.parent} onChange={(e) => setDraft({ ...draft, parent: e.target.value })} onBlur={apply}>
                <option value="">Tất cả</option>
                {parents.map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
          )}
          <label>Số mã tối thiểu{" "}<input className="sel w-20" type="number" value={draft.minSymbols} onChange={(e) => setDraft({ ...draft, minSymbols: +e.target.value })} onBlur={apply} onKeyDown={(e) => e.key === "Enter" && apply()} /></label>
          <label>Vốn hoá tối thiểu (tỷ đồng){" "}<input className="sel w-28" type="number" value={draft.minCap} onChange={(e) => setDraft({ ...draft, minCap: +e.target.value })} onBlur={apply} onKeyDown={(e) => e.key === "Enter" && apply()} /></label>
          <label>Mã đủ thanh khoản tối thiểu{" "}<input className="sel w-20" type="number" value={draft.minLiquid} onChange={(e) => setDraft({ ...draft, minLiquid: +e.target.value })} onBlur={apply} onKeyDown={(e) => e.key === "Enter" && apply()} /></label>
          <button className="btn" onClick={apply}>Áp dụng</button>
          <button className="btn-ghost" onClick={clear}>Xoá lọc</button>
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
      <Card title={`Đang hiển thị ${rows.length}/${data?.items?.length ?? 0} ngành cấp ${level}`}>
        <ErrorBox error={error} />
        {loading && <Loading what="ngành" />}
        {data && rows.length === 0 && <p className="py-5 text-sm text-slate-600">Không có ngành phù hợp. Hãy nới điều kiện lọc hoặc bấm “Xoá lọc”.</p>}
        {data && rows.length > 0 && (
          <SortTable rows={rows} rowKey={(r) => r.slug} initialSort="market_cap" onRow={(r) => `/nganh/${r.slug}`}
            cols={[
              { key: "name", label: "Ngành", title: "Ngành kinh tế theo phân loại ICB" },
              ...(level > 1 ? [{ key: "icb1", label: "Ngành cấp 1", title: "Ngành ICB cấp cao nhất" }] : []),
              { key: "n_symbols", label: "Tổng số mã", num: true, title: "Số mã trong ngành" },
              { key: "n_liquid", label: "Mã đủ thanh khoản", num: true, title: "Số mã có giá trị giao dịch trung bình 20 phiên từ 1 tỷ đồng" },
              { key: "market_cap", label: "Tổng vốn hoá", num: true, title: "Tổng vốn hoá thị trường của các mã trong ngành", render: (r: any) => bnLabel(r.market_cap) },
              { key: "market_weight", label: "Tỷ trọng vốn hoá", num: true, title: "Tỷ trọng vốn hoá ngành trên toàn thị trường", render: (r: any) => pct(r.market_weight, 2) },
              { key: "avg_value_20d", label: "GTGD bình quân 20 phiên", num: true, title: "Giá trị giao dịch trung bình mỗi phiên trong 20 phiên gần nhất", render: (r: any) => num(r.avg_value_20d / 1e9, 0) + " tỷ" },
              { key: "ret_1m", label: "Hiệu suất 1 tháng", num: true, title: "Biến động giá trong khoảng 1 tháng", render: (r: any) => <span className={cls(r.ret_1m)}>{pct(r.ret_1m)}</span> },
              { key: "ret_3m", label: "Hiệu suất 3 tháng", num: true, title: "Biến động giá trong khoảng 3 tháng", render: (r: any) => <span className={cls(r.ret_3m)}>{pct(r.ret_3m)}</span> },
              { key: "ret_ytd", label: "Hiệu suất từ đầu năm", num: true, title: "Biến động giá từ đầu năm", render: (r: any) => <span className={cls(r.ret_ytd)}>{pct(r.ret_ytd)}</span> },
              { key: "ret_1y", label: "Hiệu suất 1 năm", num: true, title: "Biến động giá trong 1 năm", render: (r: any) => <span className={cls(r.ret_1y)}>{pct(r.ret_1y)}</span> },
              { key: "ret_3m_vs_index", label: "3 tháng so với VN-Index", num: true, title: "Hiệu suất 3 tháng của ngành trừ hiệu suất VN-Index", render: (r: any) => <span className={cls(r.ret_3m_vs_index)}>{pct(r.ret_3m_vs_index, 1, true)}</span> },
              { key: "pe", label: "P/E trung vị", num: true, title: "Trung vị P/E của các mã đủ thanh khoản", sortValue: (r: any) => r.pe?.median, render: (r: any) => times(r.pe?.median) },
              { key: "pe_aggregate", label: "P/E tổng hợp", num: true, title: "Tổng vốn hoá chia tổng lợi nhuận sau thuế cổ đông công ty mẹ", render: (r: any) => times(r.pe_aggregate) },
              { key: "pb", label: "P/B trung vị", num: true, title: "Trung vị P/B của các mã đủ thanh khoản", sortValue: (r: any) => r.pb?.median, render: (r: any) => times(r.pb?.median, 2) },
              { key: "roe", label: "ROE trung vị", num: true, title: "Trung vị ROE của các mã đủ thanh khoản", sortValue: (r: any) => r.roe?.median, render: (r: any) => pct(r.roe?.median) },
              { key: "score", label: "Điểm", num: true, render: (r: any) => num(r.score, 0) },
              { key: "rank_score", label: "Hạng", num: true },
            ]} />
        )}
      </Card>
    </div>
  );
}
