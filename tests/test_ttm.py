"""TTM tu BCTC quy: tong 4 quy, CDKT quy cuoi, VCSH binh quan 5 diem, quy thieu/trung, doi chieu nam."""
import math

import pandas as pd
import pytest

from invest_system.analysis import ttm


def _quarters(start=(2024, 1), n=10, **overrides):
    """n quy lien tiep; LNST = 100 + chi so quy, VCSH = 1000 + 10*chi so quy."""
    rows = []
    year, quarter = start
    for i in range(n):
        rows.append({"symbol": "AAA", "year": year, "quarter": quarter,
                     "revenue": 1000.0 + i, "net_income_parent": 100.0 + i, "cfo": 50.0,
                     "total_assets": 5000.0 + i, "equity": 1000.0 + 10 * i})
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    frame = pd.DataFrame(rows)
    for key, value in overrides.items():
        frame[key] = value
    return frame


def test_flows_sum_last_four_quarters_and_stocks_take_last():
    frame = _quarters(n=10)                       # 2024-Q1 .. 2026-Q2
    result = ttm.compute_ttm(frame)
    assert result.ok and result.label == "TTM Q2/2026" and result.end == (2026, 2)
    assert result.periods == ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    assert result.get("net_income_parent") == 106 + 107 + 108 + 109
    assert result.get("revenue") == 1006 + 1007 + 1008 + 1009
    assert result.get("cfo") == 200
    assert result.get("total_assets") == 5009          # quy cuoi, KHONG cong
    assert result.get("equity") == 1090


def test_equity_average_uses_five_quarter_ends():
    result = ttm.compute_ttm(_quarters(n=10))
    # cuoi 2025-Q2 .. 2026-Q2: chi so 5..9 -> 1050, 1060, 1070, 1080, 1090
    assert result.equity_avg_5 == pytest.approx(1070.0)
    assert result.roe == pytest.approx((106 + 107 + 108 + 109) / 1070.0)


def test_equity_average_missing_fifth_point_is_none_but_ttm_ok():
    result = ttm.compute_ttm(_quarters(n=4))      # chi co 4 quy
    assert result.ok and result.equity_avg_5 is None and result.roe is None
    assert any("VCSH bình quân" in n for n in result.notes)


def test_rows_order_does_not_matter():
    frame = _quarters(n=10).sample(frac=1.0, random_state=7)
    assert ttm.compute_ttm(frame).get("net_income_parent") == 106 + 107 + 108 + 109


def test_explicit_end_quarter():
    result = ttm.compute_ttm(_quarters(n=10), end=(2025, 4))
    assert result.label == "TTM Q4/2025"
    assert result.get("net_income_parent") == 104 + 105 + 106 + 107


def test_missing_quarter_blocks_ttm():
    frame = _quarters(n=10)
    frame = frame[~((frame["year"] == 2025) & (frame["quarter"] == 4))]
    result = ttm.compute_ttm(frame)
    assert not result.ok and result.values == {}
    assert result.check.missing == ["2025-Q4"]
    assert "thiếu quý 2025-Q4" in result.notes[0]


def test_conflicting_duplicate_blocks_ttm():
    frame = _quarters(n=10)
    dup = frame[(frame["year"] == 2026) & (frame["quarter"] == 1)].copy()
    dup["net_income_parent"] = 999.0
    result = ttm.compute_ttm(pd.concat([frame, dup]))
    assert not result.ok and result.check.duplicates == ["2026-Q1"]


def test_identical_duplicate_is_dropped_with_note():
    frame = _quarters(n=10)
    dup = frame[(frame["year"] == 2026) & (frame["quarter"] == 1)]
    result = ttm.compute_ttm(pd.concat([frame, dup]))
    assert result.ok and result.get("net_income_parent") == 106 + 107 + 108 + 109
    assert result.check.identical_copies == ["2026-Q1"]


def test_duplicate_outside_window_does_not_block():
    frame = _quarters(n=10)
    dup = frame[(frame["year"] == 2024) & (frame["quarter"] == 1)].copy()
    dup["net_income_parent"] = -1.0
    assert ttm.compute_ttm(pd.concat([frame, dup])).ok


def test_missing_value_in_one_quarter_gives_nan_not_partial_sum():
    frame = _quarters(n=10)
    frame.loc[(frame["year"] == 2026) & (frame["quarter"] == 1), "cfo"] = float("nan")
    result = ttm.compute_ttm(frame)
    assert result.ok and math.isnan(result.values["cfo"]) and result.get("cfo") is None
    assert result.get("net_income_parent") is not None


def test_annual_rows_are_ignored():
    frame = pd.concat([_quarters(n=10), pd.DataFrame([{"symbol": "AAA", "year": 2025, "quarter": 0,
                                                       "net_income_parent": 1e9}])])
    assert ttm.compute_ttm(frame).get("net_income_parent") == 106 + 107 + 108 + 109


def test_empty_input():
    assert not ttm.compute_ttm(pd.DataFrame()).ok


def test_field_classification_from_fundamentals():
    assert "net_income_parent" in ttm.FLOW_FIELDS and "cfo" in ttm.FLOW_FIELDS
    assert "equity" in ttm.STOCK_FIELDS and "total_assets" in ttm.STOCK_FIELDS
    assert not set(ttm.FLOW_FIELDS) & set(ttm.STOCK_FIELDS)


def test_deaccumulate_ytd_cashflow():
    frame = pd.DataFrame([{"year": 2025, "quarter": q, "cfo": ytd, "net_income_parent": 10.0}
                          for q, ytd in ((1, 30.0), (2, 70.0), (3, 90.0), (4, 160.0))])
    out = ttm.deaccumulate_ytd(frame)
    assert list(out["cfo"]) == [30.0, 40.0, 20.0, 70.0]
    assert list(out["net_income_parent"]) == [10.0] * 4     # KQKD khong dung toi


def test_deaccumulate_ytd_missing_previous_quarter_is_nan():
    frame = pd.DataFrame([{"year": 2025, "quarter": q, "cfo": v} for q, v in ((1, 30.0), (3, 90.0))])
    out = ttm.deaccumulate_ytd(frame)
    assert out["cfo"].iloc[0] == 30.0 and math.isnan(out["cfo"].iloc[1])


def _year(values, year=2025):
    return pd.DataFrame([{"year": year, "quarter": q, "net_income_parent": v, "revenue": 100.0}
                         for q, v in enumerate(values, 1)])


def test_reconcile_within_two_percent():
    report = ttm.reconcile_annual(_year([25, 25, 25, 26]), {"net_income_parent": 100.0, "revenue": 400.0}, 2025,
                                  fields=("net_income_parent", "revenue")).set_index("field")
    assert report.loc["net_income_parent", "status"] == "khớp"
    assert report.loc["net_income_parent", "diff_pct"] == pytest.approx(0.01)
    assert report.loc["revenue", "status"] == "khớp"


def test_reconcile_flags_deviation_over_two_percent():
    report = ttm.reconcile_annual(_year([25, 25, 25, 28]), {"net_income_parent": 100.0}, 2025,
                                  fields=("net_income_parent",))
    assert report.iloc[0]["status"] == "lệch" and report.iloc[0]["diff_pct"] == pytest.approx(0.03)


def test_reconcile_detects_ytd_cashflow_mistake():
    ytd = pd.DataFrame([{"year": 2025, "quarter": q, "cfo": v} for q, v in ((1, 30.0), (2, 70.0), (3, 90.0), (4, 160.0))])
    raw = ttm.reconcile_annual(ytd, {"cfo": 160.0}, 2025, fields=("cfo",))
    assert raw.iloc[0]["status"] == "lệch"                 # cong luy ke: 350 vs 160
    fixed = ttm.reconcile_annual(ttm.deaccumulate_ytd(ytd), {"cfo": 160.0}, 2025, fields=("cfo",))
    assert fixed.iloc[0]["status"] == "khớp"


def test_reconcile_statuses_for_gaps():
    three = _year([25, 25, 25])
    assert ttm.reconcile_annual(three, {"net_income_parent": 100.0}, 2025,
                                fields=("net_income_parent",)).iloc[0]["status"] == "thiếu quý"
    assert ttm.reconcile_annual(_year([25, 25, 25, 25]), {}, 2025,
                                fields=("net_income_parent",)).iloc[0]["status"] == "thiếu số năm"
    dup = pd.concat([_year([25, 25, 25, 25]), _year([30, 25, 25, 25]).iloc[[0]]])
    assert ttm.reconcile_annual(dup, {"net_income_parent": 100.0}, 2025,
                                fields=("net_income_parent",)).iloc[0]["status"] == "quý trùng"


def test_reconcile_negative_and_zero_annual():
    loss = ttm.reconcile_annual(_year([-25, -25, -25, -25.5]), {"net_income_parent": -100.0}, 2025,
                                fields=("net_income_parent",))
    assert loss.iloc[0]["status"] == "khớp"
    zero = ttm.reconcile_annual(_year([0, 0, 0, 0]), {"net_income_parent": 0.0}, 2025,
                                fields=("net_income_parent",))
    assert zero.iloc[0]["status"] == "khớp"


# ---------------------------------------------------------------- review Codex d22e2db
def _ytd(rows):
    return pd.DataFrame([{"year": 2025, "quarter": q, "cfo": v} for q, v in rows])


def test_deaccumulate_conflicting_duplicate_is_nan_and_order_independent():
    rows = [(1, 30.0), (2, 70.0), (2, 75.0), (3, 90.0), (4, 160.0)]
    results = []
    for order in (rows, list(reversed(rows)), [rows[2], rows[0], rows[4], rows[1], rows[3]]):
        out = ttm.deaccumulate_ytd(_ytd(order))
        results.append(dict(zip(out["quarter"].astype(int).astype(str) + "/" + out.index.astype(str),
                                out["cfo"], strict=True)))
        by_q = out.groupby("quarter")["cfo"].apply(list).to_dict()
        assert by_q[1] == [30.0]
        assert all(pd.isna(v) for v in by_q[2])        # quy trung khac so
        assert all(pd.isna(v) for v in by_q[3])        # phu thuoc Q2 -> cung NaN
        assert by_q[4] == [70.0]                       # Q4 - Q3 khong dung Q2
    assert len({tuple(sorted(map(str, r.values()))) for r in results}) == 1


def test_deaccumulate_identical_duplicate_is_used():
    out = ttm.deaccumulate_ytd(_ytd([(1, 30.0), (2, 70.0), (2, 70.0), (3, 90.0)]))
    assert out.groupby("quarter")["cfo"].apply(list).to_dict() == {1: [30.0], 2: [40.0, 40.0], 3: [20.0]}


def test_deaccumulate_duplicate_with_one_missing_value_is_conflict():
    out = ttm.deaccumulate_ytd(_ytd([(1, 30.0), (2, 70.0), (2, float("nan")), (3, 90.0)]))
    assert out[out["quarter"] == 3]["cfo"].isna().all()


def test_fifth_equity_point_conflicting_duplicate_is_reported():
    frame = _quarters(n=10)                         # end 2026-Q2 -> diem thu 5 la 2025-Q2
    dup = frame[(frame["year"] == 2025) & (frame["quarter"] == 2)].copy()
    dup["equity"] = 1.0
    result = ttm.compute_ttm(pd.concat([frame, dup]))
    assert result.ok and result.equity_avg_5 is None
    note = next(n for n in result.notes if "VCSH" in n)
    assert "2025-Q2" in note and "trùng" in note and "thiếu" not in note
