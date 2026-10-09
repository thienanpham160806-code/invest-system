import pandas as pd

from scripts.fetch_bctc_vnstock import _tickers_for_exchange


def test_tickers_for_exchange_accepts_empty_supplement():
    assert _tickers_for_exchange(pd.DataFrame(), "UPCOM") == set()


def test_tickers_for_exchange_filters_and_normalizes_symbols():
    frame = pd.DataFrame({"ticker": ["abc", "XYZ"], "exchange": ["upcom", "HOSE"]})
    assert _tickers_for_exchange(frame, "UPCOM") == {"ABC"}

