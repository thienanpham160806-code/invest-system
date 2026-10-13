import pandas as pd

from invest_system.web import universe


def _universe():
    return pd.DataFrame({"symbol": ["AAA", "BBB"], "market_cap": [100.0, 200.0], "shares": [10.0, 10.0]})


def test_ttm_without_vci_raw_source_is_hidden(tmp_path, monkeypatch):
    pd.DataFrame({"symbol": ["AAA"], "ni_ttm": [10.0], "ttm_label": ["TTM Q2/2026"],
                  "ttm_column": ["vnstock income_statement(quarter).net_profit"]}).to_parquet(tmp_path / "ttm.parquet")
    monkeypatch.setattr(universe, "SNAPSHOT_DIR", tmp_path)
    meta = {}
    frame = universe._merge_ttm(_universe(), meta)
    assert "pe_ttm" not in frame.columns
    assert meta["sources"]["ttm"].startswith("Ẩn TTM")


def test_only_vci_raw_rows_feed_pe_ttm(tmp_path, monkeypatch):
    pd.DataFrame({"symbol": ["AAA", "BBB"], "ni_ttm": [10.0, 20.0], "ttm_label": ["TTM Q2/2026"] * 2,
                  "ttm_source": ["VCI raw BCTC quý (income.isa22)", "vnstock final"]}).to_parquet(tmp_path / "ttm.parquet")
    monkeypatch.setattr(universe, "SNAPSHOT_DIR", tmp_path)
    meta = {}
    frame = universe._merge_ttm(_universe(), meta).set_index("symbol")
    assert frame.loc["AAA", "pe_ttm"] == 10.0
    assert pd.isna(frame.loc["BBB", "pe_ttm"])
    assert "1 mã" in meta["sources"]["ttm"]
