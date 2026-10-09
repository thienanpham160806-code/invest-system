"use client";
import { useState } from "react";
import { AsOf, Card, ErrorBox, Loading, SortTable } from "@/components/ui";
import { downloadCSV, getJSON, toCSV, useApi } from "@/lib/api";
import { bnLabel, cls, num, pct, price, times } from "@/lib/fmt";

export default function Universe() {
  const [exchange, setExchange] = useState("");
  const [minValue, setMinValue] = useState(0);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("market_cap");
  const size = 100;
  const url = `/api/py/universe?page=${page}&page_size=${size}&sort=${sort}${exchange ? `&exchange=${exchange}` : ""}${minValue ? `&min_value=${minValue * 1e9}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const { data, error, loading } = useApi<any>(url);
  const pages = data ? Math.ceil(data.total / size) : 1;
  const exportAll = async () => {
    const all = await getJSON(url.replace(/page=\d+&page_size=\d+/, "page=1&page_size=2000"));
    downloadCSV("toan_thi_truong.csv", toCSV(all.items, Object.keys(all.items[0] || {}).map((k) => ({ key: k, label: k }))));
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-between items-end gap-2">
        <h1 className="text-xl font-bold">Bảng toàn thị trường</h1>
        <AsOf p={data?.provenance} />
      </div>
      <Card>
        <div className="flex flex-wrap gap-3 items-center text-sm">
          <input className="sel" placeholder="Lọc mã/tên" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <select className="sel" value={exchange} onChange={(e) => { setExchange(e.target.value); setPage(1); }}>
            <option value="">Mọi sàn</option><option>HOSE</option><option>HNX</option><option>UPCOM</option>
          </select>
          <label>GTGD TB20 ≥ <input className="sel w-20" type="number" value={minValue} onChange={(e) => { setMinValue(+e.target.value); setPage(1); }} /> tỷ</label>
          <select className="sel" value={sort} onChange={(e) => setSort(e.target.value)}>
            {[["market_cap", "Vốn hoá"], ["avg_value_20d", "Thanh khoản"], ["ret_ytd", "Hiệu suất YTD"], ["ret_1y", "Hiệu suất 1N"], ["roe", "ROE"], ["pe", "P/E"]].map(([k, l]) => <option key={k} value={k}>Sắp theo {l}</option>)}
          </select>
          <button className="btn" onClick={exportAll}>Tải CSV (đã lọc)</button>
          {data && <span className="text-slate-600">{num(data.total)} mã · trang {page}/{pages}</span>}
          <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
          <button className="btn-ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>›</button>
        </div>
      </Card>
      <Card>
        <ErrorBox error={error} />
        {loading && <Loading />}
        {data && (
          <SortTable rows={data.items} rowKey={(r) => r.symbol} onRow={(r) => `/stock/${r.symbol}`}
            cols={[
              { key: "symbol", label: "Mã" },
              { key: "name", label: "Tên", render: (r) => <span className="inline-block max-w-56 truncate align-bottom" title={r.name}>{r.name}</span> },
              { key: "exchange", label: "Sàn" }, { key: "icb2", label: "Ngành cấp 2" }, { key: "icb4", label: "ICB4" },
              { key: "price", label: "Giá", num: true, render: (r) => price(r.price) },
              { key: "change_1d", label: "±", num: true, render: (r) => <span className={cls(r.change_1d)}>{pct(r.change_1d)}</span> },
              { key: "market_cap", label: "Vốn hoá", num: true, render: (r) => bnLabel(r.market_cap) },
              { key: "pe", label: "P/E", num: true, render: (r) => times(r.pe) }, { key: "pb", label: "P/B", num: true, render: (r) => times(r.pb, 2) },
              { key: "roe", label: "ROE", num: true, render: (r) => pct(r.roe) },
              { key: "ret_ytd", label: "YTD", num: true, render: (r) => <span className={cls(r.ret_ytd)}>{pct(r.ret_ytd)}</span> },
              { key: "avg_value_20d", label: "GTGD TB20", num: true, render: (r) => num(r.avg_value_20d / 1e9, 1) + " tỷ" },
              { key: "fin_year", label: "BCTC", render: (r) => (r.fin_year ? `FY${r.fin_year}` : "–") },
            ]} />
        )}
      </Card>
    </div>
  );
}
