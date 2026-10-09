"""Diem lich su: TTM point-in-time, BCTC nam theo ngay cong bo, gia theo ngay."""
import pandas as pd

from invest_system.backtest import history
from invest_system.backtest.history import price_panel, prices_as_of, ttm_history


def _quarters(published):
    rows = []
    for k, pub in enumerate(published):
        year, quarter = 2025 + k // 4, k % 4 + 1
        rows.append({"symbol": "AAA", "year": year, "quarter": quarter, "net_income_parent": 100.0 + k,
                     "published_at": pd.Timestamp(pub) if pub else pd.NaT})
    return pd.DataFrame(rows)


def test_ttm_available_day_after_latest_quarter_published():
    q = _quarters(["2025-04-20", "2025-07-25", "2025-10-20", "2026-01-30", "2026-04-25"])
    t = ttm_history(q)
    assert t["ttm_label"].tolist() == ["TTM Q4/2025", "TTM Q1/2026"]
    first = t.iloc[0]
    assert first["ni_ttm"] == 100 + 101 + 102 + 103
    assert first["available_from"] == pd.Timestamp("2026-01-31")      # Q4 cong bo 30/01 -> dung tu 31/01


def test_ttm_without_publish_date_uses_conservative_rule():
    q = _quarters(["2025-04-20", "2025-07-25", "2025-10-20", None])
    assert ttm_history(q).iloc[0]["available_from"] == pd.Timestamp("2026-03-01")   # Q4: cuoi quy + 60


def test_ttm_gap_skips_window():
    q = _quarters(["2025-04-20", "2025-07-25", "2025-10-20", "2026-01-30", "2026-04-25"]).drop(index=1)
    assert ttm_history(q).empty


def test_prices_as_of_uses_only_past_and_flags_trading_today():
    days = pd.bdate_range("2026-01-05", periods=30)
    ohlcv = pd.concat([
        pd.DataFrame({"symbol": "AAA", "time": days, "open": 1.0, "high": 1.0, "low": 1.0,
                      "close": range(1, 31), "volume": 100.0}),
        pd.DataFrame({"symbol": "BBB", "time": days[:20], "open": 1.0, "high": 1.0, "low": 1.0,
                      "close": 5.0, "volume": 100.0}),
    ])
    panel = price_panel(ohlcv)
    snap = prices_as_of(panel, days[25]).set_index("symbol")
    assert snap.loc["AAA", "price"] == 26 and bool(snap.loc["AAA", "traded_today"])
    assert snap.loc["AAA", "ret_1m"] == 26 / 5 - 1                    # 21 phien truoc
    assert not bool(snap.loc["BBB", "traded_today"])                   # ngung tu phien 20: van la peer
    assert pd.Timestamp(snap.loc["AAA", "as_of_price"]) <= days[25]


def test_financials_as_of_hides_unpublished_years(monkeypatch):
    from invest_system.data.fundamentals import StandardFinancials
    frame = pd.DataFrame({"net_income_parent": [1.0, 2.0, 3.0]}, index=[2023, 2024, 2025])
    monkeypatch.setattr(history, "_annual", lambda s: StandardFinancials(s, frame, "test"))
    assert history.financials_as_of("AAA", "2026-03-31").years == [2023, 2024]
    assert history.financials_as_of("AAA", "2026-04-01").years == [2023, 2024, 2025]
    assert history.financials_as_of("AAA", "2023-12-31").empty
