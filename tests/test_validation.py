import pandas as pd

from invest_system.data.fundamentals import StandardFinancials
from invest_system.validation.checks import check_financials, check_prices


def _fin(liab_offset=0.0):
    frame = pd.DataFrame({"total_assets": [100e9, 120e9, 130e9],
                          "total_liabilities": [60e9, 70e9 + liab_offset, 75e9],
                          "equity": [40e9, 50e9, 55e9], "revenue": [80e9, 90e9, 95e9],
                          "gross_profit": [20e9, 22e9, 25e9], "net_income": [5e9, 6e9, 7e9],
                          "cfo": [6e9, 6e9, 8e9]}, index=[2023, 2024, 2025])
    return StandardFinancials("TST", frame, "test")


def _status(checks, name):
    return next(c.status for c in checks if c.name.startswith(name))


def test_balance_identity_pass_and_fail():
    assert _status(check_financials(_fin(), "NON_FINANCIAL"), "Tổng TS") == "PASS"
    assert _status(check_financials(_fin(5e9), "NON_FINANCIAL"), "Tổng TS") == "FAIL"


def test_empty_financials_fail():
    checks = check_financials(StandardFinancials("X", pd.DataFrame(), "—"), "NON_FINANCIAL")
    assert checks[0].status == "FAIL"


def test_price_checks_flag_non_positive():
    t = pd.bdate_range("2026-01-01", periods=30)
    frame = pd.DataFrame({"time": t, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 100})
    frame.loc[5, "close"] = 0
    checks = check_prices(frame, "HOSE", as_of=t[-1])
    assert _status(checks, "Không có giá") == "FAIL"
