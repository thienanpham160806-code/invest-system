"use client";
import { useState } from "react";
import MacroPanel from "@/components/MacroPanel";

const TYPES = [
  ["NON_FINANCIAL", "Doanh nghiệp phi tài chính"], ["BANK", "Ngân hàng"], ["SECURITIES", "Chứng khoán"],
  ["INSURANCE", "Bảo hiểm"], ["REAL_ESTATE", "Bất động sản"],
] as const;

export default function MacroPage() {
  const [ctype, setCtype] = useState<string>("NON_FINANCIAL");
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Vĩ mô</h1>
          <p className="text-sm text-slate-600">Trong nước (GSO/NSO, NHNN – có nguồn từng dòng) và bối cảnh quốc tế (FRED): lãi suất Fed, lợi suất Mỹ 10 năm, chỉ số USD, dầu Brent, VIX.</p>
        </div>
        <label className="text-sm">
          <span className="mr-2 text-slate-600">Tác động lên nhóm</span>
          <select className="sel" value={ctype} onChange={(e) => setCtype(e.target.value)} aria-label="Nhóm doanh nghiệp">
            {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
      </div>
      <MacroPanel ctype={ctype} />
    </div>
  );
}
