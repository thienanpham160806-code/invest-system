"""Information Coefficient - port nguyen tu Kumo_VN_bot/src/bot_phan_tich/backtest/ic.py.

Information Coefficient: diem so cua chi bao co XEP HANG DUNG loi suat
tuong lai giua cac ma khong?

IC phien t = tuong quan hang Spearman, tren MAT CAT cac ma trong vu tru phien
t, giua diem so tai t va loi suat tu gia mo cua t+1 den gia mo cua t+1+h.
Mua o gia mo cua t+1 la som nhat co the sau khi biet diem cuoi phien t, nen
khong co nhin truoc.

Voi h > 1 cac cua so loi suat chong lan nhau (IC ngay t va t+1 dung chung h-1
phien) -> chuoi IC tu tuong quan, t-stat thuong (mean / (std/sqrt(N))) bi
phong dai. Bao cao them t-stat Newey-West voi do tre = h.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_CROSS_SECTION = 20


def forward_open_returns(frame: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Loi suat open[t+1+h] / open[t+1] - 1 cho moi phien t cua MOT ma (theo
    vi tri phien cua chinh ma do). NaN o h+1 phien cuoi."""
    open_ = frame["open"].astype(float).reset_index(drop=True)
    entry = open_.shift(-1)
    return pd.DataFrame(
        {f"fwd_{h}": open_.shift(-(1 + h)) / entry - 1 for h in horizons}
    )


def daily_rank_ic(
    panel: pd.DataFrame, factor: str, target: str, min_names: int = MIN_CROSS_SECTION
) -> pd.Series:
    """IC Spearman theo tung phien. `panel`: dang dai co cot time, factor, target.

    Spearman = Pearson tren hang (hang trung binh khi hoa). Phien co it hon
    `min_names` ma hop le bi bo qua.
    """
    data = panel.loc[panel[factor].notna() & panel[target].notna(), ["time", factor, target]]
    if data.empty:
        return pd.Series(dtype=float, name=factor)
    grouped = data.groupby("time")
    x = grouped[factor].rank()
    y = grouped[target].rank()
    x = x - x.groupby(data["time"]).transform("mean")
    y = y - y.groupby(data["time"]).transform("mean")
    frame = pd.DataFrame({"time": data["time"], "xy": x * y, "xx": x * x, "yy": y * y})
    sums = frame.groupby("time")[["xy", "xx", "yy"]].sum()
    counts = data.groupby("time").size()
    denom = np.sqrt(sums["xx"] * sums["yy"])
    ic = (sums["xy"] / denom.replace(0.0, np.nan)).where(counts >= min_names)
    return ic.dropna().rename(factor)


def newey_west_tstat(series: pd.Series, lags: int) -> float:
    """t-stat cua trung binh voi sai so chuan Newey-West (trong so Bartlett).

        Var(mean) = (g0 + 2 * sum_{l=1..L} (1 - l/(L+1)) * g_l) / N
    g_l = tu hiep phuong sai bac l (chia N). lags = 0 -> t-stat thuong (ddof=0).
    """
    values = pd.Series(series, dtype=float).dropna().to_numpy()
    n = len(values)
    if n < 2:
        return float("nan")
    centered = values - values.mean()
    long_run = centered @ centered / n
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        long_run += 2.0 * weight * (centered[lag:] @ centered[:-lag]) / n
    if long_run <= 0:
        return float("nan")
    return float(values.mean() / np.sqrt(long_run / n))


def summarise_ic(ic: pd.Series, horizon: int) -> dict:
    """IC trung binh, do lech chuan, ICIR, t-stat (thuong va Newey-West), ti
    le thang co IC trung binh > 0."""
    ic = ic.dropna()
    if ic.empty:
        return {}
    mean, std = float(ic.mean()), float(ic.std(ddof=1))
    monthly = ic.groupby(pd.DatetimeIndex(ic.index).to_period("M")).mean()
    return {
        "IC trung binh": mean,
        "Do lech chuan IC": std,
        "ICIR": mean / std if std else float("nan"),
        "t-stat": mean / std * np.sqrt(len(ic)) if std else float("nan"),
        "t-stat Newey-West": newey_west_tstat(ic, lags=horizon),
        "Ti le thang IC>0": float((monthly > 0).mean()),
        "So phien": len(ic),
        "So thang": len(monthly),
    }
