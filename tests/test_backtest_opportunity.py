"""Chien luoc bang co hoi: chon ma, tran nganh, lich tai can bang, walk-forward, IC khong nhin truoc."""
import numpy as np
import pandas as pd
import pytest

from invest_system.backtest import opportunity as opp
from invest_system.backtest.portfolio import Costs, Market

NO_COST = Costs(fee_rate=0.0, sell_tax=0.0, settle_days=2, participation=1.0, lot=100)


def _day(as_of, rows):
    return pd.DataFrame([{"as_of": pd.Timestamp(as_of), "symbol": s, "eligible": e, "score": sc, "upside": 0.3,
                          "avg_value_20d": 1e10, "icb1": sec, "market_cap": mc}
                         for s, e, sc, sec, mc in rows])


def test_select_respects_sector_cap_and_eligibility():
    day = _day("2026-01-30", [("A1", True, 90, "Bank", 1), ("A2", True, 89, "Bank", 1), ("A3", True, 88, "Bank", 1),
                              ("A4", True, 87, "Bank", 1), ("B1", True, 80, "Tech", 1), ("C1", False, 99, "Oil", 1),
                              ("D1", True, 70, "Food", 1)])
    picked = opp.select(day, n=10)                      # tran 35% x 10 = 3 ma/nganh
    assert picked == ["A1", "A2", "A3", "B1", "D1"]
    assert opp.select(day, n=2) == ["A1", "B1"]         # 35% x 2 -> toi thieu 1 ma/nganh
    assert "C1" not in picked                           # khong du dieu kien /co-hoi
    assert opp.select(day, n=10, exclude=frozenset({"A1"}))[0] == "A2"


def test_targets_monthly_vs_quarterly_and_equal_weight():
    scores = pd.concat([_day(d, [("A1", True, 90, "Bank", 5), ("B1", True, 80, "Tech", 9)])
                        for d in ("2026-01-30", "2026-02-27", "2026-03-31")])
    monthly = opp.strategy_targets(scores, opp.Config(10, "M"))
    quarterly = opp.strategy_targets(scores, opp.Config(10, "Q"))
    assert len(monthly) == 3 and list(quarterly) == [pd.Timestamp("2026-03-31")]
    assert monthly[pd.Timestamp("2026-01-30")] == {"A1": 0.1, "B1": 0.1}      # 1/N, phan con lai tien mat
    assert opp.market_cap_targets(scores, 1)[pd.Timestamp("2026-01-30")] == {"B1": 1.0}
    assert opp.equal_weight_targets(scores)[pd.Timestamp("2026-01-30")] == {"A1": 0.5, "B1": 0.5}


def test_windows_train_24_test_6():
    w = opp.windows("2018-10-01", "2026-10-01")
    assert w[0] == (pd.Timestamp("2018-10-01"), pd.Timestamp("2020-10-01"), pd.Timestamp("2021-04-01"))
    assert w[1][0] == pd.Timestamp("2019-04-01")
    assert w[-1][2] <= pd.Timestamp("2026-10-01") and len(w) == 12


def _synthetic(n_symbols=30, days=400, seed=1):
    rng = np.random.default_rng(seed)
    cal = pd.bdate_range("2020-01-01", periods=days)
    drift = np.linspace(-0.001, 0.001, n_symbols)               # ma so cao hon tang nhanh hon
    frames = []
    for k in range(n_symbols):
        close = 10_000 * np.exp(np.cumsum(drift[k] + rng.normal(0, 0.01, days)))
        frames.append(pd.DataFrame({"symbol": f"S{k:02d}", "time": cal, "open": close, "high": close * 1.01,
                                    "low": close * 0.99, "close": close, "volume": 1e7}))
    ohlcv = pd.concat(frames)
    month_ends = pd.Series(cal).groupby(cal.to_period("M")).max().tolist()
    scores = pd.concat([_day(d, [(f"S{k:02d}", True, 50 + k, f"sec{k % 6}", k + 1) for k in range(n_symbols)])
                        for d in month_ends])
    scores["score_valuation"] = scores["score"]
    return Market.from_ohlcv(ohlcv, calendar=cal), scores, cal


def test_forward_returns_start_after_signal():
    market, scores, cal = _synthetic(n_symbols=3, days=200)
    fwd = opp.forward_returns(market, scores)
    row = fwd.iloc[0]
    i = cal.get_loc(row["as_of"])
    sym = row["symbol"]
    expected = market.open[sym].iloc[i + 1 + 21] / market.open[sym].iloc[i + 1] - 1
    assert row["fwd_1m"] == pytest.approx(expected)
    assert fwd["fwd_6m"].isna().iloc[-1]               # khong du phien phia sau -> NaN, khong doan


def test_walk_forward_and_ic_on_signal_that_works():
    market, scores, cal = _synthetic()
    wf = opp.walk_forward(market, scores, cal[0], cal[-1], capital=1e9, costs=NO_COST,
                          train_months=6, test_months=3)
    assert len(wf.slices) >= 2 and not wf.equity.empty
    assert wf.equity.index.is_monotonic_increasing
    assert set(wf.trials["top_n"]) == {10, 20}
    report = wf.sharpe_report()
    assert 0 <= report["psr"] <= 1 and report["n_trials"] == 4
    fixed = opp.walk_forward(market, scores, cal[0], cal[-1], costs=NO_COST, fixed=wf.chosen)
    assert fixed.equity.round(2).equals(wf.equity.round(2))       # cung lua chon -> cung ket qua
    ic = opp.ic_table(market, scores, min_names=10)
    one_month = ic[(ic["nhóm"] == "tổng hợp") & (ic["kỳ hạn (tháng)"] == 1)].iloc[0]
    assert one_month["IC trung binh"] > 0                          # diem do du lieu tao ra -> IC duong


def test_top_return_symbols():
    market, scores, cal = _synthetic(n_symbols=20)
    top = opp.top_return_symbols(market, set(scores["symbol"]), cal[0], cal[-1], share=0.10)
    assert len(top) == 2
