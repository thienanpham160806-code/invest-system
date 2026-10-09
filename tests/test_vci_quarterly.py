"""BCTC quy VCI raw: anh xa ma chi tieu, ngay cong bo, kiem tra TS = No + VCSH. Khong goi mang."""
import pandas as pd
import pytest

from invest_system.data import vci_quarterly as vq

DICTIONARY = pd.DataFrame([
    # report_name, field_name, en_name
    ("INCOME_STATEMENT", "isa3", "Net sales"),
    ("INCOME_STATEMENT", "isa22", "Attributable to parent company"),
    ("BALANCE_SHEET", "bsa53", "Total assets"),
    ("BALANCE_SHEET", "bsa54", "Liabilities"),
    ("BALANCE_SHEET", None, "Owners' equity"),          # dong tieu de, khong co ma
    ("BALANCE_SHEET", "bsa78", "Owners' equity"),
    ("CASH_FLOW", "cfa9", "Other receipts from operating activities"),
    ("CASH_FLOW", "cfa18", "Net cash inflows/outflows from operating activities"),
    ("CASH_FLOW", "cfa19", "Purchases of fixed assets and other long term assets"),
], columns=["report_name", "field_name", "en_name"])


def _raw(rows, **codes):
    frame = pd.DataFrame([{"yearReport": y, "lengthReport": q, "publicDate": pub,
                           "updateDate": upd} for y, q, pub, upd in rows])
    for code, values in codes.items():
        frame[code] = values
    return frame


def _raws(assets=(100e9, 110e9), liabilities=(60e9, 66e9), equity=(40e9, 44e9)):
    periods = [(2026, 1, "2026-04-28", "2026-05-01"), (2026, 2, "2026-08-20", "2026-08-21")]
    return {
        "income": _raw(periods, isa3=[10e9, 12e9], isa22=[1e9, 1.2e9]),
        "balance": _raw([(y, q, p if q == 1 else "2026-08-22", u) for y, q, p, u in periods],
                        bsa53=list(assets), bsa54=list(liabilities), bsa78=list(equity)),
        "cashflow": _raw(periods, cfa9=[0.0, 0.0], cfa18=[2e9, -1e9], cfa19=[-5e8, -6e8]),
    }


def test_maps_net_cfo_not_other_receipts():
    result = vq.standardize("abc", _raws(), DICTIONARY)
    assert result.mapping["cfo"].startswith("cashflow.cfa18")
    assert list(result.frame["cfo"]) == [2e9, -1e9]
    assert result.mapping["capex"].startswith("cashflow.cfa19")


def test_header_row_without_code_does_not_shadow_equity():
    result = vq.standardize("ABC", _raws(), DICTIONARY)
    assert result.mapping["equity"] == "balance.bsa78 owners_equity"
    assert list(result.frame["equity"]) == [40e9, 44e9]


def test_published_at_is_latest_of_three_statements():
    frame = vq.standardize("ABC", _raws(), DICTIONARY).frame
    assert frame["symbol"].unique().tolist() == ["ABC"]
    assert frame.loc[frame["quarter"] == 2, "published_at"].iloc[0] == pd.Timestamp("2026-08-22")
    assert frame.loc[frame["quarter"] == 1, "published_at"].iloc[0] == pd.Timestamp("2026-04-28")


def test_duplicate_period_keeps_latest_update_and_annual_rows_dropped():
    raws = _raws()
    extra = _raw([(2026, 1, "2026-06-01", "2026-06-02"), (2025, 5, "2026-03-01", "2026-03-02")],
                 isa3=[11e9, 99e9], isa22=[1.1e9, 9e9])
    raws["income"] = pd.concat([raws["income"], extra], ignore_index=True)
    frame = vq.standardize("ABC", raws, DICTIONARY).frame
    assert set(zip(frame["year"], frame["quarter"], strict=True)) == {(2026, 1), (2026, 2)}
    assert frame.loc[frame["quarter"] == 1, "revenue"].iloc[0] == 11e9   # ban cap nhat sau


def test_codes_missing_from_raw_fall_back_to_next_candidate():
    names = {"cfa18": "net_cash_inflows_outflows_from_operating_activities",
             "cfa99": "net_cash_from_operating_activities"}
    assert vq.pick_code(names, "cfo", available={"cfa99"}) == ("cfa99", "net_cash_from_operating_activities")
    assert vq.pick_code(names, "cfo", available=set()) == (None, None)


def test_keyword_fallback_skips_other_and_less_lines():
    names = {"x1": "other_receipts_from_operating_activities", "x2": "less_operating_items_activities",
             "x3": "operating_activities_cash_net_total"}
    assert vq.pick_code(names, "cfo")[0] == "x3"
    assert vq.pick_code({"x1": "other_receipts_from_operating_activities"}, "cfo") == (None, None)


def test_validate_rejects_unbalanced_and_wrong_unit_quarters():
    raws = _raws(assets=(100e9, 110e9), liabilities=(60e9, 70e9), equity=(40e9, 44e9))  # Q2 lech ~3,6%
    result = vq.validate(vq.standardize("ABC", raws, DICTIONARY), "NON_FINANCIAL")
    assert list(result.frame["quarter"]) == [1]
    assert result.rejected and "2026-Q2" in result.rejected[0] and "TS ≠ Nợ + VCSH" in result.rejected[0]
    small = vq.validate(vq.standardize("ABC", _raws(assets=(1e6, 1.1e6), liabilities=(6e5, 6.6e5),
                                                    equity=(4e5, 4.4e5)), DICTIONARY), "NON_FINANCIAL")
    assert small.frame.empty and "sai đơn vị" in small.rejected[0] and small.errors


def test_validate_requires_company_type_top_line():
    bank = vq.validate(vq.standardize("ABC", _raws(), DICTIONARY), "BANK")
    assert any("total_operating_income" in e for e in bank.errors)
    assert not vq.validate(vq.standardize("ABC", _raws(), DICTIONARY), "NON_FINANCIAL").errors


def test_missing_statement_is_an_error():
    raws = _raws()
    raws["cashflow"] = pd.DataFrame()
    result = vq.standardize("ABC", raws, DICTIONARY)
    assert any("cash_flow" in e for e in result.errors)
    assert "cfo" not in result.frame.columns


@pytest.mark.parametrize("ctype, template", [("BANK", "BANK"), ("SECURITIES", "SECURITIES"),
                                             ("INSURANCE", "INSURANCE"), ("REAL_ESTATE", "CORPORATE"),
                                             ("NON_FINANCIAL", "CORPORATE"), (None, "CORPORATE")])
def test_template_for(ctype, template):
    assert vq.template_for(ctype) == template


def test_latest_quarters():
    frame = pd.DataFrame([{"symbol": s, "year": 2024 + i // 4, "quarter": i % 4 + 1}
                          for s in ("A", "B") for i in range(10)])
    last = vq.latest_quarters(frame, 8)
    assert last.groupby("symbol").size().to_dict() == {"A": 8, "B": 8}
    a = last[last["symbol"] == "A"].sort_values(["year", "quarter"])
    assert (a.iloc[0]["year"], a.iloc[0]["quarter"]) == (2024, 3)     # 2024-Q1..2026-Q2 -> bo 2 quy dau
    assert (a.iloc[-1]["year"], a.iloc[-1]["quarter"]) == (2026, 2)
