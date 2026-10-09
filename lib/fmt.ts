// Dinh dang so kieu Viet Nam: 1.234,5
const nf = (d: number) => new Intl.NumberFormat("vi-VN", { minimumFractionDigits: d, maximumFractionDigits: d });

export const isNum = (v: any): v is number => typeof v === "number" && Number.isFinite(v);
export function num(v: any, d = 0): string { return isNum(v) ? nf(d).format(v) : "–"; }
export function pct(v: any, d = 1, sign = false): string {
  if (!isNum(v)) return "–";
  const s = nf(d).format(v * 100) + "%";
  return sign && v > 0 ? "+" + s : s;
}
export function times(v: any, d = 1): string { return isNum(v) ? nf(d).format(v) + "x" : "–"; }
export function price(v: any): string { return isNum(v) ? nf(0).format(v) : "–"; }
/** VND -> ty dong */
export function bn(v: any, d = 0): string { return isNum(v) ? nf(d).format(v / 1e9) : "–"; }
export function bnLabel(v: any): string {
  if (!isNum(v)) return "–";
  if (Math.abs(v) >= 1e15) return nf(1).format(v / 1e15) + " triệu tỷ";
  if (Math.abs(v) >= 1e12) return nf(1).format(v / 1e12) + " nghìn tỷ";
  return nf(0).format(v / 1e9) + " tỷ";
}
export function dmy(s: any): string {
  if (!s) return "–";
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (!m) return String(s);
  return `${m[3]}/${m[2]}/${m[1]}` + (m[4] ? ` ${m[4]}:${m[5]}` : "");
}
export function cls(v: any): string { return !isNum(v) ? "" : v > 0 ? "text-up" : v < 0 ? "text-down" : "text-ref"; }
export function fmtKind(v: any, kind: string): string {
  if (kind === "pct") return pct(v);
  if (kind === "x") return times(v, 2);
  if (kind === "d") return num(v, 0) + (isNum(v) ? " ngày" : "");
  if (kind === "vnd") return bn(v) + (isNum(v) ? " tỷ" : "");
  return num(v, 2);
}
export const RATING_COLOR: Record<string, string> = {
  "MUA": "bg-emerald-600", "KHẢ QUAN": "bg-emerald-500", "NẮM GIỮ": "bg-amber-500",
  "KÉM KHẢ QUAN": "bg-orange-600", "BÁN": "bg-red-600",
};
