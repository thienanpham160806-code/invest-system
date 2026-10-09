"""Kho chi so co ban (P/E, P/B, ROE) cho vu tru thanh khoan: mot file parquet,
duoc dung boi `scripts/backfill_fundamentals.py`.

Giai quyet mot phan yeu cau con thieu cua de: bo loc va snapshot can tham
chieu duoc chi so co ban, nhung KHONG duoc goi mang trong luc nguoi dung dang
cho /loc hay /tinhieu tra loi (se tai lai van de treo bot ma PHAN 2/3 da giai
quyet cho gia). Vi ratios thay doi cham (theo quy/nam, khong theo phien), kho
nay duoc XEM LA MOI trong toi da `_DEFAULT_CACHE_DAYS` ngay (xem
config/settings.yaml: fundamentals.cache_days) - scripts/backfill_fundamentals.py
tu bo qua neu kho con moi, tranh goi mang vo ich va cham gioi han rate limit.

Ma nao KHONG co trong kho (chua backfill, hoac nguon khong tra duoc ratios)
thi cac cot pe/pb/roe la NaN khi merge vao snapshot - tuyet doi khong bia so
(xem analysis/snapshot.py, analysis/screener.py).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..config import get_paths, get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)

FUNDAMENTALS_COLUMNS = ["symbol", "pe", "pb", "roe", "updated_at"]
FUNDAMENTALS_FILENAME = "fundamentals.parquet"
_DEFAULT_CACHE_DAYS = 7

_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _market_dir() -> Path:
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fundamentals_path() -> Path:
    return _market_dir() / FUNDAMENTALS_FILENAME


def load_fundamentals() -> pd.DataFrame:
    """Doc kho chi so co ban. DataFrame RONG neu chua backfill lan nao."""
    path = fundamentals_path()
    if not path.exists():
        return pd.DataFrame(columns=FUNDAMENTALS_COLUMNS)
    mtime = path.stat().st_mtime
    key = str(path)
    hit = _cache.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    frame = pd.read_parquet(path)
    _cache[key] = (mtime, frame)
    return frame


def save_fundamentals(frame: pd.DataFrame) -> int:
    path = fundamentals_path()
    frame = frame[FUNDAMENTALS_COLUMNS].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame.to_parquet(path, index=False)
    _cache.pop(str(path), None)
    log.info("fundamentals_store: da ghi %d dong vao %s", len(frame), path)
    return len(frame)


def fundamentals_last_updated() -> datetime | None:
    path = fundamentals_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime)


def is_stale(max_age_days: int | None = None, now: datetime | None = None) -> bool:
    """True neu chua co kho, hoac kho cu hon `max_age_days` (mac dinh: doc tu
    config/settings.yaml: fundamentals.cache_days)."""
    if max_age_days is None:
        max_age_days = get_settings().get("fundamentals.cache_days", _DEFAULT_CACHE_DAYS)
    updated = fundamentals_last_updated()
    if updated is None:
        return True
    now = now or datetime.now()
    return (now - updated) > timedelta(days=max_age_days)
