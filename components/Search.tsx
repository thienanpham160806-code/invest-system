"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getJSON } from "@/lib/api";
import { bnLabel, price } from "@/lib/fmt";

export default function Search({ big = false }: { big?: boolean }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const router = useRouter();
  const t = useRef<any>(null);
  useEffect(() => {
    clearTimeout(t.current);
    if (!q.trim()) { setItems([]); return; }
    t.current = setTimeout(() => getJSON(`/api/py/search?q=${encodeURIComponent(q)}`).then((d) => { setItems(d.items); setIdx(0); setOpen(true); }).catch(() => {}), 150);
  }, [q]);
  const go = (s: string) => { setOpen(false); setQ(""); router.push(`/stock/${s}`); };
  return (
    <div className="relative w-full">
      <input
        value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setIdx((i) => Math.min(i + 1, items.length - 1));
          if (e.key === "ArrowUp") setIdx((i) => Math.max(i - 1, 0));
          if (e.key === "Enter") { if (items[idx]) go(items[idx].symbol); else if (q.trim()) go(q.trim().toUpperCase()); }
        }}
        placeholder="Nhập mã hoặc tên DN (vd FPT, Vinamilk)…"
        className={`w-full rounded-md border border-slate-300 bg-white px-3 ${big ? "py-3 text-lg" : "py-1.5 text-sm"} text-slate-900 outline-none focus:ring-2 focus:ring-sky-500`}
      />
      {open && items.length > 0 && (
        <ul className="absolute z-30 mt-1 w-full max-h-80 overflow-auto rounded-md border border-slate-200 bg-white shadow-lg text-slate-900">
          {items.map((it, i) => (
            <li key={it.symbol} onMouseDown={() => go(it.symbol)} className={`px-3 py-2 cursor-pointer text-sm flex justify-between gap-2 ${i === idx ? "bg-sky-50" : ""}`}>
              <span><b>{it.symbol}</b> <span className="text-slate-500">{it.exchange}</span> · {it.name}</span>
              <span className="text-slate-500 whitespace-nowrap">{price(it.price)} · {bnLabel(it.market_cap)}</span>
            </li>))}
        </ul>)}
    </div>
  );
}
