"""Chi so hieu nang - port nguyen tu Kumo_VN_bot/src/bot_phan_tich/backtest/metrics.py.

Them: monthly_returns, monthly_win_rate. Moi con so deu da tru phi va thue.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def total_return(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS) -> float:
    if len(equity) < 2:
        return 0.0
    years = len(equity) / periods_per_year
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0


def max_drawdown(equity: pd.Series) -> float:
    """Muc giam sau nhat tu dinh duong von. Quan trong hon loi nhuan:
    no quyet dinh nguoi dung co du suc giu chien luoc hay khong."""
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float((equity / peak - 1).min())


def sharpe(
    returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    if returns.empty or returns.std(ddof=0) == 0:
        return 0.0
    excess = returns - risk_free / periods_per_year
    return float(excess.mean() / excess.std(ddof=0) * np.sqrt(periods_per_year))


def sortino(
    returns: pd.Series, risk_free: float = 0.0, periods_per_year: int = TRADING_DAYS
) -> float:
    """Nhu Sharpe nhung mau so chi tinh bien dong GIAM: downside deviation =
    sqrt(mean(min(r - rf, 0)^2)) tren MOI ky (ky tang dong gop 0)."""
    if returns.empty:
        return 0.0
    excess = returns - risk_free / periods_per_year
    downside = np.sqrt((np.minimum(excess, 0.0) ** 2).mean())
    if downside == 0:
        return 0.0
    return float(excess.mean() / downside * np.sqrt(periods_per_year))


def turnover(trades: pd.DataFrame, equity: pd.Series,
             periods_per_year: int = TRADING_DAYS) -> float:
    """Vong quay mot chieu theo nam: (tong gia tri mua + tong gia tri ban) / 2,
    chia von binh quan, chia so nam. 5.0 = moi nam giao dich luong hang gap 5
    lan von."""
    needed = {"entry", "exit", "shares"}
    if trades.empty or not needed.issubset(trades.columns) or len(equity) < 2:
        return 0.0
    traded = (trades["entry"] * trades["shares"]).sum() + (trades["exit"] * trades["shares"]).sum()
    years = len(equity) / periods_per_year
    return float(traded / 2 / equity.mean() / years)


_EULER_GAMMA = 0.5772156649015329


def sharpe_moments(returns: pd.Series) -> dict:
    """Sharpe THEO KY (khong nhan sqrt(252)) va cac mo-men dung cho PSR/DSR.

    sr = mean / std (ddof=1); skew = do lech; kurtosis = do nhon KHONG tru 3
    (phan phoi chuan = 3), dung quy uoc cua Bailey & Lopez de Prado (2014).
    """
    from scipy import stats  # type: ignore

    values = pd.Series(returns, dtype=float).dropna().to_numpy()
    n_obs = len(values)
    std = values.std(ddof=1) if n_obs > 1 else 0.0
    if n_obs < 3 or std == 0:
        return {"sr": 0.0, "n_obs": n_obs, "skew": 0.0, "kurtosis": 3.0}
    return {
        "sr": float(values.mean() / std),
        "n_obs": n_obs,
        "skew": float(stats.skew(values)),
        "kurtosis": float(stats.kurtosis(values, fisher=False)),
    }


def probabilistic_sharpe(
    sr: float, n_obs: int, skew: float = 0.0, kurtosis: float = 3.0, sr_benchmark: float = 0.0
) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado, 2012/2014).

        PSR(SR*) = Phi( (SR - SR*) * sqrt(T - 1) / sqrt(1 - g3*SR + (g4 - 1)/4 * SR^2) )

    SR, SR* la Sharpe THEO KY (vd theo ngay, khong annualize), T = so quan
    sat, g3 = skewness, g4 = kurtosis (khong tru 3). Tra ve XAC SUAT Sharpe
    that su lon hon SR*, co tinh den do dai mau va phan phoi lech/duoi day:
    cung mot SR nhung skew am, duoi day (rui ro sap) thi PSR thap hon.
    """
    from scipy.stats import norm  # type: ignore

    if n_obs < 2:
        return float("nan")
    variance_term = 1.0 - skew * sr + (kurtosis - 1.0) / 4.0 * sr**2
    if variance_term <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * np.sqrt(n_obs - 1) / np.sqrt(variance_term)
    return float(norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Sharpe ky vong LON NHAT trong `n_trials` lan thu khi Sharpe that bang 0:

        SR0 = sqrt(V[SR_n]) * ((1 - gamma) * Phi^-1(1 - 1/N) + gamma * Phi^-1(1 - 1/(N e)))

    gamma = hang so Euler-Mascheroni, V[SR_n] = phuong sai Sharpe (theo ky)
    giua cac lan thu. Thu cang nhieu, Sharpe "dep nhat" do may man cang cao.
    """
    from scipy.stats import norm  # type: ignore

    if n_trials <= 1 or sr_variance <= 0:
        return 0.0
    return float(
        np.sqrt(sr_variance)
        * (
            (1 - _EULER_GAMMA) * norm.ppf(1 - 1 / n_trials)
            + _EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * np.e))
        )
    )


def deflated_sharpe(
    observed: float,
    n_trials: int,
    n_obs: int,
    sr_variance: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014): PSR voi nguong
    SR* = expected_max_sharpe(n_trials, sr_variance).

    Thu nhieu to hop roi bao cao to hop dep nhat la cach de nhat de tu lua.
    DSR la XAC SUAT Sharpe that cua chien luoc duoc chon > 0 SAU KHI tru phan
    "may man do tim kiem nhieu". `observed`: Sharpe theo ky cua chien luoc;
    `sr_variance`: phuong sai Sharpe theo ky giua `n_trials` lan thu.
    """
    threshold = expected_max_sharpe(n_trials, sr_variance)
    return probabilistic_sharpe(observed, n_obs, skew, kurtosis, sr_benchmark=threshold)


def profit_factor(trade_returns: pd.Series) -> float:
    gains = trade_returns[trade_returns > 0].sum()
    losses = abs(trade_returns[trade_returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def win_rate(trade_returns: pd.Series) -> float:
    return float((trade_returns > 0).mean()) if len(trade_returns) else 0.0


def expectancy_r(r_multiples: pd.Series) -> float:
    """Ky vong moi lenh tinh bang boi so R - chi so trung thuc nhat."""
    return float(r_multiples.mean()) if len(r_multiples) else 0.0


def summarise(equity: pd.Series, trades: pd.DataFrame) -> dict:
    returns = equity.pct_change().dropna()
    trade_returns = trades["return"] if "return" in trades.columns else pd.Series(dtype=float)
    r_values = trades["r_multiple"] if "r_multiple" in trades.columns else pd.Series(dtype=float)

    return {
        "Ti suat sinh loi tich luy": total_return(equity),
        "CAGR": cagr(equity),
        "Sut giam toi da": max_drawdown(equity),
        "Ti so Sharpe": sharpe(returns),
        "Ti so Sortino": sortino(returns),
        "Vong quay (lan/nam)": turnover(trades, equity),
        "He so loi nhuan": profit_factor(trade_returns),
        "Ti le thang": win_rate(trade_returns),
        "Ky vong (boi so R)": expectancy_r(r_values),
        "So lenh": int(len(trades)),
    }


def format_report(stats: dict) -> str:
    lines = []
    for key, value in stats.items():
        if isinstance(value, float):
            if key in {"So lenh"}:
                lines.append(f"{key}: {int(value)}")
            elif any(tag in key for tag in ("R)", "He so", "Sharpe", "Sortino", "Vong quay")):
                lines.append(f"{key}: {value:.2f}")
            else:
                lines.append(f"{key}: {value:.2%}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def monthly_returns(equity: pd.Series) -> pd.Series:
    """Loi suat theo thang lich (gia tri cuoi thang / cuoi thang truoc - 1)."""
    if equity.empty:
        return pd.Series(dtype=float)
    periods = pd.DatetimeIndex(equity.index).to_period("M")
    month_end = equity.groupby(periods).last()
    returns = month_end.pct_change()
    # thang dau: so voi von ban dau, chi khi thang do co hon mot quan sat
    returns.iloc[0] = month_end.iloc[0] / equity.iloc[0] - 1 if (periods == periods[0]).sum() > 1 else np.nan
    return returns.dropna()


def monthly_win_rate(equity: pd.Series, benchmark: pd.Series | None = None) -> float:
    """Ti le thang co loi suat > 0 (benchmark=None) hoac > benchmark cung thang."""
    mine = monthly_returns(equity)
    if mine.empty:
        return 0.0
    if benchmark is None:
        return float((mine > 0).mean())
    other = monthly_returns(benchmark.reindex(equity.index).ffill().dropna())
    both = pd.concat({"a": mine, "b": other}, axis=1).dropna()
    return float((both["a"] > both["b"]).mean()) if len(both) else 0.0
