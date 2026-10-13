import re

import pandas as pd

from scripts.build_ttm_quarterly import build


def _quarters(symbol, start, values, published="2026-08-20"):
    year, quarter = start
    rows = []
    for value in values:
        rows.append({"symbol": symbol, "year": year, "quarter": quarter, "net_income_parent": value,
                     "published_at": pd.Timestamp(published)})
        year, quarter = (year, quarter + 1) if quarter < 4 else (year + 1, 1)
    return rows


def _frame(*groups):
    return pd.DataFrame([row for group in groups for row in group])


def test_sums_latest_four_quarters_with_verifiable_provenance():
    quarterly = _frame(_quarters("AAA", (2025, 1), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
    ttm, skipped = build(quarterly, {"AAA": "2026-10-09 23:57"})
    row = ttm.iloc[0]
    assert not skipped
    assert row["ni_ttm"] == 18.0
    assert row["ttm_periods"] == "2025-Q3,2025-Q4,2026-Q1,2026-Q2"
    assert row["ttm_label"] == "TTM Q2/2026"
    assert row["ttm_source"].startswith("VCI raw")
    assert all(re.fullmatch(r"20\d{2}-Q[1-4]", period) for period in row["ttm_periods"].split(","))
    assert row["ttm_published_at"] == "2026-08-20"
    assert row["ttm_fetched_at"] == "2026-10-09 23:57"


def test_skips_gap_missing_value_and_stale_symbols():
    fresh = [_quarters(s, (2025, 3), [1.0, 1.0, 1.0, 1.0]) for s in ("AAA", "BBB", "CCC")]
    gap = [r for r in _quarters("GAP", (2025, 1), [1.0] * 6) if (r["year"], r["quarter"]) != (2025, 4)]
    missing = _quarters("NAN", (2025, 3), [1.0, None, 1.0, 1.0])
    stale = _quarters("OLD", (2024, 1), [1.0, 1.0, 1.0, 1.0])
    ttm, skipped = build(_frame(*fresh, gap, missing, stale))
    assert set(ttm["symbol"]) == {"AAA", "BBB", "CCC"}
    assert "thiếu quý 2025-Q4" in skipped["GAP"]
    assert "NAN" in skipped
    assert "cũ hơn 2026-Q2" in skipped["OLD"]


def test_keeps_one_quarter_lag_and_losses():
    fresh = [_quarters(s, (2025, 3), [1.0, 1.0, 1.0, 1.0]) for s in ("AAA", "BBB")]
    lagging = _quarters("LAG", (2025, 2), [-5.0, 1.0, 1.0, 1.0])
    ttm, _ = build(_frame(*fresh, lagging))
    row = ttm.set_index("symbol").loc["LAG"]
    assert row["ttm_label"] == "TTM Q1/2026"
    assert row["ni_ttm"] == -2.0
