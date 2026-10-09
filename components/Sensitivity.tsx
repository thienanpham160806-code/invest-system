"use client";
import { useMemo, useState } from "react";
import { cls, num, pct, price } from "@/lib/fmt";

/** Thu gia dinh dinh gia ngay tren trinh duyet: P/E, P/B muc tieu, Ke & g (P/B Gordon cho ngan hang).
 *  Phuong phap khong co dau vao tuong ung (DCF, EV/EBITDA) giu nguyen gia tri co so cua may chu. */
export default function Sensitivity({ d }: { d: any }) {
  const v = d.valuation;
  const methods: any[] = (v.methods || []).filter((m: any) => m.weight > 0);
  const pe = methods.find((m) => m.key === "pe_relative");
  const pb = methods.find((m) => m.key === "pb_relative");
  const gd = methods.find((m) => m.key === "justified_pb");
  const [peT, setPeT] = useState<number>(pe?.inputs?.["P/E mục tiêu"] ?? 10);
  const [pbT, setPbT] = useState<number>(pb?.inputs?.["P/B mục tiêu"] ?? 1.5);
  const [ke, setKe] = useState<number>(gd?.inputs?.Ke ?? v.assumptions?.ke ?? 0.12);
  const [g, setG] = useState<number>(gd?.inputs?.["g bền vững"] ?? 0.05);
  const res = useMemo(() => {
    const vals: Record<string, number> = {};
    for (const m of methods) {
      if (m.key === "pe_relative") vals[m.key] = (m.inputs["EPS dự phóng"] || 0) * peT;
      else if (m.key === "pb_relative") vals[m.key] = (m.inputs["BVPS"] || 0) * pbT;
      else if (m.key === "justified_pb") {
        const roe = m.inputs["ROE bq 3 năm"];
        const p = ke - g > 0.005 ? Math.min(Math.max((roe - g) / (ke - g), 0.3), 4) : 4;
        vals[m.key] = (m.inputs["BVPS"] || 0) * p;
      } else vals[m.key] = m.values.base;
    }
    const tw = methods.reduce((s, m) => s + m.weight, 0) || 1;
    const target = methods.reduce((s, m) => s + vals[m.key] * m.weight, 0) / tw;
    return { vals, target, upside: d.price ? target / d.price - 1 : null };
  }, [methods, peT, pbT, ke, g, d.price]);
  if (!methods.length) return null;
  const Slider = ({ label, value, set, min, max, step, fmt }: any) => (
    <label className="block text-sm">
      <div className="flex justify-between"><span>{label}</span><b>{fmt(value)}</b></div>
      <input type="range" className="w-full accent-[#0b3b6f]" min={min} max={max} step={step} value={value} onChange={(e) => set(+e.target.value)} />
    </label>
  );
  return (
    <section className="card">
      <div className="flex flex-wrap justify-between gap-2 mb-3">
        <h2 className="card-title">Thử giả định (độ nhạy định giá)</h2>
        <button className="btn-ghost" onClick={() => { setPeT(pe?.inputs?.["P/E mục tiêu"] ?? 10); setPbT(pb?.inputs?.["P/B mục tiêu"] ?? 1.5); setKe(gd?.inputs?.Ke ?? 0.12); setG(gd?.inputs?.["g bền vững"] ?? 0.05); }}>Về giả định gốc</button>
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        <div className="space-y-3 md:col-span-2">
          {pe && <Slider label={`P/E mục tiêu (gốc ${num(pe.inputs["P/E mục tiêu"], 1)}x – trung vị ngành)`} value={peT} set={setPeT} min={3} max={30} step={0.1} fmt={(x: number) => num(x, 1) + "x"} />}
          {pb && <Slider label={`P/B mục tiêu (gốc ${num(pb.inputs["P/B mục tiêu"], 2)}x)`} value={pbT} set={setPbT} min={0.3} max={5} step={0.05} fmt={(x: number) => num(x, 2) + "x"} />}
          {gd && <Slider label="Chi phí vốn CSH Ke (Gordon)" value={ke} set={setKe} min={0.08} max={0.2} step={0.0025} fmt={(x: number) => pct(x, 2)} />}
          {gd && <Slider label="Tăng trưởng dài hạn g (Gordon)" value={g} set={setG} min={0} max={0.1} step={0.0025} fmt={(x: number) => pct(x, 2)} />}
          <p className="text-xs text-slate-500">DCF và EV/EBITDA giữ giá trị cơ sở của máy chủ (cần dòng tiền chi tiết). Trọng số phương pháp giữ nguyên.</p>
        </div>
        <div className="space-y-2">
          <div className="stat"><div className="text-xs text-slate-500">Giá mục tiêu theo giả định thử</div><div className="text-2xl font-bold">{price(Math.round(res.target / 100) * 100)}</div>
            <div className={cls(res.upside)}>Upside {pct(res.upside, 1, true)}</div></div>
          <table className="tbl"><tbody>
            {methods.map((m) => <tr key={m.key}><td>{m.label}</td><td className="text-right">{price(res.vals[m.key])}</td><td className="text-right">{pct(m.weight, 0)}</td></tr>)}
          </tbody></table>
        </div>
      </div>
    </section>
  );
}
