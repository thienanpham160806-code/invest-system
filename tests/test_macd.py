import numpy as np
import pandas as pd

from invest_system.indicators.macd import macd, macd_state


def _frame_from_close(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    return pd.DataFrame(
        {"close": close, "high": close, "low": close, "volume": np.full(n, 1_000.0)}
    )


def test_macd_returns_same_length_with_expected_columns():
    frame = _frame_from_close(np.linspace(50, 100, 80))
    out = macd(frame)
    assert list(out.columns) == ["macd", "signal", "hist"]
    assert len(out) == len(frame)


def test_hist_equals_macd_minus_signal():
    frame = _frame_from_close(np.linspace(50, 100, 80))
    out = macd(frame)
    diff = (out["macd"] - out["signal"]).dropna()
    assert np.allclose(out["hist"].dropna(), diff)


def test_golden_cross_and_above_zero_after_downtrend_reversal():
    down = np.linspace(100, 60, 60)
    # Tang toc (compounding) de khoang cach MACD-Signal tiep tuc NO RONG toi
    # tan cuoi chuoi, thay vi hoi tu ve mot muc on dinh nhu xu huong tuyen tinh.
    up = 60 * (1.03) ** np.arange(100)
    frame = _frame_from_close(np.concatenate([down, up]))

    state = macd_state(frame)
    assert state["cross"] == "golden"
    assert state["above_zero"] is True
    assert state["hist_slope"] > 0


def test_death_cross_after_uptrend_reversal():
    up = np.linspace(60, 140, 60)
    # Giam gia tang toc (muc giam moi phien lon dan theo t^3) de khoang cach
    # MACD-Signal tiep tuc no rong ve phia am toi tan cuoi chuoi, khong hoi
    # tu nguoc nhu khi dung suy giam kieu mu (deceleration).
    t = np.arange(90)
    down = 140 - 0.0001 * t**3
    frame = _frame_from_close(np.concatenate([up, down]))

    state = macd_state(frame)
    assert state["cross"] == "death"
    assert state["hist_slope"] < 0


def test_no_cross_on_flat_price():
    frame = _frame_from_close(np.full(60, 100.0))
    state = macd_state(frame)
    assert state["cross"] is None
    assert state["bars_since_cross"] is None


def test_bars_since_cross_matches_manual_sign_change():
    down = np.linspace(100, 60, 60)
    up = np.linspace(60, 140, 100)
    frame = _frame_from_close(np.concatenate([down, up]))

    lines = macd(frame)
    state = macd_state(frame)

    diff = (lines["macd"] - lines["signal"]).dropna().to_numpy()
    sign_changes = np.where(np.diff(np.sign(diff)) != 0)[0]
    assert len(sign_changes) > 0
    expected_bars_since = len(diff) - 1 - (sign_changes[-1] + 1)
    assert state["bars_since_cross"] == expected_bars_since
