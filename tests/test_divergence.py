import numpy as np
import pandas as pd

from invest_system.indicators.divergence import detect_divergence, find_swings


def _two_valleys(low1: float, low2: float) -> np.ndarray:
    """Chuoi co hai day: day dau tai vi tri 10, day sau tai vi tri 30."""
    seg1 = np.linspace(100.0, low1, 11)
    seg2 = np.linspace(low1, 100.0, 11)[1:]
    seg3 = np.linspace(100.0, low2, 11)[1:]
    seg4 = np.linspace(low2, 100.0, 10)[1:]
    return np.concatenate([seg1, seg2, seg3, seg4])


def _two_peaks(high1: float, high2: float) -> np.ndarray:
    """Chuoi co hai dinh: dinh dau tai vi tri 10, dinh sau tai vi tri 30."""
    seg1 = np.linspace(0.0, high1, 11)
    seg2 = np.linspace(high1, 0.0, 11)[1:]
    seg3 = np.linspace(0.0, high2, 11)[1:]
    seg4 = np.linspace(high2, 0.0, 10)[1:]
    return np.concatenate([seg1, seg2, seg3, seg4])


def test_find_swings_detects_single_valley():
    series = pd.Series(_two_valleys(80.0, 80.0)[:21])  # mot day duy nhat tai vi tri 10
    swings = find_swings(series, order=5)
    lows = [s for s in swings if s[2] == "L"]
    assert len(lows) == 1
    assert lows[0][0] == 10


def test_find_swings_detects_single_peak():
    series = pd.Series(_two_peaks(50.0, 50.0)[:21])
    swings = find_swings(series, order=5)
    highs = [s for s in swings if s[2] == "H"]
    assert len(highs) == 1
    assert highs[0][0] == 10


def test_bullish_divergence_lower_low_price_higher_low_oscillator():
    price = _two_valleys(80.0, 70.0)          # gia: day sau THAP hon
    oscillator = _two_valleys(20.0, 30.0)     # chi bao: day sau CAO hon (20 -> 30)
    frame = pd.DataFrame({"close": price, "high": price, "low": price})

    result = detect_divergence(frame, pd.Series(oscillator), lookback=60, order=5)
    assert result["type"] == "bullish"
    assert result["strength"] > 0


def test_bearish_divergence_higher_high_price_lower_high_oscillator():
    price = _two_peaks(120.0, 140.0)          # gia: dinh sau CAO hon
    oscillator = _two_peaks(50.0, 40.0)       # chi bao: dinh sau THAP hon
    frame = pd.DataFrame({"close": price, "high": price, "low": price})

    result = detect_divergence(frame, pd.Series(oscillator), lookback=60, order=5)
    assert result["type"] == "bearish"
    assert result["strength"] > 0


def test_no_divergence_when_price_and_oscillator_agree():
    price = _two_valleys(80.0, 70.0)          # gia: day sau thap hon
    oscillator = _two_valleys(20.0, 10.0)     # chi bao: day sau CUNG thap hon -> khong phan ky
    frame = pd.DataFrame({"close": price, "high": price, "low": price})

    result = detect_divergence(frame, pd.Series(oscillator), lookback=60, order=5)
    assert result["type"] is None
