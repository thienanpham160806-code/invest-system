"""Dung vu tru co phieu du dieu kien - tinh HOAN TOAN bang pandas tren kho.

Truoc day ham nay goi router.ohlcv() cho TUNG MA cua ca san (hang tram
request mang, la nguyen nhan chinh khien /loc treo bot). Gio doc mot lan tu
data/market_store.py (kho toan san tren dia, xem scripts/backfill_data.py)
roi loc bang groupby/pandas - KHONG goi mang.

Quan trong cho backtest: vu tru phai duoc dung lai theo dung danh sach cua ngay
do, khong duoc dung danh sach hom nay cho qua khu (thien lech song sot).
liquid_universe(as_of) chi dung du lieu <= as_of, va chi giu ma CON giao
dich tai as_of (phien cuoi khong cu hon _MAX_STALE_DAYS ngay so voi phien moi
nhat cua thi truong <= as_of) - ma da ngung giao dich/huy niem yet khong lot
vao vu tru chi vi 20 phien cuoi cua no dep.

Gioi han con lai (khong sua duoc bang du lieu hien co): san cua ma lay theo
danh sach HOM NAY (ma chuyen san giua chung bi xep theo san hien tai), va ma
da huy niem yet tu truoc khi dung kho se khong co trong kho.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ..config import get_settings, get_universe_config
from ..logging_conf import get_logger
from . import market_store
from .router import get_router

log = get_logger(__name__)

# Ma co phien cuoi cu hon chung nay ngay so voi as_of coi nhu da ngung giao
# dich (dai hon ky nghi Tet dai nhat ~9-10 ngay).
_MAX_STALE_DAYS = 14


def liquid_universe(
    as_of: date | None = None,
    use_watchlist: bool = False,
    ohlcv: pd.DataFrame | None = None,
    min_days: int | None = None,
) -> list[str]:
    """Danh sach ma dat nguong thanh khoan va gia tai ngay as_of, tu kho toan san.

    Chi dung du lieu co time <= as_of. `ohlcv`: du lieu dang dai (symbol,
    time, close, volume) da nap san - backtest goi ham nay nhieu lan, khong
    doc lai kho. `min_days`: ghi de universe.min_listed_days (backtest ha
    xuong muc khoi dong chi bao vi kho chi giu ~750 phien gan nhat moi ma,
    khong biet ngay niem yet that).
    """
    if use_watchlist:
        return [s.upper() for s in get_universe_config()["watchlist"]]

    settings = get_settings()
    as_of = as_of or date.today()

    exchanges = settings.get("universe.exchanges", ["HOSE", "HNX", "UPCOM"])
    min_volume = settings.get("universe.min_avg_volume_20d", 100_000)
    min_price = settings.get("universe.min_price", 5_000)
    max_price = settings.get("universe.max_price", 300_000)
    if min_days is None:
        min_days = settings.get("universe.min_listed_days", 250)

    frame = (
        ohlcv[["symbol", "time", "close", "volume"]] if ohlcv is not None
        else market_store.load_ohlcv(columns=["symbol", "time", "close", "volume"])
    )
    if frame.empty:
        log.warning(
            "market_store rong - chua chay scripts/backfill_data.py? "
            "liquid_universe tra ve danh sach rong."
        )
        return []

    frame = frame[frame["time"] <= pd.Timestamp(as_of)]
    if frame.empty:
        return []
    # "Con giao dich" so voi phien moi nhat CO TRONG DU LIEU (<= as_of), khong
    # so voi as_of: kho cap nhat cham vai tuan thi bot van chay binh thuong.
    still_trading_since = frame["time"].max() - timedelta(days=_MAX_STALE_DAYS)

    symbols_meta = market_store.load_symbols()
    if not symbols_meta.empty and "exchange" in symbols_meta.columns:
        wanted = set(
            symbols_meta.loc[
                symbols_meta["exchange"].astype(str).str.upper().isin(exchanges), "symbol"
            ]
        )
        frame = frame[frame["symbol"].isin(wanted)]

    passed: list[tuple[str, float]] = []
    for symbol, group in frame.groupby("symbol", observed=True, sort=False):
        if len(group) < min_days:
            continue
        group = group.sort_values("time")
        if group["time"].iloc[-1] < still_trading_since:
            continue  # da ngung giao dich truoc as_of
        last_close = float(group["close"].iloc[-1])
        avg_volume = float(group["volume"].tail(20).mean())
        if min_price <= last_close <= max_price and avg_volume >= min_volume:
            passed.append((str(symbol), avg_volume))

    # Gioi han quy mo de vua may chu nho (vd Render goi Free 512 MB): chi giu N
    # ma thanh khoan nhat theo khoi luong TB 20 phien. 0 = khong gioi han.
    max_symbols = int(settings.get("universe.max_symbols", 0) or 0)
    if 0 < max_symbols < len(passed):
        passed.sort(key=lambda item: item[1], reverse=True)
        log.info("liquid_universe: gioi han con %d/%d ma", max_symbols, len(passed))
        passed = passed[:max_symbols]

    keep = [symbol for symbol, _ in passed]
    log.info("Vu tru du dieu kien tai %s: %d ma (tu kho, khong goi mang)", as_of, len(keep))
    return keep


def sector_of(symbols: list[str]) -> pd.Series:
    """Anh xa ma -> nganh, dung cho rang buoc ti trong nganh."""
    mapping = get_router().industry_map()
    if mapping.empty:
        return pd.Series({s: "Khac" for s in symbols})
    col = next(
        (c for c in ("industry", "icb_name3", "icb_name2") if c in mapping.columns), None
    )
    if col is None:
        return pd.Series({s: "Khac" for s in symbols})
    table = mapping.set_index(mapping["symbol"].astype(str).str.upper())[col]
    return pd.Series({s: table.get(s, "Khac") for s in symbols})
