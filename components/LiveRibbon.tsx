"use client";
import { useRef } from "react";
import { useLive } from "@/lib/useLive";
import { bn, cls, num, pct } from "@/lib/fmt";

export default function LiveRibbon() {
  const { data } = useLive<any>("/api/py/market/live");
  const previous = useRef<Record<string, number>>({});
  return <div className="flex min-h-8 flex-wrap items-center gap-x-4 gap-y-1 border-t border-white/15 px-4 py-1 text-xs">
    <span className="flex items-center gap-1.5"><i className={`h-2 w-2 rounded-full ${data?.is_open ? "bg-emerald-400" : "bg-slate-400"}`} />{data?.is_open ? "LIVE" : data?.session || "Đang tải"}</span>
    {(data?.indices || []).map((x: any) => {
      const old = previous.current[x.symbol], flash = old !== undefined && old !== x.price ? x.price > old ? "price-up" : "price-down" : "";
      previous.current[x.symbol] = x.price;
      return <span key={x.symbol} className={`tabular-nums ${flash}`} title={`${x.source} · nến ${x.as_of || "—"}${x.stale ? " · dữ liệu cũ" : ""}`}>
        {x.name} <b>{x.price == null ? "—" : num(x.price, 2)}</b> <span className={cls(x.change)}>{x.change == null ? "" : `${x.change > 0 ? "+" : ""}${num(x.change, 2)} (${pct(x.change_pct, 2, true)})`}</span> · GTGD {x.turnover == null ? "—" : `${bn(x.turnover, 0)} tỷ`}
      </span>;
    })}
    {(data?.unavailable_indices || []).map((x: any) => <span key={x.name} className="text-amber-200" title={x.reason}>{x.name} chưa lấy được</span>)}
    <span className="ml-auto opacity-80">Cập nhật {data?.updated_at ? new Date(data.updated_at).toLocaleTimeString("vi-VN") : "—"}</span>
  </div>;
}
