import numpy as np
import pandas as pd

from invest_system.indicators.ichimoku import ICHIMOKU_PRESETS, ichimoku, ichimoku_state


def flat_then_jump(base=100.0, jump=None, n=160, tail=10) -> pd.DataFrame:
    close = np.full(n, base)
    if jump is not None:
        close[-tail:] = jump
    return pd.DataFrame({"high": close, "low": close, "close": close})


def test_ichimoku_presets_defined():
    assert ICHIMOKU_PRESETS["goc_nhat_6ngay"] == (9, 26, 52)
    assert ICHIMOKU_PRESETS["hieu_chinh_5ngay"] == (7, 22, 44)


def test_senkou_shifted_forward_by_shift_periods():
    frame = flat_then_jump(jump=None)
    out = ichimoku(frame, tenkan=9, kijun=26, senkou_b=52, shift=26)

    tenkan = (frame["high"].rolling(9, min_periods=9).max()
              + frame["low"].rolling(9, min_periods=9).min()) / 2
    kijun = (frame["high"].rolling(26, min_periods=26).max()
             + frame["low"].rolling(26, min_periods=26).min()) / 2
    expected_senkou_a = ((tenkan + kijun) / 2).shift(26)

    pd.testing.assert_series_equal(
        out["senkou_a"], expected_senkou_a, check_names=False
    )


def test_chikou_shifted_backward_by_shift_periods():
    frame = flat_then_jump(jump=None)
    out = ichimoku(frame, shift=26)
    expected_chikou = frame["close"].shift(-26)
    pd.testing.assert_series_equal(out["chikou"], expected_chikou, check_names=False)


def test_price_above_kumo_after_price_jumps_up():
    frame = flat_then_jump(base=100.0, jump=500.0, tail=10)
    state = ichimoku_state(frame)
    assert state["price_vs_kumo"] == "tren_may"


def test_price_below_kumo_after_price_drops():
    frame = flat_then_jump(base=100.0, jump=20.0, tail=10)
    state = ichimoku_state(frame)
    assert state["price_vs_kumo"] == "duoi_may"


def test_price_inside_kumo_on_flat_series():
    frame = flat_then_jump(base=100.0, jump=None)
    state = ichimoku_state(frame)
    assert state["price_vs_kumo"] == "trong_may"


def test_chikou_free_true_when_price_higher_than_26_bars_ago():
    close = np.concatenate([np.full(100, 100.0), np.linspace(100.0, 200.0, 60)])
    frame = pd.DataFrame({"high": close, "low": close, "close": close})
    state = ichimoku_state(frame)
    assert state["chikou_free"] is True


def test_kumo_break_bars_none_when_price_inside_kumo():
    frame = flat_then_jump(base=100.0, jump=None)
    state = ichimoku_state(frame)
    assert state["kumo_break_bars"] is None


def test_kumo_break_bars_counts_consecutive_sessions_above_kumo():
    # 10 phien cuoi gia nhay len va GIU NGUYEN tren may -> break_bars = 10-1 = 9.
    frame = flat_then_jump(base=100.0, jump=500.0, tail=10)
    state = ichimoku_state(frame)
    assert state["price_vs_kumo"] == "tren_may"
    assert state["kumo_break_bars"] == 9


def test_kumo_break_bars_small_for_recent_break():
    # Chi 1 phien cuoi moi vuot may -> break_bars = 0.
    frame = flat_then_jump(base=100.0, jump=500.0, tail=1)
    state = ichimoku_state(frame)
    assert state["price_vs_kumo"] == "tren_may"
    assert state["kumo_break_bars"] == 0
