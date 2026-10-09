"""Xuat bao cao phan tich tu dong ra PDF tu dong lenh.

Vi du:
    python cli.py --ticker FPT
    python cli.py --ticker VCB --sections macro,sector,valuation --years 5
    python cli.py --ticker HPG,VCB,VHM --template summary
    python cli.py --ticker DEMO            # chay thu offline bang du lieu gia lap
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from invest_system.logging_conf import setup_logging  # noqa: E402
from invest_system.pipeline import ALL_SECTIONS, run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Hệ thống phân tích cơ hội đầu tư cổ phiếu → PDF")
    ap.add_argument("--ticker", "-t", required=True, help="Mã cổ phiếu, nhiều mã cách nhau dấu phẩy")
    ap.add_argument("--sections", "-s", default=",".join(ALL_SECTIONS),
                    help=f"Các mục cần xuất: {','.join(ALL_SECTIONS)}")
    ap.add_argument("--years", "-y", type=int, default=5, help="Số năm BCTC (mặc định 5)")
    ap.add_argument("--template", choices=["full", "summary"], default="full")
    ap.add_argument("--engine", choices=["auto", "weasyprint", "playwright", "html"], default=None)
    ap.add_argument("--out", "-o", default=None, help="Thư mục xuất (mặc định outputs/reports)")
    args = ap.parse_args()
    setup_logging()

    sections = [x.strip() for x in args.sections.split(",") if x.strip()]
    status = 0
    for ticker in [t.strip().upper() for t in args.ticker.split(",") if t.strip()]:
        try:
            path, ctx = run(ticker, sections, args.years, args.template, args.out, args.engine)
            res, val = ctx["composite"], ctx["valuation"]
            print(f"✔ {ticker}: {res.rating or 'N/A'} | giá {val.price} → mục tiêu {val.target_price} "
                  f"| điểm {res.total if res.total is None else round(res.total)} "
                  f"| dữ liệu {ctx['checks_summary']['passed']}/{ctx['checks_summary']['total']} đạt"
                  f"\n  → {path}")
        except Exception as exc:  # noqa: BLE001
            status = 1
            print(f"✘ {ticker}: {exc}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
