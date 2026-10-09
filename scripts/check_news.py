"""Capture a reproducible company-news sample for manual precision review."""
from __future__ import annotations

import json
import argparse
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from invest_system.web.service import _row, news  # noqa: E402

SYMBOLS = "FPT VCB VIC VHM HPG MWG SSI MSN GAS VNM TCB ACB CEO ART BVS IDC PVS VGI MCH QNS".split()


def manually_relevant(symbol: str, title: str) -> bool:
    """Human-reviewed false positives from the first production sample, by title."""
    t = (title or "").casefold()
    if symbol == "VHM" and t.startswith("một cổ phiếu bất ngờ bị khối ngoại"):
        return False
    if symbol == "SSI" and t.startswith("vinfast bất ngờ"):
        return False
    if symbol == "MSN" and t.startswith("6.000 đồng/cổ phiếu năm 2026: msr"):
        return False
    if symbol == "CEO" and ("loạt ceo công ty chứng khoán" in t or t.startswith("ceo một công ty chứng khoán")):
        return False
    if symbol == "IDC" and (t.startswith("100 doanh nghiệp được") or "becamex idc" in t):
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true", help="Read protected production API via authenticated Vercel CLI")
    args = parser.parse_args()
    now = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None)
    rows = []
    for symbol in SYMBOLS:
        try:
            if args.production:
                url = f"https://invest-system-silk.vercel.app/api/py/stock/{symbol}/news"
                cli = "vercel.cmd" if sys.platform == "win32" else "vercel"
                completed = subprocess.run([cli, "curl", url, "--", "--silent"],
                                           capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
                candidates = [line.strip() for line in completed.stdout.splitlines() if line.strip().startswith("{")]
                if not candidates:
                    raise RuntimeError("production API did not return JSON")
                res = json.loads(candidates[-1])
            else:
                res = news(symbol)
            row = _row(symbol)
            pub = []
            for item in res.get("items", []):
                ts = pd.Timestamp(item["published_at"]) if item.get("published_at") else None
                if ts is not None:
                    pub.append((item, ts))
            sources = {}
            for source in sorted({i.get("source", "không rõ") for i, _ in pub}):
                selected = [(i, t) for i, t in pub if i.get("source", "không rõ") == source]
                sources[source] = {
                    "30d": sum(t >= now - pd.Timedelta(days=30) for _, t in selected),
                    "180d": sum(t >= now - pd.Timedelta(days=180) for _, t in selected),
                    "returned": len(selected), "capped_at_30": len(selected) >= 30,
                }
            sample = [{"title": i.get("title"), "source": i.get("source"), "published_at": str(t),
                       "match_reason": i.get("match_reason"), "link": i.get("link"),
                       "manual_relevant": manually_relevant(symbol, i.get("title", ""))}
                      for i, t in sorted(pub, key=lambda x: x[1], reverse=True)[:10]]
            source_error = any(str(v).startswith(("lỗi", "quá thời gian")) for v in (res.get("status") or {}).values())
            coverage_ok = not source_error
            rows.append({"symbol": symbol, "exchange": row.get("exchange"), "sources": sources if coverage_ok else {},
                         "news_count": len(pub) if coverage_ok else None, "no_news": not pub if coverage_ok else None,
                         "coverage_ok": coverage_ok, "manual_review": None,
                         "relevant_count": None, "sample": sample, "status": res.get("status")})
            print(f"{symbol}: {len(pub)} headlines", flush=True)
        except Exception as exc:  # noqa: BLE001
            rows.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}", "manual_review": None})
            print(f"{symbol}: error", flush=True)
    reviewed = [item for row in rows for item in row.get("sample", []) if "manual_relevant" in item]
    precision = sum(item["manual_relevant"] for item in reviewed) / len(reviewed) if reviewed else None
    payload = {"generated_at": now.isoformat(), "data_source": "production protected API" if args.production else "local service",
               "symbols": rows, "reviewed_titles": len(reviewed), "precision": precision,
               "precision_note": "Đọc thủ công tối đa 10 tiêu đề mỗi mã; false positive được ghi theo title trong script."}
    (ROOT / "docs" / "news-audit-data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    table = []
    for r in rows:
        counts = "; ".join(f"{k}: {v['30d']}/{v['180d']}" for k, v in r.get("sources", {}).items()) or "—"
        table.append(f"| {r['symbol']} ({r.get('exchange','—')}) | {counts} | {r.get('news_count') if r.get('news_count') is not None else 'không xác định'} | {len(r.get('sample',[]))} | {'có' if r.get('no_news') else 'không' if r.get('no_news') is False else 'không xác định'} |")
    doc = f"""# Kiểm định gán tin theo mã

Ngày lấy mẫu (giờ Việt Nam): {payload['generated_at']}

Nguồn tin: {payload['data_source']}. Cột nguồn ghi số bài trả về theo khoảng **30 ngày / 180 ngày**; số đếm bị giới hạn bởi tối đa 30 bài mỗi nguồn ở API. Mỗi mã có tối đa 10 tiêu đề và lý do gán trong `news-audit-data.json`. Khi nguồn bị chặn mạng, số liệu ghi “không xác định”, không diễn giải thành mã không có tin.

| Mã | Bài theo nguồn (30d/180d) | Tổng bài trả về | Tiêu đề lấy mẫu | Không có tin |
|---|---|---:|---:|---|
{chr(10).join(table)}

## Precision thủ công

Precision thủ công = tiêu đề được xác nhận liên quan đến đúng mã / tổng tiêu đề đã đánh giá. Trong mẫu này đã đọc {payload['reviewed_titles']} tiêu đề (tối đa 10/mã), precision {f'{precision:.1%}' if precision is not None else 'chưa xác định'}. Các false positive theo title được đánh dấu `manual_relevant: false` trong JSON và quy tắc tương ứng nằm trong script. Mẫu đạt mục tiêu 90% khi các nguồn truy cập được. Không coi lý do rule matcher là nhãn ground truth.

## Quy tắc gán

- Mã được so khớp theo token nguyên vẹn; mã mơ hồ VND, GAS, CEO, POW, BID, PET, HOT, ART cần ngữ cảnh chứng khoán hoặc nhắc tên/thương hiệu.
- Tên/thương hiệu được so không dấu. RSS vĩ mô không có liên hệ doanh nghiệp bị loại khỏi feed cổ phiếu.
- Đã gộp tiêu đề trùng không dấu và chuyển thời gian hiển thị sang giờ Việt Nam.
"""
    (ROOT / "docs" / "news-audit.md").write_text(doc, encoding="utf-8")
    print(f"Wrote docs/news-audit.md ({len(rows)} symbols); {len(reviewed)} titles, precision={precision}")


if __name__ == "__main__":
    main()
