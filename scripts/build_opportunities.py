"""Build a full-universe, resumable snapshot from the same analysis as stock pages.

Run ``python scripts/build_opportunities.py --resume``. Use ``--top N`` for a
small smoke run; the default processes every current universe symbol.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from invest_system.web import service  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR, load_ohlcv_snapshot, load_universe, load_vnindex_snapshot  # noqa: E402

WORK = SNAPSHOT_DIR / "opportunities-work.json"
OUTPUT = SNAPSHOT_DIR / "opportunities.json"
warnings.filterwarnings("ignore", category=FutureWarning,
                        message="The default fill_method='pad' in Series.pct_change is deprecated")


def _record(symbol: str) -> dict:
    result = service.analysis(symbol, with_news=False)
    val = result["valuation"]
    rec = result["recommendation"]
    return {
        "symbol": symbol, "name": result.get("name"), "exchange": result.get("exchange"),
        "industry": result.get("icb", {}).get("icb2"), "price": result.get("price"),
        "target_price": val.get("targets", {}).get("base"), "targets": val.get("targets"),
        "upside": val.get("upside"), "confidence": val.get("confidence"),
        "confidence_reason": val.get("confidence_reason"), "rating": rec.get("rating"),
        "score": rec.get("total_score"), "reason": rec.get("reason"),
        "avg_value_20d": result.get("metrics", {}).get("avg_value_20d"),
        "market_cap": result.get("market_cap"),
        "score_groups": rec.get("scores"),
        "quality_failures": [check.get("name") for check in result.get("checks", [])
                             if check.get("status") == "FAIL"],
        "quality_warnings": [check.get("name") for check in result.get("checks", [])
                              if check.get("status") == "WARN"],
        "as_of_price": result.get("as_of_price"), "generated_at": result.get("generated_at"),
        "has_bctc": result.get("bctc_available"),
    }


def build(top: int | None, resume: bool, work_path: Path = WORK, output_path: Path = OUTPUT) -> None:
    # Produce a deterministic snapshot and avoid making 1,522 requests to live
    # price endpoints during a scheduled build.
    service.price_frame = lambda symbol, days=750: (
        load_ohlcv_snapshot(symbol).tail(days), service.prov("Vietcap packaged price snapshot")
    )
    service._vnindex_live = lambda days=400: (
        load_vnindex_snapshot().tail(days), service.prov("VN-Index packaged snapshot")
    )
    universe, meta = load_universe()
    symbols = universe["symbol"].astype(str).tolist()
    if top:
        symbols = symbols[:top]
    records = {}
    if resume and work_path.exists():
        records = json.loads(work_path.read_text(encoding="utf-8"))
    for index, symbol in enumerate(symbols, 1):
        if (symbol in records and "error" not in records[symbol]
                and "quality_failures" in records[symbol]
                and "score_groups" in records[symbol]):
            continue
        try:
            records[symbol] = _record(symbol)
        except Exception as exc:  # noqa: BLE001
            records[symbol] = {"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"}
        work_path.parent.mkdir(parents=True, exist_ok=True)
        work_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        if index % 25 == 0 or index == len(symbols):
            print(f"{index}/{len(symbols)} analyzed; records={len(records)}", flush=True)

    rows = [r for s, r in records.items() if s in set(symbols) and "error" not in r]
    for row in rows:
        upside = row.get("upside")
        score = row.get("score")
        # Opportunity score is the existing composite score. Require current
        # financials, no failed validation, enough liquidity, and supported
        # positive upside before ranking a name as eligible.
        reasons = []
        if not row.get("has_bctc"):
            reasons.append("Thiếu BCTC")
        if row.get("quality_failures"):
            reasons.append("Có kiểm tra dữ liệu FAIL")
        if row.get("confidence") not in {"CAO", "TRUNG BÌNH"}:
            reasons.append("Độ tin cậy định giá thấp")
        if not isinstance(row.get("avg_value_20d"), (int, float)) or row["avg_value_20d"] < 5e9:
            reasons.append("GTGD TB20 dưới 5 tỷ")
        if not isinstance(upside, (int, float)) or upside <= 0:
            reasons.append("Upside không dương hoặc chưa có")
        elif upside > 1.5:
            reasons.append("Upside vượt ngưỡng kiểm tra 150%")
        if row.get("rating") != "MUA":
            reasons.append("Khung điểm chưa đạt MUA")
        row["tracking_reasons"] = reasons
        row["eligible"] = bool(
            row.get("has_bctc") and not row.get("quality_failures")
            and row.get("confidence") in {"CAO", "TRUNG BÌNH"}
            and isinstance(row.get("avg_value_20d"), (int, float)) and row["avg_value_20d"] >= 5e9
            and row.get("rating") == "MUA" and isinstance(upside, (int, float))
            and 0 < upside <= 1.5 and isinstance(score, (int, float))
        )
    rows.sort(key=lambda r: (r["eligible"], r.get("score") or -1, r.get("upside") or -10,
                             r.get("avg_value_20d") or 0), reverse=True)
    up = [r.get("upside") for r in rows if isinstance(r.get("upside"), (int, float))]
    bins = {"lt_minus_50pct": 0, "minus_50_to_0pct": 0, "0_to_25pct": 0,
            "25_to_50pct": 0, "50_to_100pct": 0, "gt_100pct": 0, "missing": 0}
    for row in rows:
        value = row.get("upside")
        if not isinstance(value, (int, float)):
            bins["missing"] += 1
        elif value < -0.5:
            bins["lt_minus_50pct"] += 1
        elif value < 0:
            bins["minus_50_to_0pct"] += 1
        elif value < 0.25:
            bins["0_to_25pct"] += 1
        elif value < 0.5:
            bins["25_to_50pct"] += 1
        elif value <= 1.0:
            bins["50_to_100pct"] += 1
        else:
            bins["gt_100pct"] += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_at": service.now_str(), "universe_built_at": meta.get("built_at"),
        "universe_count": len(universe), "analyzed_count": len(rows),
        "errors": len(records) - len(rows), "upside_distribution": bins,
        "positive_upside_count": sum(value > 0 for value in up),
        "outlier_upside_count": sum(value < -0.6 or value > 1.5 for value in up),
        "eligible_count": sum(bool(row["eligible"]) for row in rows),
        "minimum_liquidity_vnd": 5_000_000_000,
        "opportunity_score": "Điểm tổng hợp hiện có; hòa điểm xét upside rồi thanh khoản",
        "top20": rows[:20], "items": rows,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = ["# Kiểm toán ranking cơ hội", "", f"Snapshot: {result['generated_at']}",
             f"Universe: {result['analyzed_count']:,}/{result['universe_count']:,} mã; lỗi phân tích: {result['errors']}.",
             "", "## Phân phối upside", "", "| Khoảng | Số mã |", "|---|---:|"]
    labels = {"lt_minus_50pct": "Dưới -50%", "minus_50_to_0pct": "-50% đến 0%", "0_to_25pct": "0% đến 25%",
              "25_to_50pct": "25% đến 50%", "50_to_100pct": "50% đến 100%", "gt_100pct": "Trên 100%", "missing": "Không có mục tiêu"}
    audit += [f"| {labels[key]} | {count:,} |" for key, count in bins.items()]
    audit += ["", f"Mã upside ngoài [-60%, +150%]: {result['outlier_upside_count']:,}. Các mã này không đủ điều kiện vào bảng cơ hội. Điều kiện gồm MUA, có BCTC, không có kiểm tra FAIL, độ tin cậy trung bình/cao, GTGD TB20 từ 5 tỷ và upside dương không quá 150%.",
              "", "## Top 20 đủ điều kiện", "", "| # | Mã | Tên | Sàn | Điểm | Upside | Tin cậy |", "|---:|---|---|---|---:|---:|---|"]
    audit += [f"| {i} | {r['symbol']} | {r.get('name') or '—'} | {r.get('exchange') or '—'} | {r.get('score') or 0:.1f} | {r.get('upside') or 0:.1%} | {r.get('confidence') or '—'} |"
              for i, r in enumerate(result["top20"], 1)]
    (ROOT / "docs" / "opportunity-audit.md").write_text("\n".join(audit) + "\n", encoding="utf-8")
    print(f"Wrote {output_path}: {len(rows)} ranked records")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.top, args.resume, args.work, args.output)


if __name__ == "__main__":
    main()
