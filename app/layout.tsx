import type { Metadata } from "next";
import localFont from "next/font/local";
import Script from "next/script";
import Link from "next/link";
import Search from "@/components/Search";
import LiveRibbon from "@/components/LiveRibbon";
import ThemeToggle from "@/components/ThemeToggle";
import "./globals.css";

const beVietnam = localFont({
  src: [
    { path: "../assets/fonts/BeVietnamPro-Regular.ttf", weight: "400", style: "normal" },
    { path: "../assets/fonts/BeVietnamPro-Medium.ttf", weight: "500", style: "normal" },
    { path: "../assets/fonts/BeVietnamPro-SemiBold.ttf", weight: "600", style: "normal" },
    { path: "../assets/fonts/BeVietnamPro-Bold.ttf", weight: "700", style: "normal" },
    { path: "../assets/fonts/BeVietnamPro-Italic.ttf", weight: "400", style: "italic" },
  ],
  variable: "--font-bvp",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Invest System – Phân tích cơ hội đầu tư cổ phiếu",
  description: "Vĩ mô → Ngành (ICB toàn thị trường) → Doanh nghiệp → Định giá → Khuyến nghị → PDF. Dữ liệu thật, có nguồn & thời điểm.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={beVietnam.variable} suppressHydrationWarning>
      <Script id="theme-init" strategy="beforeInteractive">
        {'try { document.documentElement.dataset.theme = localStorage.getItem("invest-system-theme") === "dark" ? "dark" : "light"; } catch { document.documentElement.dataset.theme = "light"; }'}
      </Script>
      <body style={{ fontFamily: "var(--font-bvp), system-ui, sans-serif" }}>
        <header className="no-print sticky top-0 z-40 bg-[#0b3b6f] text-white shadow-sm">
          <div className="mx-auto max-w-7xl px-4 py-2.5 flex flex-wrap items-center gap-x-6 gap-y-1">
            <Link href="/" className="font-bold tracking-tight text-lg">INVEST<span className="text-sky-300">SYSTEM</span></Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/" className="hover:text-sky-200">Tổng quan</Link>
              <Link href="/nganh" className="hover:text-sky-200">Ngành</Link>
              <Link href="/co-hoi" className="hover:text-sky-200">Cơ hội</Link>
              <Link href="/thi-truong" className="hover:text-sky-200">Toàn thị trường</Link>
              <Link href="/nguon" className="hover:text-sky-200">Dữ liệu & nguồn</Link>
            </nav>
            <ThemeToggle />
            <div className="ml-auto hidden w-64 md:block"><Search globalHotkeys /></div>
          </div>
          <LiveRibbon />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-5">{children}</main>
        <footer className="no-print mx-auto max-w-7xl px-4 py-6 text-xs text-slate-500">
          Dữ liệu: Vietcap public API (giá, bảng giá, số CP), vnstock (ICB), BCTC năm từ vn-annual-report-miner (MIT),
          GSO/NSO – NHNN – HNX (vĩ mô), CafeF/VnExpress (tin). Công cụ phân tích, không phải lời khuyên đầu tư.
        </footer>
      </body>
    </html>
  );
}
