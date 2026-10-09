"""Engine tai can bang: khop mo cua t+1, phi/thue, T+2 (CP va tien), ket san, gioi han thanh khoan."""
import numpy as np
import pandas as pd
import pytest

from invest_system.backtest import metrics
from invest_system.backtest.portfolio import Costs, Market, floor_locked, run

DAYS = pd.bdate_range("2026-01-05", periods=12)
NO_COST = Costs(fee_rate=0.0, sell_tax=0.0, settle_days=2, participation=1.0, lot=100)


def _ohlcv(symbol, opens, closes=None, lows=None, volume=1e7):
    closes = closes if closes is not None else opens
    lows = lows if lows is not None else [min(o, c) for o, c in zip(opens, closes, strict=True)]
    return pd.DataFrame({"symbol": symbol, "time": DAYS[:len(opens)], "open": opens, "high": np.maximum(opens, closes),
                         "low": lows, "close": closes, "volume": volume})


def _market(*frames):
    return Market.from_ohlcv(pd.concat(frames, ignore_index=True), calendar=DAYS)


def test_signal_at_close_executes_next_open():
    opens = [10_000, 11_000, 12_000, 12_000, 12_000, 12_000]
    m = _market(_ohlcv("AAA", opens))
    res = run(m, {DAYS[0]: {"AAA": 1.0}}, capital=1_100_000, costs=NO_COST, start=DAYS[0], end=DAYS[6])
    buy = res.trades.iloc[0]
    assert buy["time"] == DAYS[1] and buy["price"] == 11_000 and buy["shares"] == 100
    assert res.equity.iloc[0] == 1_100_000                     # chua mua o phien tin hieu
    assert res.equity.iloc[-1] == pytest.approx(1_100_000 - 1_100_000 + 100 * 12_000)


def test_extra_delay_executes_one_session_later():
    m = _market(_ohlcv("AAA", [10_000, 11_000, 12_000, 13_000, 13_000]))
    res = run(m, {DAYS[0]: {"AAA": 1.0}}, capital=2_000_000, costs=NO_COST, delay=2)
    assert res.trades.iloc[0]["time"] == DAYS[2] and res.trades.iloc[0]["price"] == 12_000


def test_fees_and_sell_tax():
    costs = Costs(fee_rate=0.0025, sell_tax=0.001, settle_days=0, participation=1.0, lot=100)
    m = _market(_ohlcv("AAA", [10_000] * 8))
    res = run(m, {DAYS[0]: {"AAA": 1.0}, DAYS[3]: {}}, capital=10_000_000, costs=costs)
    buy, sell = res.trades.iloc[0], res.trades.iloc[1]
    assert buy["fee"] == pytest.approx(buy["value"] * 0.00125)
    assert sell["fee"] == pytest.approx(sell["value"] * 0.00125) and sell["tax"] == pytest.approx(sell["value"] * 0.001)
    lost = 10_000_000 - res.equity.iloc[-1]
    assert lost == pytest.approx(buy["fee"] + sell["fee"] + sell["tax"])


def test_t_plus_2_blocks_early_sale_and_delays_cash():
    m = _market(_ohlcv("AAA", [10_000] * 8), _ohlcv("BBB", [10_000] * 8))
    res = run(m, {DAYS[0]: {"AAA": 1.0}, DAYS[1]: {"BBB": 1.0}}, capital=1_000_000, costs=NO_COST)
    t = res.trades
    sell = t[(t["symbol"] == "AAA") & (t["side"] == "sell")].iloc[0]
    assert sell["time"] == DAYS[3]          # mua phien 1, ban som nhat phien 3 (T+2)
    buy_b = t[(t["symbol"] == "BBB") & (t["side"] == "buy")].iloc[0]
    assert buy_b["time"] == DAYS[5]         # tien ban phien 3 ve phien 5


def test_floor_locked_day_defers_sale():
    # phien 4: dong cua o san (-7%) va low = close -> ket san, ban sang phien 5
    closes = [10_000, 10_000, 10_000, 10_000, 9_300, 9_300, 9_300, 9_300]
    opens = [10_000, 10_000, 10_000, 10_000, 9_800, 9_300, 9_300, 9_300]
    frame = _ohlcv("AAA", opens, closes, lows=[c for c in closes])
    assert floor_locked(frame, "HOSE").tolist()[4] is True
    m = _market(frame)
    res = run(m, {DAYS[0]: {"AAA": 1.0}, DAYS[3]: {}}, capital=1_000_000, costs=NO_COST)
    sell = res.trades[res.trades["side"] == "sell"].iloc[0]
    assert sell["time"] == DAYS[5] and sell["price"] == 9_300


def test_order_capped_by_participation_of_adv20():
    m = _market(_ohlcv("AAA", [10_000] * 6, volume=1_000))          # GTGD 10 trieu/phien
    costs = Costs(fee_rate=0.0, sell_tax=0.0, settle_days=2, participation=0.10, lot=100)
    res = run(m, {DAYS[2]: {"AAA": 1.0}}, capital=1e9, costs=costs)
    assert res.trades.iloc[0]["value"] <= 0.10 * 10_000 * 1_000
    assert res.holdings.iloc[0]["cash_pct"] > 0.99                  # phan con lai giu tien


def test_lot_rounding_and_equal_weights():
    m = _market(_ohlcv("AAA", [10_000] * 5), _ohlcv("BBB", [33_000] * 5))
    res = run(m, {DAYS[0]: {"AAA": 0.5, "BBB": 0.5}}, capital=10_000_000, costs=NO_COST)
    assert (res.trades["shares"] % 100 == 0).all()
    values = res.trades.set_index("symbol")["value"]
    assert values["AAA"] <= 5_000_000 and values["BBB"] <= 5_000_000


def test_missing_bar_waits_and_values_at_last_close():
    a = _ohlcv("AAA", [10_000] * 8)
    halted = _ohlcv("BBB", [10_000] * 8).drop(index=[1, 2])          # tam ngung phien 1-2
    m = _market(a, halted)
    res = run(m, {DAYS[0]: {"BBB": 1.0}}, capital=1_000_000, costs=NO_COST)
    assert res.trades.iloc[0]["time"] == DAYS[3]


def test_turnover_and_monthly_win_rate():
    m = _market(_ohlcv("AAA", [10_000] * 12))
    res = run(m, {DAYS[0]: {"AAA": 1.0}, DAYS[5]: {}}, capital=1_000_000, costs=NO_COST)
    assert res.turnover() > 0
    # bat dau dung cuoi thang: khong tinh thang "0%" gia
    eq = pd.Series([100, 110, 105, 120], index=pd.to_datetime(["2025-12-31", "2026-01-30", "2026-02-27", "2026-03-31"]))
    assert metrics.monthly_returns(eq).round(4).tolist() == [0.1, -0.0455, 0.1429]
    assert metrics.monthly_win_rate(eq) == pytest.approx(2 / 3)
    bench = pd.Series([100, 120, 100, 110], index=eq.index)      # +20%, -16.7%, +10%
    assert metrics.monthly_win_rate(eq, bench) == pytest.approx(2 / 3)
    daily = pd.Series([100, 104, 110], index=pd.to_datetime(["2026-01-05", "2026-01-15", "2026-01-30"]))
    assert metrics.monthly_returns(daily).tolist() == [pytest.approx(0.10)]
