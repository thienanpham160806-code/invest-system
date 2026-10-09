import numpy as np
import pandas as pd

from invest_system.indicators.rsi import LOWER_BOUNDS, UPPER_BOUNDS, adaptive_bands, rsi, rsi_state


def make_frame(n=300, seed=11):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.015, n)))
    return pd.DataFrame(
        {"close": close, "high": close * 1.01, "low": close * 0.99, "volume": np.full(n, 1_000.0)}
    )


def test_rsi_bounds():
    values = rsi(make_frame()["close"]).dropna()
    assert values.between(0, 100).all()


def test_rsi_high_for_strictly_rising_series():
    close = pd.Series(np.linspace(10, 200, 300))
    values = rsi(close).dropna()
    assert values.iloc[-1] > 95.0


def test_rsi_low_for_strictly_falling_series():
    close = pd.Series(np.linspace(200, 10, 300))
    values = rsi(close).dropna()
    assert values.iloc[-1] < 5.0


def test_adaptive_bands_clamped_to_bounds_on_constant_rsi():
    close = pd.Series(np.linspace(10, 500, 300))  # RSI pinned near 100 sau warmup
    values = rsi(close)
    bands = adaptive_bands(values).dropna()
    assert (bands["upper"] <= UPPER_BOUNDS[1] + 1e-9).all()
    assert (bands["upper"] >= UPPER_BOUNDS[0] - 1e-9).all()
    assert (bands["lower"] <= LOWER_BOUNDS[1] + 1e-9).all()
    assert (bands["lower"] >= LOWER_BOUNDS[0] - 1e-9).all()
    assert abs(bands["upper"].iloc[-1] - UPPER_BOUNDS[1]) < 1e-6  # bi kep vao bien tren


def test_rsi_state_zone_overbought_on_strong_uptrend():
    close = pd.Series(np.linspace(10, 500, 300))
    frame = pd.DataFrame({"close": close})
    state = rsi_state(frame)
    assert state["zone"] == "qua_mua"
    assert state["value"] > state["upper"]


def test_rsi_state_slope_positive_on_recent_uptrend():
    # Random walk de RSI co ca tang va giam thuc su (avg_loss != 0), sau do
    # them mot dot tang gia manh 20 phien de kiem tra do doc RSI tang theo.
    rng = np.random.default_rng(3)
    walk = 50 + np.cumsum(rng.normal(0, 1.0, 280))
    rally = np.linspace(walk[-1], walk[-1] + 30, 20)
    close = pd.Series(np.concatenate([walk, rally]))
    frame = pd.DataFrame({"close": close})
    state = rsi_state(frame)
    assert state["slope"] > 0
