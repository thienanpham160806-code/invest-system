// Xuat PDF phia may chu: mo /report/[ticker] bang Chromium headless, cho window.__REPORT_READY__,
// in A4. Loi bat ky -> tra 503, giao dien tu quay ve window.print() (buoc 1).
// Cap phien ban: puppeteer-core 25.11.0 <-> @sparticuz/chromium 153.0.0 (Chrome 153).
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const ticker = (url.searchParams.get("ticker") || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!ticker) return NextResponse.json({ error: "thiếu ticker" }, { status: 400 });
  const qs = new URLSearchParams();
  for (const k of ["sections", "years", "template"]) {
    const v = url.searchParams.get(k);
    if (v) qs.set(k, v);
  }
  const target = `${url.origin}/report/${ticker}?${qs.toString()}`;
  let browser: any;
  try {
    const puppeteer = (await import("puppeteer-core")).default;
    let executablePath = process.env.CHROME_PATH;
    let args: string[] = ["--no-sandbox"];
    if (!executablePath) {
      const chromium = (await import("@sparticuz/chromium")).default;
      executablePath = await chromium.executablePath();
      args = await puppeteer.defaultArgs({ args: chromium.args, headless: "shell" });
    }
    browser = await puppeteer.launch({ args, executablePath, headless: "shell", defaultViewport: { width: 1200, height: 1600 } });
    const page = await browser.newPage();
    // chuyen tiep thong tin bao ve deployment de Chromium goi duoc /api/py trong Preview
    const bypass = req.headers.get("x-vercel-protection-bypass");
    const trustedOidc = req.headers.get("x-vercel-trusted-oidc-idp-token");
    const protectionHeaders: Record<string, string> = {};
    if (bypass) protectionHeaders["x-vercel-protection-bypass"] = bypass;
    if (trustedOidc) protectionHeaders["x-vercel-trusted-oidc-idp-token"] = trustedOidc;
    if (Object.keys(protectionHeaders).length) {
      const origin = new URL(target).origin;
      await page.setRequestInterception(true);
      page.on("request", (request) => {
        const headers = request.headers();
        if (new URL(request.url()).origin === origin) Object.assign(headers, protectionHeaders);
        void request.continue({ headers }).catch(() => {});
      });
    }
    await page.goto(target, { waitUntil: "networkidle0", timeout: 45000 });
    await page.waitForFunction("window.__REPORT_READY__ === true", { timeout: 45000 });
    const pdf = await page.pdf({ format: "A4", printBackground: true, margin: { top: "10mm", bottom: "12mm", left: "10mm", right: "10mm" },
      displayHeaderFooter: true, headerTemplate: "<span></span>",
      footerTemplate: `<div style="font-size:8px;width:100%;text-align:center;color:#64748b">${ticker} – invest-system – trang <span class="pageNumber"></span>/<span class="totalPages"></span></div>` });
    const d = new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, "");
    return new NextResponse(Buffer.from(pdf), {
      headers: { "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="${ticker}_${d}.pdf"`, "Cache-Control": "no-store" },
    });
  } catch (e: any) {
    return NextResponse.json({ error: `Không tạo được PDF trên máy chủ: ${e?.message || e}`, fallback: "window.print" }, { status: 503 });
  } finally {
    try { await browser?.close(); } catch {}
  }
}
