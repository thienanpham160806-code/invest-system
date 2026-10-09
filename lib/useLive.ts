"use client";
import { useEffect, useRef, useState } from "react";

export function useLive<T extends { is_open?: boolean }>(path: string) {
  const [data, setData] = useState<T | null>(null), [error, setError] = useState(false), [failed, setFailed] = useState(0);
  const dataRef = useRef<T | null>(null), errorRef = useRef(false), failedRef = useRef(0);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined, alive = true;
    const poll = async () => {
      if (!alive || document.visibilityState === "hidden") return;
      try {
        const r = await fetch(path, { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const next = await r.json(); if (alive) { dataRef.current = next; errorRef.current = false; failedRef.current = 0; setData(next); setError(false); setFailed(0); }
      } catch { if (alive) { errorRef.current = true; failedRef.current = Math.min(failedRef.current + 1, 5); setError(true); setFailed(failedRef.current); } }
      const isVisibleNow = () => document.visibilityState === "visible";
      if (alive && isVisibleNow()) {
        const backoff = errorRef.current ? Math.min(300000, 15000 * 2 ** failedRef.current) : dataRef.current?.is_open ? 15000 : 300000;
        timer = setTimeout(poll, backoff);
      }
    };
    const visibility = () => { if (document.visibilityState === "visible") { clearTimeout(timer); void poll(); } else clearTimeout(timer); };
    void poll(); document.addEventListener("visibilitychange", visibility);
    return () => { alive = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visibility); };
  }, [path]);
  return { data, error };
}
