import pandas as pd
import pytest

from invest_system.analysis.ratios import compute_ratios
from invest_system.analysis.valuation import value_company
from invest_system.analysis.composite import combine
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


def test_vic_uses_own_history_and_never_sector_pe_or_sell_at_low_confidence():
    fin = demo.financials("DEMO")
    ratios = compute_ratios(fin, "REAL_ESTATE")
    val = value_company(
        fin, "REAL_ESTATE", 225500, 7_762_186_429, ratios,
        {"pe": (8.0, 10.0, 12.0), "pb": (0.6, 0.86, 1.1)}, beta=1.0,
        net_income_ttm=24_389_979_000_000,
        historical_multiples={"pb": (5.0, 7.0, 9.0)}, symbol="VIC",
    )
    assert "pe_relative" not in {m.key for m in val.methods}
    pb = next(m for m in val.methods if m.key == "pb_relative")
    assert pb.inputs["P/B mục tiêu"] == 7.0
    assert pb.inputs["Nguồn bội số"] == "lịch sử 5 năm của chính doanh nghiệp"
    assert val.confidence == "THẤP"
    recommendation = combine({"macro": 67, "sector": 69, "growth": 95, "valuation": None},
                             val.upside, valuation_confidence=val.confidence,
                             valuation_confidence_reason=val.confidence_reason)
    assert recommendation.rating == "THEO DÕI"
    assert "BÁN" not in recommendation.rating_reason
    assert "valuation" not in recommendation.weights_used


def test_relative_multiple_outside_range_falls_back_to_company_history():
    years = [2021, 2022, 2023, 2024, 2025]
    frame = pd.DataFrame({"net_income_parent": [10e9] * 5, "equity": [100e9] * 5,
                          "minority_interest": [0] * 5}, index=years)
    fin = StandardFinancials("TST", frame, "test")
    val = value_company(fin, "REAL_ESTATE", 10000, 10_000_000,
                        compute_ratios(fin, "REAL_ESTATE"), {"pb": (0.05, 0.08, 0.1)},
                        beta=1.0, historical_multiples={"pb": (2.0, 3.0, 4.0)}, symbol="TST")
    pb = next(m for m in val.methods if m.key == "pb_relative")
    assert pb.inputs["P/B mục tiêu"] == 3.0
    assert pb.inputs["Nguồn bội số"] == "lịch sử 5 năm của chính doanh nghiệp"


def test_sell_rating_explains_conflicting_strong_groups_in_conclusion():
    recommendation = combine({"macro": 70, "sector": 72, "growth": 80, "quality": 68,
                               "valuation": 20}, -0.2, valuation_confidence="CAO")
    assert recommendation.rating == "BÁN"
    assert "cân nhắc xung đột tín hiệu" in recommendation.rating_reason
