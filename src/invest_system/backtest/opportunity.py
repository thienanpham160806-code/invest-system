"""Chien luoc bang co hoi: chon ma, walk-forward, benchmark, IC - docs/phase2/backtest-design.md muc 6-8.

Dau vao chinh: `scores` = DataFrame (as_of, symbol, eligible, score, upside, avg_value_20d,
icb1, market_cap, score_<nhom>...) cho moi ngay tin hieu cuoi thang, do backtest/history.py
tinh (chi dung du lieu <= as_of). Moi ham o day thuan logic tren bang do + Market.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from . import ic as ic_mod
from . import metrics
from .portfolio import Costs, Market, run

SECTOR_CAP = 0.35
SCORE_GROUPS = ("valuation", "quality", "sector", "growth", "technical")
IC_HORIZONS = {1: 21, 3: 63, 6: 126}          # thang -> phien
IC_LAGS = {1: 0, 3: 2, 6: 5}                   # Newey-West: so thang chong lan


@dataclass(frozen=True)
class Config:
    top_n: int
    freq: str          # "M" | "Q"

    def label(self) -> str:
        return f"Top {self.top_n}, {'tháng' if self.freq == 'M' else 'quý'}"


GRID: tuple[Config, ...] = (Config(10, "M"), Config(10, "Q"), Config(20, "M"), Config(20, "Q"))


# ------------------------------------------------------------------ chon ma
def select(day: pd.DataFrame, n: int, sector_cap: float = SECTOR_CAP,
           exclude: frozenset[str] = frozenset()) -> list[str]:
    """Top n theo (diem, upside, GTGD) trong cac ma du dieu kien /co-hoi; moi nganh ICB1 <= sector_cap."""
    pool = day[day["eligible"].fillna(False).astype(bool) & ~day["symbol"].isin(exclude)]
    pool = pool.sort_values(["score", "upside", "avg_value_20d"], ascending=False, kind="stable")
    per_sector = max(1, math.floor(sector_cap * n))
    picked, count = [], Counter()
    for row in pool.itertuples():
        if count[row.icb1] >= per_sector:
            continue
        picked.append(row.symbol)
        count[row.icb1] += 1
        if len(picked) == n:
            break
    return picked


def _rebalance_dates(scores: pd.DataFrame, freq: str) -> list[pd.Timestamp]:
    dates = sorted(pd.to_datetime(scores["as_of"].unique()))
    return dates if freq == "M" else [d for d in dates if d.month in (3, 6, 9, 12)]


def strategy_targets(scores: pd.DataFrame, cfg: Config,
                     exclude: frozenset[str] = frozenset()) -> dict[pd.Timestamp, dict[str, float]]:
    """{ngay tin hieu: {ma: 1/N}} - it hon N ma thi phan con lai la tien mat."""
    by_date = dict(tuple(scores.groupby("as_of")))
    return {d: {s: 1.0 / cfg.top_n for s in select(by_date[d], cfg.top_n, exclude=exclude)}
            for d in _rebalance_dates(scores, cfg.freq)}


def equal_weight_targets(scores: pd.DataFrame, freq: str = "M") -> dict[pd.Timestamp, dict[str, float]]:
    """Benchmark: can bang moi ma trong universe du dieu kien muc 4 (moi ma da cham diem)."""
    out = {}
    for d, day in scores.groupby("as_of"):
        if pd.Timestamp(d) in set(_rebalance_dates(scores, freq)):
            names = day["symbol"].tolist()
            out[pd.Timestamp(d)] = {s: 1.0 / len(names) for s in names} if names else {}
    return out


def market_cap_targets(scores: pd.DataFrame, n: int, freq: str = "M") -> dict[pd.Timestamp, dict[str, float]]:
    """Benchmark: top n von hoa trong universe du dieu kien muc 4, ty trong bang nhau."""
    out = {}
    for d, day in scores.groupby("as_of"):
        if pd.Timestamp(d) in set(_rebalance_dates(scores, freq)):
            names = day.nlargest(n, "market_cap")["symbol"].tolist()
            out[pd.Timestamp(d)] = {s: 1.0 / n for s in names}
    return out


# ------------------------------------------------------------------ chi so
def summary(equity: pd.Series, benchmark: pd.Series | None = None, turnover: float | None = None) -> dict:
    if equity.empty or len(equity) < 2:
        return {}
    returns = equity.pct_change().dropna()
    moments = metrics.sharpe_moments(returns)
    out = {
        "Lợi suất tích luỹ": metrics.total_return(equity),
        "CAGR": metrics.cagr(equity),
        "Sharpe": metrics.sharpe(returns),
        "Sụt giảm tối đa": metrics.max_drawdown(equity),
        "Tỷ lệ tháng dương": metrics.monthly_win_rate(equity),
        "PSR(0)": metrics.probabilistic_sharpe(moments["sr"], moments["n_obs"], moments["skew"], moments["kurtosis"]),
        "Số phiên": len(equity),
    }
    if benchmark is not None:
        out["Tỷ lệ tháng thắng VN-Index"] = metrics.monthly_win_rate(equity, benchmark)
    if turnover is not None:
        out["Vòng quay (lần/năm)"] = turnover
    return out


def index_equity(vnindex: pd.DataFrame, start, end, capital: float) -> pd.Series:
    s = vnindex.set_index("time")["close"].astype(float)
    s = s[(s.index >= pd.Timestamp(start)) & (s.index < pd.Timestamp(end))]
    return s / s.iloc[0] * capital if not s.empty else s


# ------------------------------------------------------------------ walk-forward
@dataclass
class WalkForward:
    equity: pd.Series
    slices: pd.DataFrame
    trials: pd.DataFrame
    trades: pd.DataFrame
    chosen: list[tuple[pd.Timestamp, pd.Timestamp, Config]]

    def sharpe_report(self, n_trials: int = len(GRID)) -> dict:
        returns = self.equity.pct_change().dropna()
        m = metrics.sharpe_moments(returns)
        var = 0.0
        if "train_sharpe" in self.trials and len(self.trials):   # do nhay (fixed) khong co lan thu
            per_day = self.trials["train_sharpe"] / np.sqrt(metrics.TRADING_DAYS)
            var = float(per_day.groupby(self.trials["train_start"]).var(ddof=1).mean())
        return {**m, "psr": metrics.probabilistic_sharpe(m["sr"], m["n_obs"], m["skew"], m["kurtosis"]),
                "dsr": metrics.deflated_sharpe(m["sr"], n_trials, m["n_obs"], var, m["skew"], m["kurtosis"]),
                "n_trials": n_trials, "sr_variance": var}

    def turnover(self) -> float:
        if self.trades.empty or len(self.equity) < 2:
            return 0.0
        return float(self.trades["value"].sum() / 2 / self.equity.mean() / (len(self.equity) / 252))


def windows(start, end, train_months: int = 24, test_months: int = 6) -> list[tuple]:
    out, train_start = [], pd.Timestamp(start)
    end = pd.Timestamp(end)
    while True:
        train_end = train_start + pd.DateOffset(months=train_months)
        test_end = min(train_end + pd.DateOffset(months=test_months), end)
        if train_end >= end or (test_end - train_end).days < 20:
            break
        out.append((train_start, train_end, test_end))
        train_start = train_start + pd.DateOffset(months=test_months)
    return out


def walk_forward(market: Market, scores: pd.DataFrame, start, end, capital: float = 1e9,
                 costs: Costs | None = None, delay: int = 1, grid: tuple[Config, ...] = GRID,
                 exclude: frozenset[str] = frozenset(),
                 fixed: list[tuple[pd.Timestamp, pd.Timestamp, Config]] | None = None,
                 train_months: int = 24, test_months: int = 6) -> WalkForward:
    """Chon cau hinh theo Sharpe tren cua so train, ap nguyen len cua so test ke tiep.

    `fixed`: danh sach (test_start, test_end, cau hinh) da chon - dung cho do nhay
    (khong chon lai). Von dau moi lat test = von cuoi lat truoc; cuoi lat dong vi the.
    """
    costs = costs or Costs.from_settings()
    targets = {cfg: strategy_targets(scores, cfg, exclude) for cfg in grid}
    pieces, trade_frames, slice_rows, trial_rows, chosen = [], [], [], [], []
    plan = ([(None, a, b, cfg) for a, b, cfg in fixed] if fixed is not None
            else [(tr, te, tend, None) for tr, te, tend in windows(start, end, train_months, test_months)])
    for train_start, test_start, test_end, cfg in plan:
        best_sharpe = None
        if cfg is None:
            best = None
            for trial in grid:
                res = run(market, targets[trial], capital=capital, costs=costs, delay=delay,
                          start=train_start, end=test_start, liquidate_at_end=True)
                sharpe = metrics.sharpe(res.equity.pct_change().dropna()) if len(res.equity) > 1 else 0.0
                trial_rows.append({"train_start": train_start, "train_end": test_start, **asdict(trial),
                                   "train_sharpe": sharpe, "train_return": metrics.total_return(res.equity)})
                if best is None or sharpe > best_sharpe:
                    best, best_sharpe = trial, sharpe
            cfg = best
        if cfg not in targets:
            targets[cfg] = strategy_targets(scores, cfg, exclude)
        res = run(market, targets[cfg], capital=capital, costs=costs, delay=delay,
                  start=test_start, end=test_end, liquidate_at_end=True)
        if not res.equity.empty:
            pieces.append(res.equity)
            capital = float(res.equity.iloc[-1])
        trade_frames.append(res.trades)
        chosen.append((test_start, test_end, cfg))
        slice_rows.append({"train_start": train_start, "test_start": test_start, "test_end": test_end,
                           "cấu hình": cfg.label(), "top_n": cfg.top_n, "freq": cfg.freq,
                           "Sharpe train": best_sharpe, **summary(res.equity, turnover=res.turnover())})
    equity = pd.concat(pieces) if pieces else pd.Series(dtype=float)
    trades = pd.concat([t for t in trade_frames if not t.empty], ignore_index=True) if trade_frames else pd.DataFrame()
    return WalkForward(equity, pd.DataFrame(slice_rows), pd.DataFrame(trial_rows), trades, chosen)


# ------------------------------------------------------------------ IC
def forward_returns(market: Market, scores: pd.DataFrame, delay: int = 1) -> pd.DataFrame:
    """Loi suat mo cua t+delay -> mo cua t+delay+h phien cho moi (as_of, symbol)."""
    cal = market.calendar
    opens = market.open
    out = scores[["as_of", "symbol"]].copy()
    idx = cal.get_indexer(pd.to_datetime(out["as_of"]))
    cols = opens.columns.get_indexer(out["symbol"])
    arr = opens.to_numpy(float)
    for months, sessions in IC_HORIZONS.items():
        entry_i, exit_i = idx + delay, idx + delay + sessions
        ok = (idx >= 0) & (cols >= 0) & (exit_i < len(cal))
        values = np.full(len(out), np.nan)
        entry = arr[np.where(ok, entry_i, 0), np.where(ok, cols, 0)]
        exit_ = arr[np.where(ok, exit_i, 0), np.where(ok, cols, 0)]
        values[ok] = (exit_ / entry - 1)[ok]
        out[f"fwd_{months}m"] = values
    return out


def ic_table(market: Market, scores: pd.DataFrame, min_names: int = ic_mod.MIN_CROSS_SECTION) -> pd.DataFrame:
    """IC Spearman theo thang cho diem tong hop va tung nhom, moi ky han; t-stat Newey-West."""
    panel = scores.merge(forward_returns(market, scores), on=["as_of", "symbol"]).rename(columns={"as_of": "time"})
    factors = ["score"] + [f"score_{g}" for g in SCORE_GROUPS if f"score_{g}" in panel.columns]
    rows = []
    for factor in factors:
        for months in IC_HORIZONS:
            series = ic_mod.daily_rank_ic(panel, factor, f"fwd_{months}m", min_names=min_names)
            stats = ic_mod.summarise_ic(series, IC_LAGS[months]) if not series.empty else {}
            rows.append({"nhóm": factor.removeprefix("score_") if factor != "score" else "tổng hợp",
                         "kỳ hạn (tháng)": months, **stats})
    return pd.DataFrame(rows)


def top_return_symbols(market: Market, symbols: set[str], start, end, share: float = 0.10) -> frozenset[str]:
    """`share` ma co tong loi suat cao nhat trong [start, end) - cho do nhay 'bo ma trung lon'."""
    close = market.close[[s for s in symbols if s in market.close.columns]]
    close = close[(close.index >= pd.Timestamp(start)) & (close.index < pd.Timestamp(end))]
    total = close.apply(lambda c: c.dropna().iloc[-1] / c.dropna().iloc[0] - 1 if c.notna().sum() > 1 else np.nan)
    total = total.dropna().sort_values(ascending=False)
    k = int(math.ceil(len(total) * share))
    return frozenset(total.index[:k])
