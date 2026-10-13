"""Fetch annual statements and quarterly TTM data for listed symbols via VCI.

Examples:
  python scripts/fetch_bctc_vnstock.py --exchange UPCOM --top 20 --resume
  python scripts/fetch_bctc_vnstock.py --exchange UPCOM --resume --upload
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.data.arminer_bctc import (  # noqa: E402
    FIELD_CODES,
    VNSTOCK_PACKED,
    _vnstock_supplement,
    coverage,
)
from invest_system.data.fundamentals import FIELD_LABELS_VI, standardize_vnstock  # noqa: E402
from invest_system.data.vietcap import VietcapProvider  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR, classify_company_type  # noqa: E402

REFERENCE = ROOT / "data" / "reference"
CACHE = REFERENCE / "bctc_vnstock" / "by_symbol"
STATE = REFERENCE / "bctc_vnstock" / "state.json"
FAILURES = REFERENCE / "bctc_vnstock" / "failures.csv"
ANNUAL_PATH = VNSTOCK_PACKED
SOURCE = "vnstock VCI"
FIELD_STATEMENT = {
    **{k: "income_statement" for k in (
        "revenue", "cogs", "gross_profit", "selling_expense", "admin_expense", "operating_profit",
        "financial_income", "interest_expense", "pbt", "tax", "net_income", "net_income_parent",
        "net_interest_income", "fee_income", "total_operating_income", "operating_expense", "provision",
    )},
    **{k: "balance_sheet" for k in (
        "cash", "short_investments", "receivables", "inventory", "current_assets", "fixed_assets",
        "total_assets", "current_liabilities", "short_debt", "long_debt", "total_liabilities", "equity",
        "minority_interest", "loans", "deposits",
    )},
    **{k: "cash_flow" for k in ("depreciation", "cfo", "capex", "cfi", "cff", "dividends_paid")},
}


def _tickers_for_exchange(frame: pd.DataFrame, exchange: str) -> set[str]:
    """Return cached supplement symbols, including the empty/missing-schema case."""
    if frame.empty or not {"ticker", "exchange"}.issubset(frame.columns):
        return set()
    rows = frame.loc[frame["exchange"].astype(str).str.upper() == exchange.upper(), "ticker"]
    return set(rows.astype(str).str.upper())


def _validate(symbol: str, company_type: str, standard) -> None:
    frame = standard.frame
    if frame.empty or len(frame.index) < 5:
        raise ValueError("need at least 5 annual periods after standardization")
    assets = pd.to_numeric(frame.get("total_assets"), errors="coerce")
    liabilities = pd.to_numeric(frame.get("total_liabilities"), errors="coerce")
    equity = pd.to_numeric(frame.get("equity"), errors="coerce")
    valid = assets.notna() & liabilities.notna() & equity.notna() & (assets > 0)
    if not valid.any():
        raise ValueError("missing total assets, liabilities, or equity")
    error = ((liabilities[valid] + equity[valid] - assets[valid]).abs() / assets[valid]).max()
    if float(error) > 0.01:
        raise ValueError(f"balance sheet equation exceeds 1% (max {error:.2%})")
    if float(assets[valid].median()) < 1e9:
        raise ValueError("total assets unit check failed; expected VND")
    required = "total_operating_income" if company_type == "BANK" else "revenue"
    if required not in frame or pd.to_numeric(frame[required], errors="coerce").dropna().empty:
        raise ValueError(f"missing company-type revenue field: {required}")


def _long_rows(symbol: str, exchange: str, standard, fetched_at: str) -> pd.DataFrame:
    rows = []
    for field, statement in FIELD_STATEMENT.items():
        if field not in standard.frame.columns or field not in FIELD_CODES:
            continue
        code = FIELD_CODES[field][0]
        code = re.sub(r"\[0-9a-f\]\{8\}", "00000000", code).removeprefix("^").removesuffix("$")
        for year, value in standard.frame[field].items():
            if pd.isna(value):
                continue
            rows.append({
                "ticker": symbol, "year": int(year), "exchange": exchange,
                "statement": statement, "item_code": code,
                "item_name": FIELD_LABELS_VI.get(field, field), "value": float(value),
                "line_no": len(rows), "source": SOURCE, "fetched_at": fetched_at,
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no rows mapped to the shared BCTC schema")
    return frame


def _fetch_one(symbol: str, exchange: str, company_type: str, provider: VietcapProvider,
               delay: float, years: int) -> pd.DataFrame:
    bundle = {}
    for key, method, period in (
        ("income", provider.income_statement, "year"),
        ("balance", provider.balance_sheet, "year"),
        ("cashflow", provider.cash_flow, "year"),
        ("ratios", provider.ratios, "year"),
    ):
        bundle[key] = method(symbol, period=period)
        time.sleep(delay)
    standard = standardize_vnstock(symbol, bundle)
    standard.frame = standard.frame.sort_index().tail(years)
    _validate(symbol, company_type, standard)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    annual = _long_rows(symbol, exchange, standard, now)

    return annual


def _upload(path: Path, pathname: str) -> None:
    token = __import__("os").environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is not configured; cannot upload refreshed BCTC data")
    proc = subprocess.run(
        ["vercel", "blob", "put", str(path), "--pathname", pathname, "--access", "public",
         "--allow-overwrite", "true", "--rw-token", token],
        check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode:
        raise RuntimeError((proc.stdout + proc.stderr)[-1000:])
    print(f"Uploaded {pathname}")


def _download_existing() -> None:
    """Restore the last published supplement so scheduled runs can resume across runners."""
    import os

    import requests

    base = os.environ.get("BLOB_BASE_URL", "").rstrip("/")
    if not base or ANNUAL_PATH.exists():
        return
    response = requests.get(f"{base}/universe/bctc_vnstock.parquet", timeout=30)
    response.raise_for_status()
    ANNUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.read_parquet(io.BytesIO(response.content)).to_parquet(ANNUAL_PATH, index=False, compression="zstd")
    print(f"Restored existing packed supplement ({len(pd.read_parquet(ANNUAL_PATH)):,} rows)")
    _vnstock_supplement.cache_clear()


def run(exchange: str, top: int | None, resume: bool, delay: float, years: int, upload: bool) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _download_existing()
    universe = pd.read_parquet(SNAPSHOT_DIR / "market_universe.parquet")
    exchange_set = {"HOSE", "HNX", "UPCOM"} if exchange == "ALL" else {exchange}
    candidates = universe[universe["exchange"].isin(exchange_set)].copy()
    available = coverage().copy()
    available["exchange"] = available["exchange"].replace({"HSX": "HOSE"})
    if exchange == "UPCOM":
        # Only a supplement tagged UPCOM counts; legacy HSX/HNX records with the
        # same ticker must not silently suppress a current UPCOM fetch.
        current_upcom = _tickers_for_exchange(_vnstock_supplement(), "UPCOM")
        candidates = candidates[~candidates["symbol"].isin(current_upcom)]
    else:
        if exchange == "ALL":
            present = set(zip(available["ticker"].astype(str), available["exchange"].astype(str), strict=True))
            candidates = candidates[[ (str(row.symbol), str(row.exchange)) not in present
                                      for row in candidates.itertuples() ]]
        else:
            present = set(available.loc[available["exchange"] == exchange, "ticker"].astype(str))
            candidates = candidates[~candidates["symbol"].isin(present)]
    candidates = candidates.sort_values("avg_value_20d", ascending=False, na_position="last")
    if top:
        candidates = candidates.head(top)
    state = json.loads(STATE.read_text(encoding="utf-8")) if resume and STATE.exists() else {"success": [], "failed": []}
    done = set(state.get("success", []))
    provider = VietcapProvider()
    failed = []
    total = len(candidates)
    for index, row in enumerate(candidates.itertuples(index=False), start=1):
        symbol = str(row.symbol).upper()
        if symbol in done and (CACHE / f"{symbol}.parquet").exists():
            continue
        ctype = classify_company_type(row.com_type_code, row.icb1, row.icb2, row.icb3, row.icb4)
        try:
            annual = _fetch_one(symbol, exchange, ctype, provider, delay, years)
            annual.to_parquet(CACHE / f"{symbol}.parquet", index=False)
            state["success"] = sorted(set(state.get("success", [])) | {symbol})
            state["failed"] = [item for item in state.get("failed", []) if item.get("symbol") != symbol]
            done.add(symbol)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            failed.append({"symbol": symbol, "exchange": exchange, "error": str(exc)[:500],
                           "attempted_at": datetime.now().astimezone().isoformat(timespec="seconds")})
            state["failed"] = [item for item in state.get("failed", []) if item.get("symbol") != symbol] + [failed[-1]]
            time.sleep(min(60, max(delay, 1) * 2))
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if index % 10 == 0 or index == total:
            print(f"{index}/{total} processed; successful={len(done)} failed={len(state['failed'])}", flush=True)

    files = [pd.read_parquet(path) for path in CACHE.glob("*.parquet") if path.name != "ttm.parquet"]
    if files:
        old = pd.read_parquet(ANNUAL_PATH) if ANNUAL_PATH.exists() else pd.DataFrame()
        merged = pd.concat([old, *files], ignore_index=True)
        merged = merged.drop_duplicates(["ticker", "year", "statement", "item_code"], keep="last")
        ANNUAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        merged.to_parquet(ANNUAL_PATH, index=False, compression="zstd")
    if failed:
        pd.DataFrame(failed).to_csv(FAILURES, index=False, encoding="utf-8-sig")
    if upload:
        _upload(ANNUAL_PATH, "universe/bctc_vnstock.parquet")
    print(f"Annual rows={len(pd.read_parquet(ANNUAL_PATH)) if ANNUAL_PATH.exists() else 0}; new failures={len(failed)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exchange", choices=("HOSE", "HNX", "UPCOM", "ALL"), default="UPCOM")
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--delay", type=float, default=3.2, help="wait seconds between each VCI request")
    parser.add_argument("--years", type=int, choices=range(5, 11), default=10)
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    run(args.exchange, args.top, args.resume, args.delay, args.years, args.upload)


if __name__ == "__main__":
    main()
