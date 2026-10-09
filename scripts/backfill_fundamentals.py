"""Nap chi so co ban (P/E, P/B, ROE) cho vu tru thanh khoan vao kho mot file
(data/fundamentals_store.py) - dung cho bo loc/snapshot doc them dieu kien
co ban (xem analysis/screener.py, analysis/snapshot.py).

Mac dinh BO QUA neu kho con moi (xem config/settings.yaml:
fundamentals.cache_days, mac dinh 7 ngay) - ratios thay doi cham theo quy/nam
nen khong can goi mang lai moi lan chay. Dung --force de ep tai lai.

Nguon: DataRouter.ratios() -> FundamentalProvider.ratios() (hien la Vietcap
qua vnstock, xem data/vietcap.py). Nguon nay co gioi han rate limit (~20
request/phut o goi Guest) nen script CHU Y GIAN CACH giua cac ma (xem
config/settings.yaml: fundamentals.request_delay_seconds).

Ma nao khong lay duoc ratios (loi mang, chua niem yet du, nguon khong co so
lieu) se BI BO QUA - khong bia so, cot pe/pb/roe cua ma do se la NaN khi loc.

Cach chay:
    python scripts/backfill_fundamentals.py            # bo qua neu kho con moi
    python scripts/backfill_fundamentals.py --force     # ep tai lai toan bo
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from invest_system.analysis.lookup import _RATIO_COLUMN_MAP, _extract  # noqa: E402
from invest_system.config import get_settings  # noqa: E402
from invest_system.data import fundamentals_store  # noqa: E402
from invest_system.data.router import get_router  # noqa: E402
from invest_system.data.universe import liquid_universe  # noqa: E402
from invest_system.logging_conf import get_logger, setup_logging  # noqa: E402

log = get_logger("backfill_fundamentals")

_DEFAULT_DELAY_SECONDS = 3.0


def _fetch_one(symbol: str) -> dict | None:
    ratios = get_router().ratios(symbol, period="year")
    if ratios.empty:
        return None
    row = ratios.iloc[-1]
    pe = _extract(row, _RATIO_COLUMN_MAP["pe"])
    pb = _extract(row, _RATIO_COLUMN_MAP["pb"])
    roe = _extract(row, _RATIO_COLUMN_MAP["roe"])
    if pe is None and pb is None and roe is None:
        return None
    return {"symbol": symbol, "pe": pe, "pb": pb, "roe": roe}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true", help="Ep tai lai du kho con moi (bo qua cache_days)"
    )
    args = parser.parse_args()

    setup_logging()
    settings = get_settings()

    if not args.force and not fundamentals_store.is_stale():
        updated = fundamentals_store.fundamentals_last_updated()
        print(f"Kho fundamentals con moi (cap nhat {updated}), bo qua. Dung --force de ep tai lai.")
        return

    symbols = liquid_universe()
    if not symbols:
        print("Vu tru thanh khoan rong - chay scripts/backfill_data.py truoc.")
        return

    delay = settings.get("fundamentals.request_delay_seconds", _DEFAULT_DELAY_SECONDS)
    log.info("Nap ratios cho %d ma, gian cach %.1fs/ma...", len(symbols), delay)

    started = time.time()
    rows: list[dict] = []
    for i, symbol in enumerate(symbols, start=1):
        try:
            row = _fetch_one(symbol)
            if row is not None:
                rows.append(row)
        except Exception as exc:  # noqa: BLE001 - bo qua ma nay, khong lam hong ca lot
            log.warning("backfill_fundamentals: bo qua %s do loi: %s", symbol, exc)
        if i % 50 == 0 or i == len(symbols):
            log.info("backfill_fundamentals: %d/%d ma (%d co du lieu)", i, len(symbols), len(rows))
        if i < len(symbols):
            time.sleep(delay)

    if not rows:
        print("Khong lay duoc ratios cho ma nao - kiem tra ket noi mang / nguon du lieu.")
        return

    import pandas as pd

    frame = pd.DataFrame(rows)
    frame["updated_at"] = pd.Timestamp.now()
    total = fundamentals_store.save_fundamentals(frame)

    elapsed = time.time() - started
    log.info("Hoan tat trong %.1fs: %d/%d ma co ratios", elapsed, total, len(symbols))
    print(
        f"\nXong: {total}/{len(symbols)} ma co du lieu P/E, P/B, ROE, {elapsed:.1f}s. "
        f"Kho: {fundamentals_store.fundamentals_path()}"
    )


if __name__ == "__main__":
    main()
