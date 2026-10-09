"""Dung BANG TOAN THI TRUONG (market_universe.parquet) - chay tren may o VN.

Web (Vercel) KHONG goi 1.500 ma trong mot request -> tinh san o day, web chi doc.

Nguon:
  - Danh sach ma + san: Vietcap public getAll (data/vietcap.fetch_all_symbols).
  - Gia lich su: kho data/market/ohlcv.parquet (scripts/backfill_data.py, gap-chart Vietcap).
  - Bang gia + so CP niem yet (listedShare) + ten DN: Vietcap public getList (lo 100 ma).
  - Nganh ICB 1-4: vnstock Reference().equity.list_by_industry(); bu cho thieu bang
    fiinpro_icb_companies.csv (repo vn-annual-report-miner); khong co -> "Chưa phân loại".
  - BCTC nam: data/reference/bctc_long.parquet (arminer, HSX/HNX, FY2009-FY2025).

Output (data/snapshot/):
  market_universe.parquet  - moi ma mot dong (xem COLUMNS)
  sector_index.parquet     - chi so nganh cap-weighted rebase 100 (moi nut ICB 1-4) + VNINDEX
  ohlcv.parquet            - kho gia sap theo ma, row group nho (web doc theo ma)
  meta.json                - thoi diem du lieu, so lieu kiem tra

Cach chay:
    python scripts/backfill_data.py          # cap nhat kho gia (2-3 phut)
    python scripts/build_market_universe.py  # ~1-2 phut
    python scripts/build_market_universe.py --upload   # + day len Vercel Blob (BLOB_READ_WRITE_TOKEN)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.data import arminer_bctc, market_store  # noqa: E402
from invest_system.data.vietcap import (  # noqa: E402
    fetch_all_symbols, fetch_daily_bars, fetch_price_board, pivot_industry_levels,
)
from invest_system.logging_conf import get_logger, setup_logging  # noqa: E402
from invest_system.web.universe import (  # noqa: E402
    SNAPSHOT_DIR, UNCLASSIFIED, classify_company_type, node_key,
)

log = get_logger("build_universe")
REF = ROOT / "data" / "reference"
MIN_LIQUID_VALUE = 1e9  # GTGD TB 20 phien >= 1 ty dong -> "du thanh khoan"


def load_industry() -> tuple[pd.DataFrame, str]:
    """ICB 1-4 tu vnstock (live, luu lai ban raw), loi thi dung ban raw da luu."""
    raw_path = REF / "vnstock_industry_raw.parquet"
    try:
        from vnstock import Reference  # type: ignore

        raw = pd.DataFrame(Reference().equity.list_by_industry())
        if not raw.empty:
            raw.to_parquet(raw_path)
            note = "vnstock list_by_industry (live)"
        else:
            raise RuntimeError("rong")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.warning("vnstock industry loi (%s) -> dung ban luu %s", exc, raw_path)
        raw = pd.read_parquet(raw_path)
        note = f"vnstock list_by_industry (bản lưu {datetime.fromtimestamp(raw_path.stat().st_mtime):%d/%m/%Y})"
    return pivot_industry_levels(raw), note


def load_fiinpro() -> pd.DataFrame:
    f = pd.read_csv(REF / "arminer" / "fiinpro_icb_companies.csv")
    f = f.rename(columns={
        "Mã CK": "symbol", "Tên Doanh Nghiệp": "fiin_name", "Sàn giao dịch": "fiin_exchange",
        "Ngành ICB Cấp 1 (Industry)": "icb1", "Ngành ICB Cấp 2 (Supersector)": "icb2",
        "Ngành ICB Cấp 3 (Sector)": "icb3", "Ngành ICB Cấp 4 (Subsector)": "icb4",
        "Mã Phân Ngành (ICB Code L4)": "icb4_code", "Trang chủ (Website)": "website",
        "Tên thương hiệu / Viết tắt": "brand",
    })
    f["symbol"] = f["symbol"].astype(str).str.upper().str.strip()
    f["icb4_code"] = f["icb4_code"].astype(str)
    return f.drop_duplicates("symbol")


def price_metrics(ohlcv: pd.DataFrame) -> pd.DataFrame:
    rows = []
    year_start = pd.Timestamp(datetime.now().year, 1, 1)
    for sym, g in ohlcv.groupby("symbol", sort=False):
        g = g.sort_values("time")
        close = g["close"].astype(float).to_numpy()
        if len(close) == 0 or not np.isfinite(close[-1]):
            continue
        last = close[-1]

        def ret(n):
            return float(last / close[-1 - n] - 1) if len(close) > n and close[-1 - n] > 0 else None

        prev_year = g.loc[g["time"] < year_start, "close"]
        value = (g["close"].astype(float) * g["volume"].astype(float)).tail(20)
        rows.append({
            "symbol": sym, "price": float(last), "as_of_price": g["time"].iloc[-1],
            "change_1d": ret(1), "ret_1m": ret(21), "ret_3m": ret(63), "ret_1y": ret(250),
            "ret_ytd": float(last / prev_year.iloc[-1] - 1) if len(prev_year) and prev_year.iloc[-1] > 0 else None,
            "avg_value_20d": float(value.mean()) if len(value) else None,
            "n_sessions": len(close),
        })
    return pd.DataFrame(rows)


def fin_metrics(symbols: list[str]) -> pd.DataFrame:
    rows = []
    cov = set(arminer_bctc.coverage()["ticker"])
    for sym in symbols:
        if sym not in cov:
            continue
        std = arminer_bctc.from_arminer(sym)
        if std is None:
            continue
        f = std.frame
        ni = f["net_income_parent"] if "net_income_parent" in f else f.get("net_income")
        if ni is None or ni.dropna().empty:
            continue
        year = int(ni.dropna().index.max())
        row = f.loc[year]
        eq_total = row.get("equity")
        minority = row.get("minority_interest")
        eq_parent = eq_total - (minority if pd.notna(minority) else 0) if pd.notna(eq_total) else None
        prev_eq = None
        if year - 1 in f.index and pd.notna(f.loc[year - 1].get("equity")):
            pm = f.loc[year - 1].get("minority_interest")
            prev_eq = f.loc[year - 1, "equity"] - (pm if pd.notna(pm) else 0)
        avg_eq = (eq_parent + prev_eq) / 2 if eq_parent and prev_eq else eq_parent
        ni_y = float(ni.loc[year])
        ni_prev = float(ni.loc[year - 1]) if year - 1 in ni.index and pd.notna(ni.loc[year - 1]) else None
        debt = sum(v for v in (row.get("short_debt"), row.get("long_debt")) if pd.notna(v)) \
            if any(pd.notna(row.get(k)) for k in ("short_debt", "long_debt")) else None
        rev = row.get("revenue")
        rows.append({
            "symbol": sym, "fin_year": year, "as_of_fin": f"FY{year}",
            "fin_exchange": arminer_bctc.coverage().set_index("ticker").loc[sym, "exchange"],
            "net_income_parent": ni_y, "equity_parent": eq_parent,
            "total_assets": row.get("total_assets"), "revenue": rev,
            "charter_capital": row.get("charter_capital"),
            "eps_reported": row.get("eps_reported"),
            "roe": ni_y / avg_eq if avg_eq and avg_eq > 0 else None,
            "net_margin": ni_y / rev if pd.notna(rev) and rev and rev > 0 else None,
            "ni_growth": (ni_y / ni_prev - 1) if ni_prev and ni_prev > 0 else None,
            "ebitda": row.get("ebitda") if pd.notna(row.get("ebitda")) and row.get("ebitda") else None,
            "net_debt": (debt or 0) - sum(v for v in (row.get("cash"), row.get("short_investments")) if pd.notna(v)),
            "debt_to_equity": debt / eq_parent if debt is not None and eq_parent and eq_parent > 0 else None,
        })
    return pd.DataFrame(rows)


def sector_index(universe: pd.DataFrame, ohlcv: pd.DataFrame, days: int = 260) -> pd.DataFrame:
    """Chi so nganh cap-weighted (so CP hien tai co dinh), rebase 100 tai phien dau."""
    px = ohlcv.pivot_table(index="time", columns="symbol", values="close").sort_index().tail(days)
    px = px.ffill()
    shares = universe.set_index("symbol")["shares"].reindex(px.columns)
    out = []
    for lvl in (1, 2, 3, 4):
        col = f"icb{lvl}"
        for name, members in universe.groupby(col)["symbol"]:
            cols = [s for s in members if s in px.columns and pd.notna(shares.get(s))]
            if not cols:
                continue
            sub = px[cols]
            base = sub.iloc[0]
            valid = base.notna()
            cols = [c for c, ok in valid.items() if ok]
            if not cols:
                continue
            cap = (sub[cols] * shares[cols]).sum(axis=1)
            idx = cap / cap.iloc[0] * 100
            out.append(pd.DataFrame({"node": node_key(lvl, name), "time": idx.index, "value": idx.values}))
    try:
        vni = fetch_daily_bars("VNINDEX", count_back=days)
        vni = vni.sort_values("time").tail(days)
        out.append(pd.DataFrame({"node": "VNINDEX", "time": vni["time"].values,
                                 "value": (vni["close"] / vni["close"].iloc[0] * 100).values}))
        vni[["time", "open", "high", "low", "close", "volume"]].to_parquet(SNAPSHOT_DIR / "vnindex.parquet")
    except Exception as exc:  # noqa: BLE001
        log.warning("Khong lay duoc VNINDEX: %s", exc)
    frame = pd.concat(out, ignore_index=True)
    frame["value"] = frame["value"].astype("float32")
    return frame


def upload_blob(path: Path, pathname: str) -> str | None:
    """Day len Vercel Blob bang CLI chinh thuc `vercel blob put` (can `vercel login` va
    BLOB_READ_WRITE_TOKEN - lay bang `vercel env pull`). Tra ve URL cong khai."""
    import re
    import shutil
    import subprocess

    exe = shutil.which("vercel") or shutil.which("vercel.cmd")
    if not exe:
        log.warning("Khong thay Vercel CLI -> bo qua upload")
        return None
    cmd = [exe, "blob", "put", str(path), "--pathname", pathname, "--access", "public",
           "--allow-overwrite", "true", "--cache-control-max-age", "60"]
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if token:
        cmd += ["--rw-token", token]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    url = re.search(r"https://\S+blob\.vercel-storage\.com/\S+", out.stdout + out.stderr)
    if out.returncode != 0 or not url:
        log.warning("Upload %s loi: %s", path.name, (out.stdout + out.stderr)[-400:])
        return None
    log.info("Upload %s -> %s", path.name, url.group(0))
    return url.group(0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--upload-only", action="store_true", help="Chi day ban da dung len Blob")
    args = ap.parse_args()
    if args.upload_only:
        upload_all()
        return
    setup_logging()
    t0 = time.time()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now()

    if not arminer_bctc.PACKED.exists():
        arminer_bctc.repack()

    listing = fetch_all_symbols(["HOSE", "HNX", "UPCOM"])
    log.info("getAll: %d ma", len(listing))
    board = fetch_price_board(listing["symbol"].tolist(), delay=0.3)
    board = board.rename(columns={
        "listingInfo.symbol": "symbol", "listingInfo.organName": "board_name",
        "listingInfo.listedShare": "listed_share", "listingInfo.board": "board",
        "matchPrice.matchPrice": "board_price", "listingInfo.refPrice": "ref_price",
        "matchPrice.accumulatedValue": "board_value_mil",
    })
    keep = ["symbol", "board_name", "listed_share", "board_price", "ref_price", "board_value_mil"]
    board = board[[c for c in keep if c in board.columns]].drop_duplicates("symbol")

    industry, industry_note = load_industry()
    fiin = load_fiinpro()

    ohlcv = market_store.load_ohlcv()
    ohlcv = ohlcv[ohlcv["symbol"].isin(listing["symbol"])]
    prices = price_metrics(ohlcv)
    fins = fin_metrics(listing["symbol"].tolist())

    uni = listing.merge(board, on="symbol", how="left")
    # ---- nganh: vnstock truoc, bu bang fiinpro, con lai "Chua phan loai"
    ind = industry.set_index("symbol")
    fi = fiin.set_index("symbol")
    recs = []
    for sym in uni["symbol"]:
        if sym in ind.index and pd.notna(ind.loc[sym, "icb4"]):
            r = ind.loc[sym]
            recs.append({"symbol": sym, **{f"icb{i}": r[f"icb{i}"] for i in range(1, 5)},
                         "icb4_code": r.get("icb4_code"), "com_type_code": r.get("com_type_code"),
                         "vn_name": r.get("organ_name"), "industry_source": "vnstock"})
        elif sym in fi.index and pd.notna(fi.loc[sym, "icb4"]):
            r = fi.loc[sym]
            recs.append({"symbol": sym, **{f"icb{i}": r[f"icb{i}"] for i in range(1, 5)},
                         "icb4_code": r.get("icb4_code"), "com_type_code": None,
                         "vn_name": r.get("fiin_name"), "industry_source": "fiinpro_arminer"})
        else:
            recs.append({"symbol": sym, **{f"icb{i}": UNCLASSIFIED for i in range(1, 5)},
                         "icb4_code": None, "com_type_code": None, "vn_name": None,
                         "industry_source": "none"})
    uni = uni.merge(pd.DataFrame(recs), on="symbol", how="left")
    uni["website"] = uni["symbol"].map(fi["website"]) if "website" in fi.columns else None
    uni["brand"] = uni["symbol"].map(fi["brand"]) if "brand" in fi.columns else None
    uni["name"] = uni["board_name"].fillna(uni["vn_name"]).fillna(uni["symbol"].map(fi["fiin_name"]))
    uni["company_type"] = [classify_company_type(r.com_type_code, r.icb1, r.icb2, r.icb3, r.icb4)
                           for r in uni.itertuples()]

    uni = uni.merge(prices, on="symbol", how="left").merge(fins, on="symbol", how="left")
    # ---- so CP: listedShare live; khong co -> von gop / 10.000d (xap xi)
    uni["shares"] = pd.to_numeric(uni["listed_share"], errors="coerce").where(lambda s: s > 0)
    uni["shares_source"] = np.where(uni["shares"].notna(), "Vietcap getList listedShare", None)
    approx = uni["shares"].isna() & uni["charter_capital"].notna() & (uni["charter_capital"] > 0)
    uni.loc[approx, "shares"] = uni.loc[approx, "charter_capital"] / 10_000
    uni.loc[approx, "shares_source"] = "xấp xỉ = vốn góp/10.000đ"
    uni["market_cap"] = uni["price"] * uni["shares"]
    ni = uni["net_income_parent"]
    uni["pe"] = np.where(ni > 0, uni["market_cap"] / ni, np.nan)
    uni["pb"] = np.where(uni["equity_parent"] > 0, uni["market_cap"] / uni["equity_parent"], np.nan)
    ev = uni["market_cap"] + uni["net_debt"].fillna(0)
    uni["ev_ebitda"] = np.where((uni["ebitda"] > 0) & (uni["company_type"] == "NON_FINANCIAL"),
                                ev / uni["ebitda"], np.nan)
    uni["eps"] = np.where(uni["shares"] > 0, ni / uni["shares"], np.nan)
    uni["liquidity_flag"] = uni["avg_value_20d"] >= MIN_LIQUID_VALUE
    uni["has_bctc"] = uni["fin_year"].notna()
    uni["as_of_price"] = pd.to_datetime(uni["as_of_price"]).dt.strftime("%Y-%m-%d")
    uni["fetched_at"] = fetched_at.strftime("%Y-%m-%d %H:%M")
    for lvl in (1, 2, 3, 4):
        uni[f"icb{lvl}"] = uni[f"icb{lvl}"].fillna(UNCLASSIFIED)
    uni = uni.drop(columns=["board_name", "vn_name", "listed_share"], errors="ignore")
    uni = uni.sort_values("market_cap", ascending=False, na_position="last").reset_index(drop=True)

    # ---- kiem tra
    n_lvl4 = uni.groupby("symbol")["icb4"].nunique().max()
    checks = {
        "n_getall": int(len(listing)), "n_universe": int(len(uni)),
        "one_icb4_per_symbol": bool(n_lvl4 == 1 and uni["symbol"].is_unique),
        "sum_icb1_equals_total": int(uni.groupby("icb1").size().sum()) == len(uni),
        "n_unclassified": int((uni["icb1"] == UNCLASSIFIED).sum()),
        "industry_source_counts": uni["industry_source"].value_counts().to_dict(),
        "n_with_price": int(uni["price"].notna().sum()),
        "n_with_bctc": int(uni["has_bctc"].sum()),
        "n_shares_approx": int(approx.sum()),
        "n_liquid": int(uni["liquidity_flag"].sum()),
        "exchange_counts": uni["exchange"].value_counts().to_dict(),
    }
    log.info("Kiem tra: %s", checks)
    assert checks["one_icb4_per_symbol"] and checks["sum_icb1_equals_total"]

    uni.to_parquet(SNAPSHOT_DIR / "market_universe.parquet", index=False)
    sector_index(uni, ohlcv).to_parquet(SNAPSHOT_DIR / "sector_index.parquet", index=False)
    store = ohlcv[["symbol", "time", "open", "high", "low", "close", "volume"]].sort_values(["symbol", "time"])
    store.to_parquet(SNAPSHOT_DIR / "ohlcv.parquet", index=False, row_group_size=8000, compression="zstd")

    meta = {
        "built_at": fetched_at.strftime("%Y-%m-%d %H:%M"),
        "as_of_price": str(uni["as_of_price"].dropna().max()),
        "as_of_fin_max": f"FY{int(uni['fin_year'].max())}",
        "sources": {
            "symbols": "Vietcap public API /price/symbols/getAll",
            "price": "Vietcap public API gap-chart (kho OHLCV ngày)",
            "board_shares": "Vietcap public API /price/symbols/getList (listedShare)",
            "industry": industry_note + " + bù fiinpro_icb_companies.csv (vn-annual-report-miner)",
            "financials": arminer_bctc.SOURCE_NAME,
        },
        "checks": checks, "elapsed_s": round(time.time() - t0, 1),
    }
    (SNAPSHOT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    if args.upload:
        upload_all()


def upload_all() -> None:
    """market_universe -> universe/latest.parquet (+ meta, ttm). Backend doc qua BLOB_BASE_URL."""
    for name, target in (("market_universe.parquet", "latest.parquet"), ("meta.json", "meta.json"),
                         ("ttm.parquet", "ttm.parquet")):
        if (SNAPSHOT_DIR / name).exists():
            print(upload_blob(SNAPSHOT_DIR / name, f"universe/{target}"))


if __name__ == "__main__":
    main()
