import pandas as pd
import pytest

from invest_system.analysis.ratios import compute_ratios
from invest_system.analysis.valuation import value_company
from invest_system.data import demo
from invest_system.data.fundamentals import StandardFinancials


def test_bank_uses_justified_pb_not_dcf():
    fin = demo.financials("DEMOB")
    ratios = compute_ratios(fin, "BANK")
    val = value_company(fin, "BANK", 40000, 2e9, ratios, {}, beta=1.0, rf=0.03)
    keys = {m.key for m in val.methods}
    assert "justified_pb" in keys
    assert "dcf_fcff" not in keys and "ev_ebitda" not in keys


def test_justified_pb_formula():
    # ROE 20%, Ke = max(3% + 1.0*8%, san 12%) = 12%, g = min(ROE*(1-0.25), 6%, Ke-4%) = 6%
    # -> P/B = (0.20-0.06)/(0.12-0.06) = 2.333
    years = [2021, 2022, 2023, 2024, 2025]
    frame = pd.DataFrame({"net_income_parent": [20.0] * 5, "equity": [100.0] * 5,
                          "total_assets": [1000.0] * 5, "net_interest_income": [30.0] * 5},
                         index=years) * 1e9
    fin = StandardFinancials("TST", frame, "test")
    ratios = compute_ratios(fin, "BANK")
    val = value_company(fin, "BANK", 10000, 1e7, ratios, {}, beta=1.0, rf=0.03)
    jpb = next(m for m in val.methods if m.key == "justified_pb")
    assert jpb.inputs["P/B hợp lý"] == pytest.approx(0.14 / 0.06)


def test_dcf_skipped_when_fcff_negative():
    years = [2022, 2023, 2024, 2025]
    frame = pd.DataFrame({"revenue": [100.0] * 4, "net_income_parent": [10.0] * 4,
                          "net_income": [10.0] * 4, "equity": [80.0] * 4, "total_assets": [150.0] * 4,
                          "cfo": [5.0] * 4, "capex": [-30.0] * 4}, index=years) * 1e9
    fin = StandardFinancials("TST", frame, "test")
    val = value_company(fin, "NON_FINANCIAL", 20000, 1e7, compute_ratios(fin, "NON_FINANCIAL"),
                        {"pe": (8.0, 10.0, 12.0)}, beta=1.0, rf=0.03)
    assert "dcf_fcff" not in {m.key for m in val.methods}
    assert any("DCF" in s for s in val.skipped)
    pe = next(m for m in val.methods if m.key == "pe_relative")
    eps = 10e9 / 1e7
    assert pe.values["base"] == pytest.approx(eps * 1.0 * 10.0)  # tang truong 0% (CAGR = 0)
    assert val.target_price is not None


def test_scenarios_are_ordered():
    fin = demo.financials("DEMO")
    val = value_company(fin, "NON_FINANCIAL", 30000, 5e8, compute_ratios(fin, "NON_FINANCIAL"),
                        {"pe": (8.0, 10.0, 12.0), "pb": (1.0, 1.3, 1.6)}, beta=1.0, rf=0.03)
    assert val.target["bear"] <= val.target["base"] <= val.target["bull"]
