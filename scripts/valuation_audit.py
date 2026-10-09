"""Build the requested live-input valuation audit. Run: python scripts/valuation_audit.py"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from invest_system.web.service import analysis  # noqa: E402

SYMBOLS = "FPT VCB VIC VHM HPG MWG SSI MSN GAS VNM TCB ACB VRE BSR ACV".split()


def fmt(v, digits=1):
    return "—" if v is None else f"{v:,.{digits}f}"


def main():
    records = []
    for symbol in SYMBOLS:
        try:
            d = analysis(symbol, with_news=False)
            v, rec = d["valuation"], d["recommendation"]
            records.append({
                "symbol": symbol, "price": d.get("price"), "shares": d.get("shares"),
                "shares_source": d.get("shares_source"), "shares_as_of": v.get("shares_as_of"),
                "market_cap": d.get("market_cap"), "pe_ttm": d.get("metrics", {}).get("pe_ttm"),
                "pe_fy": d.get("metrics", {}).get("pe"), "pb": d.get("metrics", {}).get("pb"),
                "methods": [m["key"] for m in v.get("methods", []) if m.get("weight", 0) > 0],
                "target": (v.get("targets") or {}).get("base"), "upside": v.get("upside"),
                "rating": rec.get("rating"), "rating_reason": rec.get("reason"), "confidence": v.get("confidence"),
                "confidence_reason": v.get("confidence_reason"), "price_as_of": d.get("as_of_price"),
                "source": d.get("sources", [{}])[0].get("source"),
                "historical_multiples": v.get("historical_multiples", {}),
                "comparison": v.get("comparison", {}), "pb_roe_regression": v.get("pb_roe_regression"),
                "thesis": d.get("thesis", []), "risks": d.get("risks", []),
            })
            print(f"{symbol}: done", flush=True)
        except Exception as exc:  # noqa: BLE001
            records.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{symbol}: failed ({type(exc).__name__})", flush=True)

    rows = []
    for r in records:
        if "error" in r:
            rows.append(f"| {r['symbol']} | lỗi | — | — | — | — | — | — | — | — |")
            continue
        rows.append("| {symbol} | {price} | {shares} | {cap} | {pe} | {pb} | {methods} | {target} | {upside} | {rating} · {confidence} |".format(
            symbol=r["symbol"], price=fmt(r["price"], 0), shares=fmt(r["shares"], 0),
            cap=fmt((r["market_cap"] or 0) / 1e12, 2) + " T", pe=fmt(r["pe_ttm"] or r["pe_fy"], 1) + "x",
            pb=fmt(r["pb"], 2) + "x", methods=", ".join(r["methods"]) or "không đủ dữ liệu",
            target=fmt(r["target"], 0), upside=(fmt(r["upside"] * 100, 1) + "%") if r["upside"] is not None else "—",
            rating=r["rating"], confidence=r["confidence"]))
    failed_signals = [r["symbol"] for r in records if "error" not in r and r["upside"] is not None
                      and not -0.6 <= r["upside"] <= 1.5 and r["rating"] in {"MUA", "BÁN"}]
    local_data = {"generated_at": datetime.now().astimezone().isoformat(), "records": records,
                  "out_of_range_buy_sell": failed_signals}
    (ROOT / "docs" / "valuation-audit-data.json").write_text(json.dumps(local_data, ensure_ascii=False, indent=2), encoding="utf-8")
    vhm = next((r for r in records if r.get("symbol") == "VHM" and "error" not in r), {})
    vic = next((r for r in records if r.get("symbol") == "VIC" and "error" not in r), {})
    msn = next((r for r in records if r.get("symbol") == "MSN" and "error" not in r), {})
    vhm_target = fmt(vhm.get("target"), 0)
    vhm_upside = (fmt(vhm["upside"] * 100, 1) + "%") if vhm.get("upside") is not None else "—"
    vic_pb_years = len(vic.get("historical_multiples", {}).get("pb", []))
    msn_pb_years = len(msn.get("historical_multiples", {}).get("pb", []))
    doc = """# Kiểm định định giá và nhận định

Ngày tạo: {generated}

| Mã | Giá | Số CP | Vốn hoá | P/E TTM (nếu có, nếu không FY) | P/B | Phương pháp hợp lệ | Mục tiêu | Upside | Khuyến nghị · tin cậy |
|---|---:|---:|---:|---|---:|---|---:|---:|---|
{rows}

## Cách đọc và giới hạn

- Giá, số cổ phiếu, BCTC và thời điểm lấy từ snapshot ghi trong từng bản ghi; P/E ưu tiên LNST cổ đông mẹ TTM khi có, P/B dùng vốn chủ cổ đông mẹ.
- Loại chính mã mục tiêu khỏi peer set. Không dùng bội số gộp theo vốn hoá để định giá một doanh nghiệp riêng lẻ.
- P/B–ROE chỉ điều chỉnh trung vị peer khi có ít nhất 8 peer thanh khoản, hệ số dốc dương và R² ≥ 0,10; P/B mục tiêu bị chặn trong P25–P90. Nếu không đạt điều kiện, dùng trung vị peer thông thường.
- VHM sau sửa có giá trị cơ sở {vhm_target} đồng, upside {vhm_upside} trên snapshot này; kết quả khác mức outlier cũ do không còn dùng bội số gộp vốn hoá. Đây là ước tính theo snapshot, không phải dự báo chắc chắn.
- VIC và MSN là trường hợp đa ngành: không áp P/E hoặc P/B peer rộng. Snapshot có lần lượt {vic_pb_years} và {msn_pb_years} năm P/B lịch sử hợp lệ; thiếu tối thiểu ba năm thì không công bố mục tiêu giá và giữ độ tin cậy thấp.
- Quy tắc cảnh báo kiểm tra các mã nhận MUA/BÁN có upside ngoài [-60%; +150%]. Danh sách lần chạy: {failed}.
- Dữ liệu từng mã, nguồn, thời điểm, peer selection, P/B regression và historical multiples nằm trong valuation-audit-data.json.

## Đối chiếu CafeF

CafeF công bố trang tải BCTC và hồ sơ tài chính hiện hành cho ACV; trang tải tài liệu có báo cáo hợp nhất năm 2025 đã kiểm toán và các báo cáo quý. CafeF cũng có báo cáo thường niên 2025 của BSR, VEA và MCH. Các tài liệu công khai này chưa được đối chiếu từng chỉ tiêu với snapshot trong repo ở lần chạy này; cần tải đúng báo cáo hợp nhất, cùng kỳ, rồi so khớp đơn vị và phạm vi hợp nhất trước khi đánh dấu PASS. [ACV – tải BCTC](https://cafef.vn/du-lieu/upcom/acv-tai-lieu.chn) · [ACV – hồ sơ](https://cafef.vn/du-lieu/acv/thong-tin-chung.chn) · [BSR – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/160426/bsr-bao-cao-thuong-nien-nam-2025-0.pdf) · [VEA – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/210426/vea-bao-cao-thuong-nien-2025-0-610380.pdf) · [MCH – báo cáo thường niên 2025](https://cafef1.mediacdn.vn/download/150426/mch-bao-cao-thuong-nien-nam-2025-0.pdf).

## PDF

Đối chiếu trường số liệu với văn bản PDF được tạo bởi scripts/audit_report_numbers.py; kết quả hiện tại nằm trong docs/pdf-audit.md. Nếu chưa cung cấp PDF đầu vào, trạng thái PDF là NOT CHECKED.
""".format(generated=local_data["generated_at"], rows="\n".join(rows), failed=", ".join(failed_signals) or "không có",
           vhm_target=vhm_target, vhm_upside=vhm_upside, vic_pb_years=vic_pb_years, msn_pb_years=msn_pb_years)
    (ROOT / "docs" / "valuation-audit.md").write_text(doc, encoding="utf-8")
    print(f"Wrote docs/valuation-audit.md ({len(records)} symbols); out-of-range MUA/BÁN: {failed_signals}")


if __name__ == "__main__":
    main()
