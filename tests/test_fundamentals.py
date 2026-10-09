import pandas as pd

from invest_system.data.company import classify
from invest_system.data.fundamentals import standardize_long_vi, standardize_vnstock


def test_standardize_vnstock_maps_confirmed_item_ids():
    income = pd.DataFrame({"period": ["2024", "2025"], "revenue": [100.0, 120.0],
                           "net_profit": [10.0, 12.0], "gross_profit": [30.0, 35.0]})
    balance = pd.DataFrame({"period": ["2024", "2025"], "total_assets": [200.0, 220.0],
                            "owners_equity_2": [90.0, 100.0]})
    std = standardize_vnstock("TST", {"income": income, "balance": balance,
                                      "cashflow": pd.DataFrame(), "ratios": pd.DataFrame()})
    assert std.years == [2024, 2025]
    assert std.get("revenue") == 120.0
    assert std.get("equity", 2024) == 90.0
    assert std.mapping["equity"].endswith("owners_equity_2")


def test_standardize_vietnamese_names():
    long = pd.DataFrame({
        "ticker": "TST", "year": [2025, 2025, 2025],
        "item_name": ["Doanh thu thuần về bán hàng và cung cấp dịch vụ", "TỔNG CỘNG TÀI SẢN",
                      "Lợi nhuận sau thuế thu nhập doanh nghiệp"],
        "value": [500.0, 900.0, 50.0]})
    std = standardize_long_vi("TST", long, "test")
    assert std.get("revenue") == 500.0
    assert std.get("total_assets") == 900.0
    assert std.get("net_income") == 50.0


def test_classify_company_type():
    assert classify("XYZ", "Ngân hàng")[0] == "BANK"
    assert classify("VCB", None)[0] == "BANK"
    assert classify("VHM", None)[0] == "REAL_ESTATE"
    assert classify("FPT", "Phần mềm")[0] == "NON_FINANCIAL"
