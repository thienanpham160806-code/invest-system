"""Compare the active market universe with packaged annual reports."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.data.arminer_bctc import _vnstock_supplement, coverage  # noqa: E402
from invest_system.web.universe import load_universe  # noqa: E402


def build() -> dict:
    uni, _ = load_universe()
    bctc = coverage().copy()
    bctc["exchange"] = bctc["exchange"].replace({"HSX": "HOSE", "HOSE": "HOSE"})
    supplement = _vnstock_supplement().copy()
    if not supplement.empty:
        supplement = supplement[supplement["exchange"].astype(str).str.upper() == "UPCOM"]
        supplement = supplement.groupby("ticker").agg(first_year=("year", "min"), last_year=("year", "max")).reset_index()
    else:
        supplement = pd.DataFrame(columns=["ticker", "first_year", "last_year"])
    active = set(uni["symbol"].astype(str))
    financial = set(bctc["ticker"].astype(str))
    by_exchange = {}
    missing = {}
    for exchange in ("HOSE", "HNX", "UPCOM"):
        members = uni[uni["exchange"] == exchange]
        tickers = set(members["symbol"].astype(str))
        # The packaged source explicitly contains only HSX/HNX, even if a
        # same-symbol historical row happens to match a current UPCOM ticker.
        if exchange == "UPCOM":
            matched = supplement[supplement["ticker"].isin(tickers)]
        else:
            matched = bctc[(bctc["ticker"].isin(tickers)) & (bctc["exchange"] == exchange)]
        matched_tickers = set(matched["ticker"].astype(str))
        covered_cap = members.loc[members["symbol"].isin(matched_tickers), "market_cap"].fillna(0).sum()
        exchange_cap = members["market_cap"].fillna(0).sum()
        miss = sorted(tickers - matched_tickers)
        missing[exchange] = miss
        by_exchange[exchange] = {
            "listed": len(members), "with_bctc": int(matched["ticker"].nunique()),
            "coverage_pct": round(100 * matched["ticker"].nunique() / len(members), 2) if len(members) else 0,
            "market_cap_covered": float(covered_cap), "market_cap_total": float(exchange_cap),
            "market_cap_coverage_pct": round(100 * covered_cap / exchange_cap, 2) if exchange_cap else 0,
            "with_fy2025": int((matched["last_year"] >= 2025).sum()),
            "only_fy2024_or_older": int((matched["last_year"] < 2025).sum()),
            "missing_count": len(miss),
        }
    delisted = bctc[~bctc["ticker"].isin(active)].sort_values("ticker")
    return {
        "source": "vn-annual-report-miner (HOSE/HNX) + vnstock VCI supplement (when available)",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "listed_total": int(len(uni)), "source_total": int(len(financial | set(supplement["ticker"].astype(str)))) if not supplement.empty else int(len(financial)),
        "by_exchange": by_exchange, "missing": missing,
        "delisted_count": int(delisted["ticker"].nunique()),
        "delisted": delisted["ticker"].astype(str).tolist(),
    }


def main() -> None:
    data = build()
    (ROOT / "webdata" / "bctc_coverage.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Độ phủ BCTC năm theo sàn", "", f"Nguồn: {data['source']}",
             f"Universe: {data['listed_total']:,} mã; cập nhật {data['generated_at']}.", "",
             "| Sàn | Mã niêm yết | Có BCTC | Độ phủ mã | Độ phủ vốn hoá | Có FY2025 | FY2024 trở về trước | Thiếu |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for exch, row in data["by_exchange"].items():
        lines.append(f"| {exch} | {row['listed']:,} | {row['with_bctc']:,} | {row['coverage_pct']:.2f}% | {row['market_cap_coverage_pct']:.2f}% | {row['with_fy2025']:,} | {row['only_fy2024_or_older']:,} | {row['missing_count']:,} |")
    lines += ["", "## Mã HOSE/HNX thiếu BCTC từ nguồn chính", ""]
    for exch in ("HOSE", "HNX"):
        lines += [f"### {exch} ({len(data['missing'][exch])} mã)", "", ", ".join(data["missing"][exch]) or "Không có.", ""]
    lines += ["### UPCOM", "", "UPCOM được đối chiếu theo nguồn bổ sung vnstock VCI; mã chỉ được tính khi dữ liệu đã qua kiểm tra đơn vị, phương trình bảng cân đối và chỉ tiêu doanh thu theo loại hình doanh nghiệp.", "",
              f"## Mã trong nguồn nhưng không còn niêm yết ({data['delisted_count']})", "",
              ", ".join(data["delisted"]) or "Không có.", ""]
    (ROOT / "docs" / "bctc-coverage.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"listed={data['listed_total']} source={data['source_total']} delisted={data['delisted_count']}")
    for exch, row in data["by_exchange"].items():
        print(f"{exch}: {row['with_bctc']}/{row['listed']} ({row['coverage_pct']}%), FY2025={row['with_fy2025']}, missing={row['missing_count']}")


if __name__ == "__main__":
    main()
