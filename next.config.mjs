/** @type {import('next').NextConfig} */
// Theo template "Next.js FastAPI Starter" (vercel): /api/py/* -> FastAPI (api/index.py)
const nextConfig = {
  // Chromium cho route /api/pdf: khong bundle, dung nguyen goi (theo huong dan @sparticuz/chromium)
  serverExternalPackages: ["@sparticuz/chromium", "puppeteer-core"],
  outputFileTracingIncludes: { "/api/pdf": ["./node_modules/@sparticuz/chromium/bin/**"] },
  rewrites: async () => [
    {
      source: "/api/py/:path*",
      destination:
        process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000/api/py/:path*" : "/api/",
    },
    {
      source: "/docs",
      destination: process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000/api/py/docs" : "/api/py/docs",
    },
  ],
};
export default nextConfig;
