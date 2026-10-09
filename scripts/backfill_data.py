"""Nap gia TOAN SAN vao kho mot file (data/market_store.py).

Mac dinh tai TOAN BO co phieu HOSE/HNX/UPCOM (khong con can co --full-universe
nhu truoc). Dung `--watchlist-only` khi dang phat trien, muon chay nhanh voi
vai ma trong config/universe.yaml.

Lan dau (chua co kho): tai `market_store.count_back_bootstrap` phien (mac
dinh 500, ~2 nam; ghi de bang bien MARKET_COUNT_BACK) cho MOI ma.
Cac lan sau (da co kho): CHI tai `market_store.count_back_refresh` phien
(mac dinh 10, du bu vai phien nghi/loi mang) roi gop vao kho cu, khu trung
theo (symbol, time) - nhanh hon nhieu vi khong phai tai lai het lich su.

Nguon: endpoint cong khai cua bang gia Vietcap (data/vietcap.py:
fetch_all_symbols/fetch_ohlcv_bulk), khong can API key.

Cach chay:
    python scripts/backfill_data.py                  # toan san, tang dan neu da co kho
    python scripts/backfill_data.py --full            # ep tai lai tu dau
    python scripts/backfill_data.py --watchlist-only  # chi 12 ma trong universe.yaml, phat trien
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from invest_system.config import get_settings, get_universe_config  # noqa: E402
from invest_system.data import market_store  # noqa: E402
from invest_system.data.vietcap import fetch_all_symbols, fetch_ohlcv_bulk  # noqa: E402
from invest_system.logging_conf import get_logger, setup_logging  # noqa: E402

log = get_logger("backfill")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Ep tai lai tu dau (bo qua kho cu)")
    parser.add_argument(
        "--watchlist-only", action="store_true",
        help="Chi tai vai ma trong config/universe.yaml (phat trien, chay nhanh)",
    )
    args = parser.parse_args()

    setup_logging()
    settings = get_settings()
    started = time.time()

    if args.watchlist_only:
        config = get_universe_config()
        symbols = [s.upper() for s in config["watchlist"]]
        exchanges_frame = None
        log.info("Che do watchlist-only: %d ma", len(symbols))
    else:
        exchanges = settings.get("universe.exchanges", ["HOSE", "HNX", "UPCOM"])
        log.info("Lay danh sach ma toan san (%s)...", ", ".join(exchanges))
        exchanges_frame = fetch_all_symbols(exchanges)
        symbols = exchanges_frame["symbol"].tolist()
        market_store.save_symbols(exchanges_frame)
        log.info("Da luu danh sach %d ma vao %s", len(exchanges_frame), market_store.symbols_path())

    existing = market_store.last_updated()
    is_first_run = args.full or existing is None
    count_back = int(
        settings.get("market_store.count_back_bootstrap", 500)
        if is_first_run
        else settings.get("market_store.count_back_refresh", 10)
    )
    log.info(
        "%s: countBack=%d cho %d ma",
        "Tai lan dau" if is_first_run else "Cap nhat tang dan", count_back, len(symbols),
    )

    frame = fetch_ohlcv_bulk(symbols, count_back=count_back)
    fetched_symbols = frame["symbol"].nunique() if not frame.empty else 0
    failed = len(symbols) - fetched_symbols

    total_rows = market_store.save_ohlcv(frame, merge=not is_first_run)

    elapsed = time.time() - started
    log.info(
        "Hoan tat trong %.1fs: %d/%d ma co du lieu (%d that bai), kho hien co %d dong",
        elapsed, fetched_symbols, len(symbols), failed, total_rows,
    )
    print(
        f"\nXong: {fetched_symbols}/{len(symbols)} ma, {total_rows:,} dong trong kho, "
        f"{elapsed:.1f}s. Kho: {market_store.ohlcv_path()}"
    )


if __name__ == "__main__":
    main()
