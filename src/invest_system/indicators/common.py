"""Tien ich chung dung lai o nhieu chi bao: SMA, EMA, ATR, ti le khoi luong.

Giai quyet van de: MACD, RSI va Ichimoku deu can EMA/ATR lam nen, va ca ba deu
can phat hien giao cat giua hai duong (MACD/Signal, Tenkan/Kijun). Dat chung
mot cho de khong lap lai cong thuc o ba file rieng.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """Trung binh truot don gian: SMA_n(t) = mean(P(t-n+1..t))."""
    return series.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Trung binh truot mu: EMA_n(t) = alpha*P(t) + (1-alpha)*EMA_n(t-1), alpha = 2/(n+1)."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    """TR(t) = max(High-Low, |High-Close(t-1)|, |Low-Close(t-1)|)."""
    prev_close = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR lam muot theo Wilder: ATR(t) = ewm(TR, alpha=1/period)."""
    return true_range(frame).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def volume_ratio(frame: pd.DataFrame, period: int = 20) -> pd.Series:
    """Khoi luong phien hien tai so voi trung binh `period` phien gan nhat."""
    return frame["volume"] / frame["volume"].rolling(period, min_periods=period).mean()


def slope(series: pd.Series, bars: int = 3) -> float | None:
    """Do doc tuyen tinh cua `bars` phien gan nhat (hoi quy bac 1, buoc = 1 phien).

    Dung cho hist_slope (MACD) va slope (RSI). Tra None neu khong du du lieu.
    """
    window = series.dropna().tail(bars)
    if len(window) < bars:
        return None
    x = np.arange(len(window), dtype=float)
    return float(np.polyfit(x, window.to_numpy(dtype=float), 1)[0])


def detect_cross(fast: pd.Series, slow: pd.Series) -> tuple[str | None, int | None]:
    """Tim lan giao cat gan nhat giua hai duong (fast so voi slow).

    Tra ve (huong, so_phien_tu_luc_cat):
      huong = "golden" neu fast cat LEN tren slow, "death" neu cat XUONG duoi.
      so_phien_tu_luc_cat = 0 nghia la vua cat ngay phien cuoi.
    Tra (None, None) neu khong tim thay lan cat nao trong chuoi con hop le.
    """
    diff = (fast - slow).dropna()
    if len(diff) < 2:
        return None, None
    sign = np.sign(diff.to_numpy())
    change_idx = np.where(np.diff(sign) != 0)[0]
    if len(change_idx) == 0:
        return None, None
    last_change = change_idx[-1]  # vi tri NGAY TRUOC luc cat
    direction = "golden" if sign[last_change + 1] > 0 else "death"
    bars_since = len(sign) - 1 - (last_change + 1)
    return direction, int(bars_since)
