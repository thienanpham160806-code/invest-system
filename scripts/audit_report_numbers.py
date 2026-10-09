"""Cross-check key analysis numbers and, optionally, text extracted from PDFs.

Run with the repo's shared Python environment:
  python scripts/audit_report_numbers.py
  python scripts/audit_report_numbers.py --pdf-dir outputs/reports
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.web import service  # noqa: E402
from invest_system.web.service import analysis, financials_std, jsonable  # noqa: E402

SYMBOLS = "FPT VCB VIC VHM HPG MWG SSI MSN GAS VNM TCB ACB VRE BSR ACV".split()
FIELDS = ("price", "shares", "market_cap", "revenue_fy", "net_income_parent_fy", "total_assets",
          "total_liabilities", "equity", "balance_error_pct", "pe_ttm", "pb", "roe", "target_base",
          "upside", "confidence")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _matches(actual, expected, rel: float = 0.03, abs_tol: float = 0.01) -> bool:
    return (_is_number(actual) and _is_number(expected)
            and abs(actual - expected) <= max(abs_tol, abs(expected) * rel))


def _formula_status(actual, expected, rel: float = 0.03, abs_tol: float = 0.01) -> str:
    if not _is_number(actual) and not _is_number(expected):
        return "SKIP"
    return "PASS" if _matches(actual, expected, rel, abs_tol) else "WARN"


def audit_one(symbol: str) -> dict:
    result = analysis(symbol, with_news=False)
    fin = financials_std(symbol, 10)
    year = fin.last_year() if not fin.empty else None
    get = lambda field: fin.get(field, year) if year is not None else None
    assets, liabilities, equity = get("total_assets"), get("total_liabilities"), get("equity")
    balance_error = (abs(assets - liabilities - equity) / assets
                     if all(_is_number(v) for v in (assets, liabilities, equity)) and assets else None)
    parent_equity = equity - (get("minority_interest") or 0) if equity is not None else None
    current_cap = result.get("market_cap")
    price_now, shares = result.get("price"), result.get("shares")
    cap_calc = price_now * shares if _is_number(price_now) and _is_number(shares) else None
    pb_check = current_cap / parent_equity if current_cap and parent_equity and parent_equity > 0 else None
    actual_pb = result.get("metrics", {}).get("pb")
    ttm_income = result.get("metrics", {}).get("ni_ttm")
    pe_calc = cap_calc / ttm_income if cap_calc and _is_number(ttm_income) and ttm_income else None
    previous_parent_equity = None
    if year is not None and year - 1 in set(fin.years):
        prior_equity = fin.get("equity", year - 1)
        prior_minority = fin.get("minority_interest", year - 1) or 0
        if _is_number(prior_equity):
            previous_parent_equity = prior_equity - prior_minority
    roe_calc = (get("net_income_parent") / ((parent_equity + previous_parent_equity) / 2)
                if _is_number(get("net_income_parent")) and _is_number(parent_equity)
                and _is_number(previous_parent_equity) and parent_equity + previous_parent_equity else None)
    valuation = result.get("valuation", {})
    methods = [method for method in valuation.get("methods", [])
               if _is_number(method.get("weight")) and method["weight"] > 0
               and _is_number(method.get("values", {}).get("base"))]
    method_weight = sum(method["weight"] for method in methods)
    target_calc_raw = (sum(method["weight"] * method["values"]["base"] for method in methods) / method_weight
                       if method_weight else None)
    target_calc = round(target_calc_raw / 100) * 100 if target_calc_raw is not None else None
    upside_calc = (valuation.get("targets", {}).get("base") / price_now - 1
                   if _is_number(valuation.get("targets", {}).get("base"))
                   and _is_number(price_now) and price_now else None)
    recommendation = result.get("recommendation", {})
    scores, weights = recommendation.get("scores", {}), recommendation.get("weights", {})
    weight_total = sum(value for value in weights.values() if _is_number(value))
    score_calc = (sum(weights[key] * scores[key] for key in weights
                       if key in scores and _is_number(weights[key]) and _is_number(scores[key])) / weight_total
                  if weight_total else None)
    price_frame, _ = service.price_frame(symbol, days=400)
    close = price_frame["close"].dropna() if not price_frame.empty and "close" in price_frame else None
    def ret_sessions(n: int):
        if close is None or len(close) <= n or not close.iloc[-n - 1]:
            return None
        return close.iloc[-1] / close.iloc[-n - 1] - 1
    high_52w = float(close.tail(252).max()) if close is not None and len(close) else None
    low_52w = float(close.tail(252).min()) if close is not None and len(close) else None
    bvps_calc = parent_equity / shares if _is_number(parent_equity) and _is_number(shares) and shares else None
    checks = {
        "balance_sheet_identity": "PASS" if balance_error is not None and balance_error <= 0.01 else "WARN",
        "pb_vs_parent_equity": "PASS" if pb_check is not None and actual_pb is not None
            and abs(pb_check - actual_pb) <= max(0.05, abs(actual_pb) * 0.05) else "WARN",
        "price_positive": "PASS" if _is_number(result.get("price")) and result["price"] > 0 else "FAIL",
        "shares_positive": "PASS" if _is_number(result.get("shares")) and result["shares"] > 0 else "WARN",
        "valuation_confidence_present": "PASS" if result.get("valuation", {}).get("confidence") else "WARN",
        "market_cap_formula": _formula_status(current_cap, cap_calc, rel=0.01),
        "pe_ttm_formula": _formula_status(result.get("metrics", {}).get("pe_ttm"), pe_calc, rel=0.05),
        "pb_formula": _formula_status(actual_pb, pb_check, rel=0.05),
        "roe_formula": _formula_status(result.get("metrics", {}).get("roe"), roe_calc, rel=0.05),
        "target_weighted_methods": _formula_status(valuation.get("targets", {}).get("base"), target_calc, rel=0.001, abs_tol=100),
        "upside_formula": _formula_status(valuation.get("upside"), upside_calc, rel=0.001),
        "composite_score_formula": _formula_status(recommendation.get("total_score"), score_calc, rel=0.001),
    }
    values = {
        "price": result.get("price"), "shares": result.get("shares"), "market_cap": current_cap,
        "revenue_fy": get("total_operating_income") if result.get("company_type") == "BANK" else get("revenue"),
        "net_income_parent_fy": get("net_income_parent"), "total_assets": assets,
        "total_liabilities": liabilities, "equity": equity, "balance_error_pct": balance_error,
        "pe_ttm": result.get("metrics", {}).get("pe_ttm"), "pb": actual_pb,
        "roe": result.get("metrics", {}).get("roe"),
        "eps_calc": get("net_income_parent") / shares if _is_number(get("net_income_parent")) and _is_number(shares) and shares else None,
        "bvps_calc": bvps_calc, "market_cap_calc": cap_calc, "pe_ttm_calc": pe_calc,
        "pb_calc": pb_check, "roe_calc": roe_calc, "target_base_calc": target_calc,
        "upside_calc": upside_calc, "composite_score": recommendation.get("total_score"),
        "composite_score_calc": score_calc, "return_1m_calc": ret_sessions(21),
        "return_3m_calc": ret_sessions(63), "return_1y_calc": ret_sessions(252),
        "high_52w_calc": high_52w, "low_52w_calc": low_52w,
        "target_base": result.get("valuation", {}).get("targets", {}).get("base"),
        "upside": result.get("valuation", {}).get("upside"),
        "confidence": result.get("valuation", {}).get("confidence"),
    }
    sources = {"price": result.get("as_of_price"), "shares": result.get("shares_source"),
               "financials": fin.source if not fin.empty else None, "financial_year": year}
    return {"symbol": symbol, "values": values, "checks": checks, "sources": sources,
            "recalculated": {"market_cap": cap_calc, "pe_ttm": pe_calc, "pb": pb_check,
                             "roe": roe_calc, "eps": values["eps_calc"], "bvps": bvps_calc,
                             "target_base": target_calc, "upside": upside_calc,
                             "composite_score": score_calc, "return_1m": ret_sessions(21),
                             "return_3m": ret_sessions(63), "return_1y": ret_sessions(252),
                             "high_52w": high_52w, "low_52w": low_52w},
            "historical_multiples": result.get("valuation", {}).get("historical_multiples", {}),
            "valuation_comparison": result.get("valuation", {}).get("comparison", {}),
            "pb_roe_regression": result.get("valuation", {}).get("pb_roe_regression")}


def compare_pdf_text(pdf_dir: Path, records: list[dict]) -> dict:
    pdfs = {p.stem.split("_")[0].upper(): p for p in pdf_dir.glob("*.pdf")}
    output = {}
    for record in records:
        symbol = record["symbol"]
        path = pdfs.get(symbol)
        if path is None:
            output[symbol] = {"status": "MISSING", "file": None, "matched_fields": [],
                              "note": "Chưa có PDF cho mã này trong thư mục."}
            continue
        try:
            from invest_system.analysis.fintext import extract_text
            text = extract_text(path)
            compact = text.replace(",", "").replace(".", "").replace(" ", "")
            matches = []
            for key in ("price", "shares", "market_cap", "revenue_fy", "net_income_parent_fy", "total_assets", "equity"):
                value = record["values"].get(key)
                if not _is_number(value):
                    continue
                token = f"{value:,.0f}".replace(",", "")
                if token and token in compact:
                    matches.append(key)
            output[symbol] = {"status": "PASS" if len(matches) >= 3 else "WARN", "file": str(path),
                              "matched_fields": matches, "checked_fields": 7,
                              "note": "Text search confirms rounded numeric tokens; it does not prove section labels or semantic placement."}
        except Exception as exc:  # noqa: BLE001
            output[symbol] = {"status": "ERROR", "file": str(path), "error": f"{type(exc).__name__}: {exc}"}
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=Path)
    args = parser.parse_args()
    records = []
    for symbol in SYMBOLS:
        try:
            records.append(audit_one(symbol))
            print(f"{symbol}: audited", flush=True)
        except Exception as exc:  # noqa: BLE001
            records.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}", "checks": {"analysis": "FAIL"}})
            print(f"{symbol}: failed: {type(exc).__name__}", flush=True)
    pdf = compare_pdf_text(args.pdf_dir, records) if args.pdf_dir else {}
    result = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "symbols": SYMBOLS, "fields": FIELDS, "records": records, "pdf_comparison": pdf}
    (ROOT / "docs" / "pdf-audit-data.json").write_text(
        json.dumps(jsonable(result), ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Báo cáo kiểm tra số liệu trong báo cáo", "", f"Tạo lúc: {result['generated_at']}",
             "", "Kiểm tra 15 mã × 15 trường: giá, số cổ phiếu, vốn hóa, doanh thu FY, LNST cổ đông mẹ, tổng tài sản, nợ phải trả, vốn chủ, sai lệch phương trình kế toán, P/E TTM, P/B, ROE, giá trị cơ sở, upside và độ tin cậy.",
             "", "| Mã | Năm BCTC | Đồng nhất CDKT | P/B vs VCSH mẹ | Giá | Số CP | Độ tin cậy | PDF |", "|---|---:|---|---|---|---|---|---|"]
    for record in records:
        checks = record.get("checks", {})
        pdf_state = pdf.get(record["symbol"], {}).get("status", "NOT CHECKED")
        lines.append(f"| {record['symbol']} | {record.get('sources', {}).get('financial_year', '—')} | {checks.get('balance_sheet_identity', 'FAIL')} | {checks.get('pb_vs_parent_equity', 'FAIL')} | {checks.get('price_positive', 'FAIL')} | {checks.get('shares_positive', 'FAIL')} | {checks.get('valuation_confidence_present', 'FAIL')} | {pdf_state} |")
    formula_states = [status for record in records for key, status in record.get("checks", {}).items()
                      if key.endswith("_formula") or key in {"target_weighted_methods", "composite_score_formula"}]
    lines += ["", f"Kiểm tra công thức độc lập: PASS {formula_states.count('PASS')}, WARN {formula_states.count('WARN')}, SKIP {formula_states.count('SKIP')}, FAIL {formula_states.count('FAIL')}.",
              "SKIP nghĩa là snapshot thiếu đầu vào để tính (ví dụ ACV chưa có BCTC hoặc VIC/MSN chưa có mục tiêu định giá); WARN cần rà số liệu/phương pháp."]
    lines += ["", "## Giới hạn đối chiếu PDF", "", "Nếu `--pdf-dir` được truyền, script tìm PDF theo mã, trích text và tìm các token số đã làm tròn. Đây là đối chiếu tự động mức sơ bộ; không xác minh token nằm đúng nhãn/đúng phần. `MISSING` nghĩa là chưa có PDF được cung cấp, không được tính là PASS.",
              "", "## Kiểm tra định giá trọng điểm", "", "VHM được định giá theo nhóm peer đã loại chính mã mục tiêu; regression P/B–ROE chỉ bật khi mẫu thanh khoản đủ lớn, hệ số dốc dương và R² đạt ngưỡng; P/B dự báo bị chặn trong P25–P90. Các mã đa ngành VIC/MSN chỉ dùng P/B lịch sử nếu có ít nhất ba FY giao dịch hợp lệ; khi snapshot giá không có đủ điểm lịch sử, hệ thống hạ độ tin cậy và không xuất mục tiêu giá.",
              "", "Dữ liệu từng mã, 15 trường, nguồn và thời điểm nằm trong `pdf-audit-data.json`.", ""]
    (ROOT / "docs" / "pdf-audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote docs/pdf-audit.md; records={len(records)}; pdfs={len(pdf)}")


if __name__ == "__main__":
    main()
