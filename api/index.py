"""FastAPI backend cho web (Vercel Python function). Theo template Next.js FastAPI Starter:
moi route nam duoi /api/py/*, Next.js rewrite /api/py/:path* -> function nay.

Chay local:  uvicorn api.index:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# Vercel: chi /tmp ghi duoc
if os.getenv("VERCEL"):
    os.environ.setdefault("DATA_DIR", "/tmp")
    os.environ.setdefault("CACHE_DB", "/tmp/cache.sqlite3")
    os.environ.setdefault("MODEL_DIR", "/tmp/artifacts")

from fastapi import FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from invest_system.web import service  # noqa: E402

app = FastAPI(title="invest-system API", docs_url="/api/py/docs", openapi_url="/api/py/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200 and not request.url.path.endswith(("/health", "/sources")):
        response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
    return response


def _call(fn, *args, **kwargs):
    try:
        return JSONResponse(fn(*args, **kwargs))
    except service.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/py/health")
def health():
    uni, meta = service.load_universe()
    return {"status": "ok", "time": service.now_str(), "universe_symbols": len(uni),
            "as_of_price": meta.get("as_of_price"), "built_at": meta.get("built_at"),
            "origin": meta.get("origin"), "vercel_region": os.getenv("VERCEL_REGION")}


@app.get("/api/py/sources")
def sources():
    return _call(service.sources_live)


@app.get("/api/py/search")
def search(q: str = "", limit: int = 12):
    return _call(service.search, q, limit)


@app.get("/api/py/market")
def market():
    return _call(service.market)


@app.get("/api/py/macro")
def macro(company_type: str = "NON_FINANCIAL", world_bank: bool = True):
    return _call(service.macro, company_type, world_bank)


@app.get("/api/py/sectors")
def sectors(level: int = Query(1, ge=1, le=4), exchange: str | None = None):
    return _call(service.sectors, level, exchange)


@app.get("/api/py/sectors/{slug}")
def sector_detail(slug: str):
    return _call(service.sector_detail, slug)


@app.get("/api/py/universe")
def universe(exchange: str | None = None, icb: str | None = None, sort: str = "market_cap",
             order: str = "desc", min_value: float | None = None, page: int = 1,
             page_size: int = 50, q: str | None = None):
    return _call(service.universe_table, exchange, icb, sort, order, min_value, page, page_size, q)


@app.get("/api/py/stock/{ticker}/profile")
def stock_profile(ticker: str):
    return _call(service.profile, ticker)


@app.get("/api/py/stock/{ticker}/price")
def stock_price(ticker: str, days: int = Query(365, ge=5, le=1500)):
    return _call(service.price, ticker, days)


@app.get("/api/py/stock/{ticker}/financials")
def stock_financials(ticker: str, statement: str = "is", years: int = Query(5, ge=1, le=17)):
    return _call(service.financials, ticker, statement, years)


@app.get("/api/py/stock/{ticker}/ratios")
def stock_ratios(ticker: str, years: int = Query(5, ge=1, le=15)):
    return _call(service.ratios, ticker, years)


@app.get("/api/py/stock/{ticker}/valuation")
def stock_valuation(ticker: str):
    def fn(t):
        a = service.analysis(t, with_news=False)
        return {k: a[k] for k in ("symbol", "price", "valuation", "recommendation", "sector", "provenance")}
    return _call(fn, ticker)


@app.get("/api/py/stock/{ticker}/technical")
def stock_technical(ticker: str):
    def fn(t):
        a = service.analysis(t, with_news=False)
        return {"symbol": a["symbol"], "technical": a["technical"], "provenance": a["provenance"]}
    return _call(fn, ticker)


@app.get("/api/py/stock/{ticker}/news")
def stock_news(ticker: str):
    return _call(service.news, ticker)


@app.get("/api/py/stock/{ticker}/documents")
def stock_documents(ticker: str):
    return _call(service.documents, ticker)


@app.get("/api/py/stock/{ticker}/analysis")
def stock_analysis(ticker: str, years: int = Query(5, ge=2, le=10), news: bool = True):
    return _call(service.analysis, ticker, years, news)
