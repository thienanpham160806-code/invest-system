import numpy as np
import pandas as pd

from invest_system.indicators import common as ind


def make_frame(n=300, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n)))
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    return pd.DataFrame(
        {
            "time": pd.date_range("2023-01-02", periods=n, freq="B"),
            "open": close * (1 + rng.normal(0, 0.003, n)),
            "high": high, "low": low, "close": close,
            "volume": rng.integers(50_000, 500_000, n).astype(float),
        }
    )


def test_sma_matches_manual_average():
    series = pd.Series([1.0, 2, 3, 4, 5])
    assert ind.sma(series, 3).iloc[-1] == 4.0


def test_ema_converges_towards_constant_series():
    series = pd.Series([10.0] * 30)
    assert abs(ind.ema(series, 5).iloc[-1] - 10.0) < 1e-9


def test_atr_is_positive():
    frame = make_frame()
    assert (ind.atr(frame).dropna() > 0).all()


def test_volume_ratio_is_one_for_constant_volume():
    frame = pd.DataFrame({"volume": [100.0] * 25, "close": range(25)})
    ratio = ind.volume_ratio(frame, period=20).dropna()
    assert abs(ratio.iloc[-1] - 1.0) < 1e-9


def test_slope_positive_for_rising_series():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert ind.slope(series, bars=3) > 0


def test_slope_none_when_not_enough_data():
    assert ind.slope(pd.Series([1.0, 2.0]), bars=5) is None


def test_detect_cross_finds_golden_cross():
    # Cat xay ra dung o buoc cuoi cung (giua vi tri -2 va -1): bars_since = 0.
    fast = pd.Series([1.0, 2.0, 3.0, 6.0])
    slow = pd.Series([4.0, 4.0, 4.0, 4.0])
    direction, bars_since = ind.detect_cross(fast, slow)
    assert direction == "golden"
    assert bars_since == 0


def test_detect_cross_finds_death_cross():
    fast = pd.Series([5.0, 4.0, 3.0, 1.0, 0.5])
    slow = pd.Series([3.0, 3.0, 3.0, 3.0, 3.0])
    direction, _ = ind.detect_cross(fast, slow)
    assert direction == "death"


def test_detect_cross_none_when_no_crossing():
    fast = pd.Series([5.0, 6.0, 7.0])
    slow = pd.Series([1.0, 1.0, 1.0])
    direction, bars_since = ind.detect_cross(fast, slow)
    assert direction is None
    assert bars_since is None
