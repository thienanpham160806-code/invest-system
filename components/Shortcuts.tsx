"use client";
// Phím tắt toàn cục: "g" + chữ để chuyển trang, "?" mở bảng phím tắt. Không bắt phím khi đang gõ
// (input/textarea/select/contenteditable) hoặc khi giữ Ctrl/Alt/Meta. Trang cổ phiếu tự xử lý 1–9 (đổi tab).
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { COMMANDS } from "@/lib/terminal/commands";

export const GO_KEYS: Record<string, { href: string; label: string }> = {
  h: { href: "/", label: "Trang chủ" },
  m: { href: "/#ban-do", label: "Bản đồ thị trường" },
  t: { href: "/thi-truong", label: "Toàn thị trường" },
  n: { href: "/nganh", label: "Ngành" },
  v: { href: "/vi-mo", label: "Vĩ mô" },
  c: { href: "/co-hoi", label: "Cơ hội" },
  b: { href: "/backtest", label: "Backtest" },
  s: { href: "/so-sanh", label: "So sánh" },
};
const CHORD_MS = 1200;

export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.isContentEditable);
}

export default function Shortcuts() {
  const router = useRouter();
  const [help, setHelp] = useState(false);
  const pendingG = useRef(0);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || isTyping(e.target)) return;
      if (document.querySelector('[role="dialog"][aria-modal="true"]') && e.key !== "Escape") return;
      if (e.key === "Escape") { setHelp(false); return; }
      if (e.key === "?") { e.preventDefault(); setHelp((h) => !h); return; }
      const now = Date.now();
      if (e.key === "g" && !e.shiftKey) { pendingG.current = now; return; }
      if (pendingG.current && now - pendingG.current < CHORD_MS && GO_KEYS[e.key]) {
        e.preventDefault();
        pendingG.current = 0;
        router.push(GO_KEYS[e.key].href);
        return;
      }
      pendingG.current = 0;
    };
    const open = () => setHelp(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener("open-shortcuts", open);
    return () => { document.removeEventListener("keydown", onKey); window.removeEventListener("open-shortcuts", open); };
  }, [router]);
  if (!help) return null;
  return (
    <div className="fixed inset-0 z-50 bg-slate-950/50 p-4 sm:p-10" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && setHelp(false)}>
      <section className="mx-auto max-h-full max-w-3xl overflow-auto rounded-xl bg-white p-5 text-slate-900 shadow-2xl" role="dialog" aria-modal="true" aria-label="Bảng phím tắt và lệnh" data-testid="shortcuts-help">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Phím tắt & lệnh</h2>
          <button type="button" className="btn-ghost" onClick={() => setHelp(false)}>Đóng (Esc)</button>
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-700">Phím tắt</h3>
            <table className="tbl text-sm"><tbody>
              <tr><td><kbd>/</kbd> hoặc <kbd>Ctrl</kbd>+<kbd>K</kbd></td><td>Mở thanh lệnh / tìm mã</td></tr>
              {Object.entries(GO_KEYS).map(([k, v]) => <tr key={k}><td><kbd>g</kbd> <kbd>{k}</kbd></td><td>{v.label}</td></tr>)}
              <tr><td><kbd>1</kbd>–<kbd>9</kbd></td><td>Đổi tab trên trang cổ phiếu</td></tr>
              <tr><td><kbd>?</kbd></td><td>Bật/tắt bảng này</td></tr>
              <tr><td><kbd>Tab</kbd> / <kbd>↑</kbd></td><td>Trong thanh lệnh: hoàn thành lệnh / lệnh gần đây</td></tr>
            </tbody></table>
            <p className="mt-2 text-xs text-slate-500">Phím tắt không hoạt động khi con trỏ đang ở ô nhập liệu.</p>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-700">Lệnh (gõ trong thanh lệnh)</h3>
            <table className="tbl text-sm"><tbody>
              {COMMANDS.map((c) => <tr key={c.syntax}><td className="font-mono whitespace-nowrap">{c.syntax}</td><td>{c.description}</td><td className="font-mono text-xs text-slate-500">{c.example}</td></tr>)}
            </tbody></table>
            <p className="mt-2 text-xs text-slate-500">CMP, SRC, TOP cũng là mã cổ phiếu: gõ riêng là lệnh chung, thêm chức năng (vd <code>SRC DES</code>) để mở mã.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
