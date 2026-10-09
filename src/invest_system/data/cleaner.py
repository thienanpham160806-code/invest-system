"""Lam sach du lieu gia truoc khi dua vao tinh toan.

Cac loi da gap trong thuc te va duoc xu ly o day:
  - tep CSV co BOM va xuong dong kieu CRLF
  - cot ngay o dang so nguyen YYYYMMDD
  - ban ghi trung lap theo cap (ma, ngay)
  - du lieu khong duoc sap xep theo thoi gian
  - gia bang 0 hoac am o cac phien khong giao dich
"""
from __future__ import annotations

import pandas as pd

from ..logging_conf import get_logger

log = get_logger(__name__)

REQUIRED = ["time", "open", "high", "low", "close", "volume"]


def clean_ohlcv(frame: pd.DataFrame, symbol: str | None = None) -> pd.DataFrame:
    """Chuan hoa mot khung du lieu gia. Luon tra ve ban sao moi."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=REQUIRED)

    out = frame.copy()
    out.columns = [str(c).strip().lstrip("\ufeff").lower() for c in out.columns]

    alias = {
        "<ticker>": "symbol", "ticker": "symbol",
        "<dtyyyymmdd>": "time", "dtyyyymmdd": "time", "date": "time", "tradingdate": "time",
        "<open>": "open", "<high>": "high", "<low>": "low", "<close>": "close",
        "<volume>": "volume", "vol": "volume",
    }
    out = out.rename(columns={k: v for k, v in alias.items() if k in out.columns})

    out["time"] = _parse_time(out["time"])
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if symbol is not None:
        out["symbol"] = symbol.upper()
    elif "symbol" in out.columns:
        out["symbol"] = out["symbol"].astype(str).str.strip().str.upper()

    out = out.dropna(subset=["time", "close"])
    out = out[(out["close"] > 0) & (out["volume"].fillna(0) >= 0)]

    subset = ["symbol", "time"] if "symbol" in out.columns else ["time"]
    before = len(out)
    out = out.drop_duplicates(subset=subset, keep="last")
    if before != len(out):
        log.info("Da bo %d ban ghi trung lap", before - len(out))

    out = out.sort_values(subset).reset_index(drop=True)
    return _fix_ohlc_consistency(out)


def _parse_time(series: pd.Series) -> pd.Series:
    """Nhan dang ngay o dang so nguyen YYYYMMDD, chuoi, hoac epoch."""
    if pd.api.types.is_numeric_dtype(series):
        as_int = series.astype("Int64")
        if as_int.dropna().between(19000101, 29991231).all():
            return pd.to_datetime(as_int.astype(str), format="%Y%m%d", errors="coerce")
        return pd.to_datetime(series, unit="s", errors="coerce")
    return pd.to_datetime(series, errors="coerce")


def _fix_ohlc_consistency(frame: pd.DataFrame) -> pd.DataFrame:
    """Bao dam low <= min(open, close) <= max(open, close) <= high."""
    if frame.empty:
        return frame
    out = frame.copy()
    body_low = out[["open", "close"]].min(axis=1)
    body_high = out[["open", "close"]].max(axis=1)
    out["low"] = out[["low"]].join(body_low.rename("b")).min(axis=1)
    out["high"] = out[["high"]].join(body_high.rename("b")).max(axis=1)
    return out


def flag_price_band_breach(
    frame: pd.DataFrame, band: float, tolerance: float = 0.005
) -> pd.Series:
    """Danh dau phien co bien dong vuot bien do cho phep cua san.

    Vuot bien do thuong khong phai bien dong that ma la dau hieu gia chua duoc
    dieu chinh sau chia tach hoac tra co tuc.
    """
    change = frame["close"].pct_change()
    return change.abs() > (band + tolerance)
