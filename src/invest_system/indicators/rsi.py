"""RSI (Relative Strength Index) voi nguong thich ung theo phan vi lich su.

RSI 14 phien, lam muot theo phuong phap Wilder:
    gain, loss = phan tang / phan giam cua gia dong cua moi phien
    avg_gain(t) = ewm(gain, alpha=1/14)
    avg_loss(t) = ewm(loss, alpha=1/14)
    RS  = avg_gain / avg_loss
    RSI = 100 - 100/(1+RS)

KHONG dung nguong cung 30/70. Thay bang nguong thich ung theo phan vi
LICH SU CUA CHINH MA DO:
    upper(t) = phan_vi_90(RSI, 252 phien gan nhat), kep trong [65, 85]
    lower(t) = phan_vi_10(RSI, 252 phien gan nhat), kep trong [15, 35]

Ly do: trong xu huong tang manh, RSI co the nam tren 70 lien tuc nhieu tuan -
ban theo nguong cung 70 la ban mat hang tot giua xu huong. Nguong thich ung
tu dieu chinh theo "vung binh thuong" cua rieng ma do, thay vi ap mot chuan
chung cho moi co phieu bat ke bien dong manh yeu khac nhau.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import slope

UPPER_BOUNDS = (65.0, 85.0)
LOWER_BOUNDS = (15.0, 35.0)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """RSI theo phuong phap lam muot Wilder. Gia tri trong [0, 100]."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    result = 100 - 100 / (1 + rs)
    return result.fillna(100.0).where(avg_loss.notna())


def adaptive_bands(series: pd.Series, lookback: int = 252) -> pd.DataFrame:
    """Nguong tren/duoi thich ung tinh tu phan vi lich su cua chinh chuoi RSI.

    Tra ve DataFrame[upper, lower] cung do dai voi `series`.
    """
    min_periods = min(60, lookback)
    upper = series.rolling(lookback, min_periods=min_periods).quantile(0.90)
    lower = series.rolling(lookback, min_periods=min_periods).quantile(0.10)
    upper = upper.clip(lower=UPPER_BOUNDS[0], upper=UPPER_BOUNDS[1])
    lower = lower.clip(lower=LOWER_BOUNDS[0], upper=LOWER_BOUNDS[1])
    return pd.DataFrame({"upper": upper, "lower": lower})


def rsi_state(frame: pd.DataFrame, period: int = 14, lookback: int = 252) -> dict:
    """Tom tat trang thai RSI tai phien cuoi cua `frame`.

    Tra ve dict: value, zone ("qua_mua"/"trung_tinh"/"qua_ban"), upper, lower,
    slope (do doc RSI 5 phien gan nhat).
    """
    values = rsi(frame["close"], period)
    bands = adaptive_bands(values, lookback)

    last_value = values.dropna()
    if last_value.empty:
        return {"value": None, "zone": None, "upper": None, "lower": None, "slope": None}

    value = float(last_value.iloc[-1])
    upper = bands["upper"].dropna()
    lower = bands["lower"].dropna()
    upper_val = float(upper.iloc[-1]) if not upper.empty else UPPER_BOUNDS[1]
    lower_val = float(lower.iloc[-1]) if not lower.empty else LOWER_BOUNDS[0]

    if value > upper_val:
        zone = "qua_mua"
    elif value < lower_val:
        zone = "qua_ban"
    else:
        zone = "trung_tinh"

    return {
        "value": value,
        "zone": zone,
        "upper": upper_val,
        "lower": lower_val,
        "slope": slope(values, bars=5),
    }
