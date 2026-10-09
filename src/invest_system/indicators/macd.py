"""MACD (Moving Average Convergence Divergence).

Cong thuc (n = so phien):
    EMA_n(t) = alpha*P(t) + (1-alpha)*EMA_n(t-1),   alpha = 2/(n+1)
    MACD     = EMA_12 - EMA_26
    Signal   = EMA_9(MACD)
    Hist     = MACD - Signal

Quy uoc dien giai dung trong analysis/scoring.py:
  - Giao cat TREN duong 0 manh hon giao cat DUOI duong 0 (xu huong tang đa
    duoc xac nhan bang gia tri MACD duong).
  - Histogram thu hep dan du CHUA cat la dau hieu dong luc suy yeu som hon
    tin hieu giao cat.
"""
from __future__ import annotations

import pandas as pd

from .common import detect_cross, ema, slope


def macd(frame: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Tra ve DataFrame[macd, signal, hist] cung do dai voi `frame`."""
    close = frame["close"]
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig}, index=frame.index)


def macd_state(frame: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """Tom tat trang thai MACD tai phien cuoi cua `frame`.

    Tra ve dict:
      cross          "golden" / "death" / None
      bars_since_cross  so phien tu lan giao cat gan nhat (0 = vua cat)
      hist_slope     do doc histogram 3 phien gan nhat (hoi quy bac 1)
      above_zero     True neu duong MACD dang nam tren muc 0
    """
    lines = macd(frame, fast, slow, signal)
    cross, bars_since = detect_cross(lines["macd"], lines["signal"])
    last_macd = lines["macd"].dropna()
    return {
        "cross": cross,
        "bars_since_cross": bars_since,
        "hist_slope": slope(lines["hist"], bars=3),
        "above_zero": bool(last_macd.iloc[-1] > 0) if not last_macd.empty else None,
    }
