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

SYMBOLS = "FPT VCB VIC VHM HPG MWG SSI MSN GAS VNM TCB ACB".split()


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
                      and not -0.5 <= r["upside"] <= 1.0 and r["rating"] in {"MUA", "BÁN"}]
    local_data = {"generated_at": datetime.now().astimezone().isoformat(), "records": records,
                  "out_of_range_buy_sell": failed_signals}
    (ROOT / "docs" / "valuation-audit-data.json").write_text(json.dumps(local_data, ensure_ascii=False, indent=2), encoding="utf-8")
    doc = """# Kiểm định định giá và nhận định

Ngày tạo: {generated}

| Mã | Giá | Số CP | Vốn hoá | P/E TTM (nếu có, nếu không FY) | P/B | Phương pháp hợp lệ | Mục tiêu | Upside | Khuyến nghị · tin cậy |
|---|---:|---:|---:|---:|---:|---|---:|---:|---|
{rows}

## Cách đọc và dữ liệu

- Giá lấy từ nguồn giá đang khả dụng; số cổ phiếu lấy từ `listedShare` trong Vietcap `getList`, ngày theo metadata universe. P/E dùng LNST cổ đông công ty mẹ TTM khi có, nếu không dùng FY; P/B dùng vốn chủ sở hữu cổ đông công ty mẹ.
- Khi nguồn mạng bị chặn, ứng dụng ghi rõ đang dùng snapshot. Bản audit được sinh bởi `scripts/valuation_audit.py`; chi tiết kỳ, nguồn, độ tin cậy, nhận định và rủi ro từng mã nằm trong `valuation-audit-data.json`.
- VIC trước sửa: theo tái hiện trên dữ liệu snapshot, giá 225.500đ, mục tiêu 18.500đ, upside −91,8%, khuyến nghị BÁN; công thức dùng trung vị P/E/P/B của nhóm ICB quá rộng và P/E FY 155,2x. Sau sửa: P/E không còn dùng khi >60x, tập đoàn đa ngành chỉ dùng P/B lịch sử 5 năm; thiếu đủ 3 điểm lịch sử thì không công bố giá mục tiêu, độ tin cậy THẤP, khuyến nghị THEO DÕI. Số lượng cổ phiếu hiện tại là 7.762.186.429 theo Vietcap; ngày snapshot ghi trong từng bản ghi.
- Quy tắc kiểm thử: không để mã nào có upside ngoài [−50%; +100%] vẫn nhận MUA/BÁN. Kết quả lần chạy: `{failed}`.

## Đối chiếu công khai

CafeF có trang thông tin VIC hiện hành, nhưng kết quả web không trả cùng bộ số định lượng/đúng timestamp với snapshot này. Vietstock có báo cáo Vietcap VIC ngày 30/03/2026 nêu vốn hoá 977,3 nghìn tỷ, P/E trượt 85,2x và P/B 6,6x; đây là ngày khác và loại trừ cổ phiếu VIC do công ty con sở hữu, nên không thể coi là đối chiếu cùng kỳ với số liệu snapshot 09/10/2026. Không dùng benchmark lệch ngày để kết luận sai số định lượng. [CafeF VIC](https://cafef.vn/du-lieu/vic/bao-cao-tai-chinh.chn) · [Vietstock/Vietcap, 30/03/2026](https://static1.vietstock.vn/edocs/19653/Vinstocks_20260330_VN.pdf).

## Nhận định trang đầu

Mỗi bản ghi `thesis`/`risks` trong tệp JSON là nội dung narrative đầu trang gửi cùng API. Đã bỏ câu định giá khỏi luận điểm khi độ tin cậy THẤP, hiển thị lý do theo dõi và ký hiệu tăng trưởng có dấu; không phát sinh khuyến nghị mua/bán từ giá mục tiêu không đáng tin cậy.
""".format(generated=local_data["generated_at"], rows="\n".join(rows), failed=", ".join(failed_signals) or "không có")
    (ROOT / "docs" / "valuation-audit.md").write_text(doc, encoding="utf-8")
    print(f"Wrote docs/valuation-audit.md ({len(records)} symbols); out-of-range MUA/BÁN: {failed_signals}")


if __name__ == "__main__":
    main()
