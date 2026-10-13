# Invest System

A Vietnamese equity research system that combines macroeconomic context, industry analysis, company fundamentals, valuation, and risk-aware recommendations. It provides a web dashboard, company reports, market-wide opportunity screens, and an optional AI narrative layer.

> **Integration status (13 October 2026):** Phase 2 implementation is complete on `feature/phase2` at `7b6d9ae`; it has not yet been merged into `upgrade/post-submission-20261009` or deployed. The production URL below may not include the Phase 2 routes or refreshed data. The new BCTC and TTM snapshots are local; the Blob refresh, opportunity rebuild, and production deployment are still pending.

## Product overview

The analysis flow is top-down:

**Macro → Industry → Company → Valuation → Recommendation → Report**

Quantitative scores and recommendations come from deterministic, reviewable rules. OpenAI or Gemini can optionally turn already-computed evidence into concise Vietnamese analysis. The model does not set scores or recommendations, fetch external facts, or add unsupported numbers.

## Web application

Production URL: <https://invest-system-silk.vercel.app>

- API documentation: `/api/py/docs`
- Source health: `/nguon`

| Route | Purpose |
|---|---|
| `/` | VN-Index, market breadth, macro snapshot, industry overview, opportunity preview, and market treemap. |
| `/co-hoi` | Ranked investment opportunities with exchange, liquidity, industry, rating, confidence, and CSV filters. |
| `/thi-truong` | Searchable market universe with market, performance, valuation, and coverage metrics. |
| `/nganh` and `/nganh/[slug]` | ICB industry hierarchy, peer distributions, market-weighted performance, and company tables. |
| `/stock/[ticker]` | Company overview, macro and sector context, financial statements, ratios, valuation scenarios, technical analysis, news, reports, and data provenance. |
| `/so-sanh` | Compare up to eight companies using the shared company-analysis data. TTM P/E is shown only when raw VCI quarter provenance and four consecutive quarter labels validate. |
| `/vi-mo` | Vietnamese and international macro context, including the relationship to the selected company or industry. |
| `/backtest` | Walk-forward opportunity strategy results, benchmarks, risk metrics, information coefficient, and limitations. |
| `/report/[ticker]` | Configurable research report with browser print and server-rendered PDF options. |
| `/nguon` | Live source checks, freshness, news feeds, market indices, and financial-statement coverage. |

## Architecture

```mermaid
flowchart LR
  U[Investor / browser] --> N[Next.js 16 App Router\nDashboard · search · tables · charts]
  N -->|/api/py/* rewrite| F[FastAPI on Python\napi/index.py]
  N -->|/api/pdf| P[Node PDF function\nPuppeteer + Chromium]
  P -->|opens /report/[ticker]| N

  F --> S[web/service.py\nAPI orchestration]
  S --> A[Deterministic analysis\nMacro · industry · ratios · valuation\ntechnical · sentiment · composite]
  S --> V[Validation and provenance\nsource · as-of · fetched-at · N/A reasons]
  S -. opt-in narrative only .-> L[OpenAI Responses API\nor Gemini]

  F --> D[Snapshot reader\nBlob with packaged fallback]
  B[Offline / local data pipeline\nprices · BCTC · TTM · market universe\nopportunities · backtest] --> W[Parquet / JSON snapshots]
  W --> D
  W -->|authorized refresh| VB[Vercel Blob\nuniverse/latest.parquet]

  S -->|live requests| X[External sources\nVietcap/VCI · CafeF/RSS\nWorld Bank · FRED]
  X --> S
  A --> R[Research report builder\nHTML/PDF]
  R --> P
```

The web request path reads prepared market snapshots instead of querying every listed company on demand. The data pipeline runs separately and produces versionable Parquet/JSON artifacts. Vercel Blob can serve refreshed market data; packaged `webdata/snapshot/` files provide the repository fallback. Source timestamps and missing-data explanations should remain visible when snapshots are refreshed.

The standalone Python application also includes a CLI and Streamlit interface. It shares analysis modules with the web API and can create research reports from Jinja templates and charts.

Architecture source and SVG: [`docs/architecture/architecture.mmd`](docs/architecture/architecture.mmd) and [`docs/architecture/architecture.svg`](docs/architecture/architecture.svg).

## Data and provenance

Sources include Vietcap/VCI market and financial data, annual-report data from the arminer dataset, CafeF and VnExpress RSS news, World Bank Open Data, and FRED. Availability depends on the source, ticker, deployment region, and configured credentials.

The API returns provenance where available: source, observation or report date (`as_of`), and retrieval time (`fetched_at`). Missing metrics should remain `N/A` with a reason; they must not be replaced by fabricated or stale values without a visible label.

### Current local data status

- Quarterly statements were fetched for **1,222 of 1,522 symbols**, covering 37,015 quarters from 2018–2026. The 300 unavailable cases are UPCOM: 253 have no quarterly records from the source and 47 lack cash-flow statements. This snapshot is local to the Phase 2 worktree and has not yet been uploaded to production.
- The Phase 2 TTM build uses raw VCI quarterly data and validates four consecutive quarter labels. Negative or otherwise invalid TTM rows are excluded from the comparison display rather than silently presented as valid P/E.
- The current annual and quarterly sources retain their latest statement values, not every historical restatement vintage. The backtest filters by publication availability but cannot reconstruct values investors saw before later corrections. This limitation affects historical results; see the backtest warning below.

## Backtest status and limits

The Phase 2 report covers an out-of-sample period from 29 September 2020 through 28 September 2026, with 98 month-end signal dates and 392 symbols that qualified at least once. It found **no evidence of a statistically meaningful investment edge**: the strategy achieved one of four pre-registered criteria; OOS Sharpe was 0.57 versus 0.68 for the VN-Index price benchmark and 0.70 for the top-20 market-cap benchmark.

> **Exploratory result only — not a strictly point-in-time validated backtest.** Historical statement values may include later restatements because the source has no full vintage archive. Other documented limitations include survivorship from using currently listed symbols and present-day company classifications. Do not present these results as a validated investment track record.

Details and methodology: [`docs/backtest-opportunity.md`](https://github.com/thienanpham160806-code/invest-system/blob/feature/phase2/docs/backtest-opportunity.md) and [`docs/phase2/backtest-design.md`](https://github.com/thienanpham160806-code/invest-system/blob/feature/phase2/docs/phase2/backtest-design.md) on the Phase 2 branch.

## Optional AI analysis

AI prose is disabled by default. A configured API key alone does not trigger requests. To opt in, select exactly one provider and set `LLM_ENABLED=1`. The backend sends only computed analysis inputs, enforces a short output limit, checks that the model has not introduced unsupported numbers, and falls back to deterministic commentary on provider errors.

```dotenv
LLM_ENABLED=0
LLM_PROVIDER=openai       # openai or gemini
OPENAI_API_KEY=
GEMINI_API_KEY=
OPENAI_MODEL=gpt-6-luna
GEMINI_MODEL=gemini-3.5-flash-lite
```

Keep provider keys server-side. Never use a `NEXT_PUBLIC_` prefix, put keys in source control, or enable the model until you are ready for billable API requests.

## Local development

Requirements: Python 3.10 or newer, Node.js compatible with Next.js 16, and npm. Install the full local Python toolset and JavaScript dependencies:

```bash
python -m pip install -r requirements-local.txt
npm ci
```

Run the Python API and Next.js in separate terminals. The API uses port 8000 and the web app uses port 3000 by default.

```bash
# Terminal 1
python -m uvicorn api.index:app --reload --port 8000

# Terminal 2
npm run dev -- --port 3000
```

Open <http://localhost:3000>. Local API docs are at <http://localhost:8000/api/py/docs>. In development, Next.js rewrites `/api/py/*` to `http://127.0.0.1:8000`; the current repo does not expose an override variable for that URL.

## Data pipeline

The scripts are intended for controlled local or scheduled jobs, not for execution inside a user page request. The quarterly BCTC, TTM, and backtest scripts below are Phase 2 additions and remain on `feature/phase2` until merge. Typical jobs include:

```bash
python scripts/backfill_data.py
python scripts/backfill_vnindex.py
python scripts/fetch_bctc_quarterly.py --resume
python scripts/build_ttm_quarterly.py
python scripts/build_market_universe.py
python scripts/build_opportunities.py
python scripts/run_backtest_opportunity.py --score
python scripts/run_backtest_opportunity.py --run
```

Check each script's `--help` before running a data refresh. BCTC collection calls VCI through vnstock, can be rate-limited, and writes local data. Coordinate it with `.agent-coord/locks/vnstock.lock`; resume from its checkpoint instead of starting a duplicate run. Uploading snapshots changes shared production data and requires `.agent-coord/locks/blob-latest.lock`. Production deployment requires `.agent-coord/locks/prod-deploy.lock` and a clean preview review.

Important scripts:

| Script | Role |
|---|---|
| `backfill_data.py`, `backfill_vnindex.py` | Historical adjusted prices and VN-Index data for analysis and backtests. |
| `fetch_bctc_quarterly.py`, `fetch_bctc_vnstock.py` | Quarterly and annual financial-statement collection with resume support. |
| `build_ttm_quarterly.py`, `build_ttm.py` | Build quarterly-provenance TTM data or supplementary annual data. |
| `build_market_universe.py`, `build_opportunities.py` | Produce the market and opportunity snapshots. |
| `run_backtest_opportunity.py` | Score historical signals and run walk-forward evaluation. |
| `check_sources.py`, `check_news.py`, `check_bctc_coverage.py` | Inspect source health, news, and financial-statement coverage. |
| `valuation_audit.py`, `audit_report_numbers.py` | Audit valuation inputs and report figures. |

## Environment variables

Use `.env` locally and Vercel Project Environment Variables in deployments. `.env.example` documents sample defaults; add private credentials only to `.env` or the deployment's secret settings.

| Variable | Purpose |
|---|---|
| `DATA_DIR`, `CACHE_DB`, `MODEL_DIR` | Local application data, cache database, and model/artifact directories. |
| `WEBDATA_DIR`, `REFERENCE_DIR` | Packaged web snapshots and reference financial data. |
| `BLOB_READ_WRITE_TOKEN`, `BLOB_BASE_URL` | Snapshot upload token and optional configured Blob base URL. Keep the token private. |
| `DNSE_API_KEY`, `DNSE_API_SECRET`, `DNSE_BASE_URL`, `DNSE_API_VERSION` | Optional DNSE connection for trading/data integrations. The research dashboard does not place trades. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_IDS` | Optional Telegram bot token and comma-separated administrator IDs. |
| `VNSTOCK_ACCEPT_TOS` | vnstock terms acceptance setting used by local collection jobs. |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LLM_ENABLED`, `LLM_PROVIDER`, `OPENAI_MODEL`, `GEMINI_MODEL` | Optional server-side narrative provider configuration. |
| `AUTO_SUBSCRIBE_CHAT_IDS` | Optional comma-separated Telegram chat IDs to subscribe to news on startup. |
| `UNIVERSE_MAX_SYMBOLS`, `MARKET_COUNT_BACK`, `SNAPSHOT_MAX_WORKERS` | Optional limits for local snapshot building. |
| `LOG_LEVEL`, `CHROME_PATH` | Logging level and optional local Chromium executable path for PDF rendering. |

## Verification

```bash
python -m pytest -q
npx tsc --noEmit --incremental false
npm run build
```

The project also contains focused tests for point-in-time availability, quarterly TTM labels, portfolio execution constraints, financial validation, PDF output, and frontend command parsing.

## Deployment

The web application targets Vercel: Next.js serves the UI and PDF route, and the Python function exposes `/api/py/*` in the `sin1` region. Production secrets belong in Vercel Environment Variables. Data refreshes use the Blob pipeline and require a refresh lock; code releases require a reviewed preview and the production-deploy lock.

As of this README revision, Phase 2 code and its generated snapshots are not yet merged or published. Do not assume that production contains `/so-sanh`, `/vi-mo`, `/backtest`, or the latest TTM/opportunity data until the merge, Blob refresh, and deployment are complete.

## Repository layout

```text
app/                         Next.js pages and API routes
components/, lib/            Shared UI and frontend API helpers
api/index.py                 FastAPI entry point for Vercel
src/invest_system/analysis/  Deterministic macro, sector, valuation, and scoring logic
src/invest_system/backtest/  Point-in-time scoring and walk-forward engine
src/invest_system/data/      Market, financial, macro, and news data adapters
src/invest_system/narrative/ Optional OpenAI/Gemini narrative layer
src/invest_system/report/    Standalone report assembly
scripts/                     Data collection, snapshot, audit, and backtest jobs
config/                      Analysis settings and macro/industry configuration
webdata/snapshot/            Packaged fallback datasets
docs/                        Audits, data notes, backtest design, and architecture
tests/                       Python and frontend tests
```

## References

- [Vietnam listed companies annual-report dataset (Zenodo)](https://zenodo.org/records/20949551)
- [vnfinancialdata](https://github.com/thanhnp-uel/vnfinancialdata)
- [vn-annual-report-miner](https://github.com/Tumiqa/vn-annual-report-miner)
- World Bank Open Data, FRED, Vietcap/VCI, CafeF, VnExpress RSS, and Vietnamese government macroeconomic sources.
- Be Vietnam Pro font, licensed under the SIL Open Font License; see [`assets/fonts/OFL.txt`](assets/fonts/OFL.txt).
