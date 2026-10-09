"""BCTC point-in-time: khong bao gio tra ve ky chua cong bo."""
import pandas as pd
import pytest

from invest_system.backtest import pit
from invest_system.backtest.pit import (
    ANNUAL,
    BASIS_ACTUAL,
    BASIS_RULE,
    PointInTimeStore,
    available_financials,
)


def _rows():
    rows = []
    for year in (2023, 2024, 2025):
        rows.append({"symbol": "AAA", "year": year, "quarter": ANNUAL, "net_income": year * 10.0})
        for q in (1, 2, 3, 4):
            rows.append({"symbol": "AAA", "year": year, "quarter": q, "net_income": year + q / 10})
    rows.append({"symbol": "AAA", "year": 2026, "quarter": 1, "net_income": 1.0})
    rows.append({"symbol": "AAA", "year": 2026, "quarter": 2, "net_income": 2.0})
    return pd.DataFrame(rows)


@pytest.fixture
def store():
    return PointInTimeStore(_rows())


def _periods(view):
    return set(zip(view["year"], view["quarter"], strict=True))


def test_annual_not_visible_before_april_first(store):
    assert (2024, ANNUAL) not in _periods(available_financials("AAA", "2025-03-31", store=store))
    assert (2024, ANNUAL) in _periods(available_financials("AAA", "2025-04-01", store=store))


@pytest.mark.parametrize("quarter, last_hidden, first_visible", [
    (1, "2025-05-14", "2025-05-15"),   # 31/03 + 45
    (2, "2025-08-13", "2025-08-14"),   # 30/06 + 45
    (3, "2025-11-13", "2025-11-14"),   # 30/09 + 45
    (4, "2026-02-28", "2026-03-01"),   # 31/12 + 60
])
def test_quarter_lags(store, quarter, last_hidden, first_visible):
    assert (2025, quarter) not in _periods(available_financials("AAA", last_hidden, store=store))
    assert (2025, quarter) in _periods(available_financials("AAA", first_visible, store=store))


def test_never_returns_unpublished_period(store):
    """Quet moi ngay 2023-2026: moi ky tra ve deu da ket thuc VA da qua ngay cong bo."""
    for as_of in pd.date_range("2023-01-01", "2026-12-31", freq="D"):
        view = available_financials("AAA", as_of, store=store)
        if view.empty:
            continue
        assert (view["available_from"] <= as_of).all()
        assert (view["period_end"] < as_of).all()
        for _, row in view.iterrows():
            expected = pit.rule_available_from(row["year"], row["quarter"])
            assert row["available_from"] == expected


def test_q4_and_annual_are_separate_periods(store):
    view = available_financials("AAA", "2026-03-15", store=store)
    assert (2025, 4) in _periods(view)            # quy 4 co tu 01/03
    assert (2025, ANNUAL) not in _periods(view)   # BCTC nam kiem toan chua co


def test_actual_publication_date_earlier_than_rule():
    frame = pd.DataFrame([{"symbol": "BBB", "year": 2025, "quarter": 3,
                           "published_at": "2025-10-20", "net_income": 5.0}])
    store = PointInTimeStore(frame)
    assert available_financials("BBB", "2025-10-20", store=store).empty   # cong bo trong ngay -> chua dung
    view = available_financials("BBB", "2025-10-21", store=store)
    assert len(view) == 1 and view.iloc[0]["available_basis"] == BASIS_ACTUAL


def test_actual_publication_date_later_than_rule():
    frame = pd.DataFrame([{"symbol": "BBB", "year": 2024, "quarter": ANNUAL,
                           "published_at": "2025-04-28", "net_income": 5.0}])
    store = PointInTimeStore(frame)
    assert available_financials("BBB", "2025-04-15", store=store).empty   # nop muon: quy tac 01/04 khong ap
    assert len(available_financials("BBB", "2025-04-29", store=store)) == 1


def test_publication_before_period_end_is_ignored():
    frame = pd.DataFrame([{"symbol": "BBB", "year": 2025, "quarter": 2,
                           "published_at": "2025-01-05", "net_income": 5.0}])
    store = PointInTimeStore(frame)
    assert store.frame.iloc[0]["available_basis"] == BASIS_RULE
    assert available_financials("BBB", "2025-08-13", store=store).empty


def test_restated_vintage_only_after_its_publication():
    frame = pd.DataFrame([
        {"symbol": "CCC", "year": 2024, "quarter": ANNUAL, "published_at": "2025-03-25", "net_income": 100.0},
        {"symbol": "CCC", "year": 2024, "quarter": ANNUAL, "published_at": "2025-09-10", "net_income": 80.0},
    ])
    store = PointInTimeStore(frame)
    assert available_financials("CCC", "2025-06-30", store=store).iloc[0]["net_income"] == 100.0
    after = available_financials("CCC", "2025-09-11", store=store)
    assert len(after) == 1 and after.iloc[0]["net_income"] == 80.0


def test_freq_filter_and_latest(store):
    annual = available_financials("AAA", "2026-06-30", freq="annual", store=store)
    assert set(annual["quarter"]) == {ANNUAL} and annual.iloc[-1]["year"] == 2025
    quarterly = available_financials("AAA", "2026-06-30", freq="quarter", store=store)
    assert (2026, 1) in _periods(quarterly) and (2026, 2) not in _periods(quarterly)
    assert store.latest("AAA", "2026-06-30", "quarter")["year"] == 2026
    with pytest.raises(ValueError):
        available_financials("AAA", "2026-06-30", freq="monthly", store=store)


def test_unknown_symbol_and_symbol_case(store):
    assert available_financials("ZZZ", "2026-01-01", store=store).empty
    assert not available_financials("aaa", "2026-01-01", store=store).empty


def test_default_store_reads_annual_and_quarterly(monkeypatch, tmp_path):
    annual = pd.DataFrame([{"symbol": "DDD", "year": 2025, "quarter": ANNUAL, "net_income": 9.0}])
    quarterly = pd.DataFrame([{"symbol": "DDD", "year": 2026, "quarter": 1, "net_income": 3.0},
                              {"symbol": "EEE", "year": 2026, "quarter": 1, "net_income": 1.0}])
    qpath = tmp_path / "bctc_quarterly.parquet"
    quarterly.to_parquet(qpath)
    monkeypatch.setattr(pit, "_annual_rows", lambda s: annual if s == "DDD" else pd.DataFrame())
    monkeypatch.setattr(pit, "_quarterly_path", lambda: qpath)
    pit._default_store.cache_clear()
    try:
        assert available_financials("DDD", "2026-03-31").empty
        assert _periods(available_financials("DDD", "2026-05-15")) == {(2025, ANNUAL), (2026, 1)}
    finally:
        pit._default_store.cache_clear()
