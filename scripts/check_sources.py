"""Kiem tra nhanh nguon du lieu nao chay duoc TREN MAY NAY (chay truoc khi demo).

    python scripts/check_sources.py FPT
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _try(label, fn):
    t = time.time()
    try:
        detail = fn()
        print(f"  [OK ] {label:42s} {detail}  ({time.time()-t:.1f}s)")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"  [LỖI] {label:42s} {str(exc)[:110]}")


def main(sym: str) -> None:
    from invest_system.data import prices
    from invest_system.data.fundamentals import from_router, from_vnfinancialdata
    from invest_system.data.macro import fetch_world_bank
    from invest_system.data.vietcap import vnstock_available

    print(f"Kiểm tra nguồn dữ liệu cho {sym}:")
    print(f"  vnstock đã cài: {'có' if vnstock_available() else 'KHÔNG (BCTC/ngành/tin công bố sẽ thiếu)'}")
    _try("Giá – Vietcap public API", lambda: f"{len(prices._public_ohlcv(sym, 60))} phiên")
    _try("Giá – VN-Index (public API)", lambda: f"{len(prices._public_ohlcv('VNINDEX', 60))} phiên")
    _try("Giá – data router (kho/DNSE/vnstock)", lambda: f"{len(prices.get_ohlcv(sym, 60))} phiên")
    _try("BCTC – vnstock (Vietcap/VCI)", lambda: (lambda f: f"{f.years} | {len(f.mapping)} chỉ tiêu"
                                                  if f else "không có")(from_router(sym)))
    _try("BCTC – vnfinancialdata (HF)", lambda: (lambda f: f"{f.years} | {len(f.mapping)} chỉ tiêu"
                                                 if f else "không có (cần `hf auth login`?)")(from_vnfinancialdata(sym)))
    _try("Vĩ mô – World Bank API", lambda: f"GDP đến năm {int(fetch_world_bank('NY.GDP.MKTP.KD.ZG').index.max())}")

    def rss():
        from invest_system.data.macro_news import fetch_all_macro_news
        return f"{len(fetch_all_macro_news())} tin"
    _try("Tin tức – RSS CafeF/VnExpress", rss)


if __name__ == "__main__":
    main((sys.argv[1] if len(sys.argv) > 1 else "FPT").upper())
