import pandas as pd

from invest_system.data.cleaner import clean_ohlcv


def test_parses_integer_dates_and_sorts():
    raw = pd.DataFrame(
        {
            "<Ticker>": ["FPT", "FPT", "FPT"],
            "<DTYYYYMMDD>": [20240103, 20240101, 20240102],
            "<Open>": [10, 10, 10],
            "<High>": [11, 11, 11],
            "<Low>": [9, 9, 9],
            "<Close>": [10.5, 10.2, 10.3],
            "<Volume>": [100, 200, 300],
        }
    )
    out = clean_ohlcv(raw)
    assert list(out["time"].dt.day) == [1, 2, 3]
    assert out["symbol"].unique().tolist() == ["FPT"]


def test_drops_duplicates_keeping_last():
    raw = pd.DataFrame(
        {
            "symbol": ["FPT", "FPT"],
            "time": ["2024-01-01", "2024-01-01"],
            "open": [10, 10], "high": [11, 11], "low": [9, 9],
            "close": [10.0, 12.0], "volume": [100, 500],
        }
    )
    out = clean_ohlcv(raw)
    assert len(out) == 1
    assert out["close"].iloc[0] == 12.0


def test_removes_non_positive_close():
    raw = pd.DataFrame(
        {
            "time": ["2024-01-01", "2024-01-02"],
            "open": [10, 10], "high": [11, 11], "low": [9, 0],
            "close": [10.0, 0.0], "volume": [100, 0],
        }
    )
    assert len(clean_ohlcv(raw)) == 1
