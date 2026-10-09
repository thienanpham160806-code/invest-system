"use client";
import { useEffect, useState } from "react";

export type Prov = { source: string; as_of?: string | null; fetched_at?: string; note?: string; origin?: string; built_at?: string; as_of_fin?: string };

export async function getJSON<T = any>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json();
}

export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true); setError(null);
    getJSON<T>(path).then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(String(e.message || e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path]);
  return { data, error, loading };
}

export function toCSV(rows: Record<string, any>[], cols: { key: string; label: string }[]): string {
  const esc = (v: any) => { const s = v === null || v === undefined ? "" : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return "﻿" + [cols.map((c) => esc(c.label)).join(","), ...rows.map((r) => cols.map((c) => esc(r[c.key])).join(","))].join("\n");
}
export function downloadCSV(name: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click();
}
