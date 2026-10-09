"""Cham diem hop luu ba he chi bao (MACD, RSI, Ichimoku) va sinh khuyen nghi.

Day la noi duy nhat trong he thong quyet dinh MUA/BAN. Ba he cham DOC LAP
(moi he tra ve diem trong [-100, 100]), roi gop co trong so:

    Diem tong = w_macd*S_macd + w_rsi*S_rsi + w_ichi*S_ichi

Nhung day KHONG phai cong don mu quang - co ba quy tac hop luu bat buoc,
xem _apply_confluence_rules():
  1. Ichimoku co quyen PHU QUYET: khong bao gio phat MUA khi gia duoi may
     Kumo, bat ke diem tong cao bao nhieu.
  2. Phan ky am (gia/MACD) tru thang vao diem tong.
  3. Khoi luong qua thap (khong co dong tien xac nhan) ha do tin cay mot bac,
     khong doi diem so nhung lam giam muc do tin tuong vao khuyen nghi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings
from ..indicators.common import atr, volume_ratio
from ..indicators.divergence import detect_divergence
from ..indicators.ichimoku import ICHIMOKU_PRESETS, ichimoku, ichimoku_state
from ..indicators.macd import macd, macd_state
from ..indicators.rsi import rsi_state

CONFIDENCE_LEVELS = ["cao", "trung_binh", "thap"]

ACTION_BUY = "MUA"
ACTION_ACCUMULATE = "TÍCH LUỸ"
ACTION_WATCH = "THEO DÕI"
ACTION_REDUCE = "GIẢM TỶ TRỌNG"
ACTION_SELL = "BÁN"


@dataclass
class Recommendation:
    """Ket qua khuyen nghi day du cho mot ma, dung de bot hien thi va luu lai."""

    symbol: str
    action: str
    total_score: float
    component_scores: dict[str, float]
    confidence: str
    close: float
    entry_low: float
    entry_high: float
    stop_loss: float
    target: float
    target_resistance: float | None
    risk_reward: float | None
    reasons: list[str] = field(default_factory=list)
    vetoed_by_kumo: bool = False

    # Trang thai THO cua tung he chi bao - da tinh san ben trong recommend(),
    # tra kem theo de noi khac (analysis/snapshot.py, analysis/screener.py)
    # KHONG PHAI tinh lai lan nua tren cung mot `frame`.
    macd_state: dict = field(default_factory=dict)
    rsi_state: dict = field(default_factory=dict)
    ichimoku_state: dict = field(default_factory=dict)
    divergence: dict = field(default_factory=dict)
    volume_ratio: float | None = None


def _ichimoku_periods(settings) -> tuple[int, int, int]:
    preset_name = settings.get("indicators.ichimoku_preset", "goc_nhat_6ngay")
    return ICHIMOKU_PRESETS.get(preset_name, ICHIMOKU_PRESETS["goc_nhat_6ngay"])


# --------------------------------------------------------------- cham diem tung he
def score_macd(state: dict) -> float:
    """Diem MACD trong [-100, 100].

    Nen: +/-35 theo above_zero (MACD tren/duoi duong 0). Cong/tru them toi 45
    diem neu vua giao cat (giam dan theo so phien da qua - qua 20 phien coi
    nhu het hieu luc), cat tren duong 0 duoc trong so cao hon cat duoi duong 0
    (dung quy uoc trong docstring cua indicators/macd.py). Hist_slope dieu
    chinh nhe theo dong luc dang manh len hay yeu di.
    """
    above_zero = state.get("above_zero")
    if above_zero is None:
        return 0.0

    score = 35.0 if above_zero else -35.0

    cross, bars_since = state.get("cross"), state.get("bars_since_cross")
    if cross is not None and bars_since is not None:
        decay = max(0.0, 1.0 - bars_since / 20.0)
        if cross == "golden":
            bonus = 45.0 if above_zero else 30.0
        else:
            bonus = -45.0 if not above_zero else -30.0
        score += bonus * decay

    hist_slope = state.get("hist_slope")
    if hist_slope is not None:
        score += float(np.clip(hist_slope * 200.0, -15.0, 15.0))

    return float(np.clip(score, -100.0, 100.0))


def score_rsi(state: dict) -> float:
    """Diem RSI trong [-100, 100].

    Nen: do lech cua RSI so voi muc trung tinh 50, quy doi tuyen tinh ve
    [-100,100]. Vung cuc tri (qua_mua/qua_ban theo nguong thich ung) duoc
    giam trong so 15% vi rui ro dao chieu tang len. Do doc RSI 5 phien dieu
    chinh nhe them.
    """
    value = state.get("value")
    if value is None:
        return 0.0

    base = (value - 50.0) / 50.0 * 100.0
    if state.get("zone") in ("qua_mua", "qua_ban"):
        base *= 0.85

    slope = state.get("slope")
    if slope is not None:
        base += float(np.clip(slope * 10.0, -15.0, 15.0))

    return float(np.clip(base, -100.0, 100.0))


_TK_STRENGTH_WEIGHT = {"manh": 45.0, "trung_tinh": 25.0, "yeu": 10.0}
_KUMO_BASE_SCORE = {"tren_may": 40.0, "trong_may": 0.0, "duoi_may": -40.0}


def score_ichimoku(state: dict) -> float:
    """Diem Ichimoku trong [-100, 100].

    Nen theo vi tri gia so voi may Kumo (+/-40, 0 neu trong may). Giao cat
    Tenkan/Kijun cong/tru them toi 45 diem, TRONG SO THEO VI TRI SO VOI MAY
    (cat tren may = manh = 45, trong may = trung tinh = 25, duoi may = yeu =
    10) - dung dung quy uoc "giao cat tren may la tin hieu manh nhat". Chikou
    thoang phia tren gia qua khu cong them diem xac nhan. May sap doi mau
    (kumo_twist) lam giam do tin cay bang cach thu nho diem lai 15%. May day
    (kumo_thickness) khuech dai nhe diem theo huong hien tai vi la vung ho
    tro/khang cu manh.
    """
    price_vs_kumo = state.get("price_vs_kumo")
    if price_vs_kumo is None:
        return 0.0

    score = _KUMO_BASE_SCORE[price_vs_kumo]

    cross, bars_since, strength = state.get("tk_cross", (None, None, None))
    if cross is not None and bars_since is not None:
        decay = max(0.0, 1.0 - bars_since / 20.0)
        weight = _TK_STRENGTH_WEIGHT.get(strength, 20.0)
        direction = 1.0 if cross == "golden" else -1.0
        score += direction * weight * decay

    if state.get("chikou_free") is True:
        score += 10.0
    elif state.get("chikou_free") is False:
        score -= 10.0

    if state.get("kumo_twist"):
        score *= 0.85

    thickness = state.get("kumo_thickness")
    if thickness is not None:
        boost = float(np.clip(thickness, 0.0, 1.0)) * 10.0
        score += boost if score >= 0 else -boost

    return float(np.clip(score, -100.0, 100.0))


# ------------------------------------------------------------------- ket hop
def _map_action(score: float, settings) -> str:
    buy = settings.get("scoring.thresholds.buy", 60)
    accumulate = settings.get("scoring.thresholds.accumulate", 20)
    watch = settings.get("scoring.thresholds.watch", -20)
    reduce = settings.get("scoring.thresholds.reduce", -60)

    if score >= buy:
        return ACTION_BUY
    if score >= accumulate:
        return ACTION_ACCUMULATE
    if score >= watch:
        return ACTION_WATCH
    if score >= reduce:
        return ACTION_REDUCE
    return ACTION_SELL


def _downgrade_confidence(level: str) -> str:
    idx = CONFIDENCE_LEVELS.index(level)
    return CONFIDENCE_LEVELS[min(idx + 1, len(CONFIDENCE_LEVELS) - 1)]


def _nearest_resistance(ichi_lines: pd.DataFrame, close: float) -> float | None:
    """Muc khang cu Ichimoku gan nhat PHIA TREN gia hien tai (dinh/day may)."""
    last = ichi_lines.iloc[-1]
    candidates = [
        float(v) for v in (last.get("senkou_a"), last.get("senkou_b")) if pd.notna(v) and v > close
    ]
    return min(candidates) if candidates else None


def _entry_zone(close: float, atr14: float | None) -> tuple[float, float]:
    """Vung gia vao: tu gia hien tai den mot bien nho phia tren (~1/4 ATR).

    Muc dich: cho phep khop lenh gan gia thi truong nhung khong duoi ep phai
    mua dung 1 gia, ma khong keo mua qua xa gia hien tai (tranh mua duoi).
    """
    buffer = 0.25 * atr14 if atr14 else close * 0.005
    return close, close + buffer


def _build_reasons(macd_st: dict, rsi_st: dict, ichi_st: dict, divergence: dict) -> list[str]:
    reasons = [_macd_reason(macd_st), _rsi_reason(rsi_st), _ichimoku_reason(ichi_st)]
    if divergence.get("type") is not None:
        note = (
            "phân kỳ dương (đà giảm suy yếu)"
            if divergence["type"] == "bullish"
            else "phân kỳ âm (đà tăng suy yếu)"
        )
        reasons[0] = f"{reasons[0]} Ngoài ra giá và MACD đang xuất hiện {note}."
    return reasons


def _macd_reason(state: dict) -> str:
    cross, bars_since = state.get("cross"), state.get("bars_since_cross")
    above = state.get("above_zero")
    if cross == "golden":
        vi_tri = "trên đường 0 (tín hiệu mạnh)" if above else "dưới đường 0"
        return f"MACD vừa giao cắt vàng {vi_tri}, {bars_since} phiên trước."
    if cross == "death":
        vi_tri = "dưới đường 0 (tín hiệu mạnh)" if not above else "trên đường 0"
        return f"MACD vừa giao cắt chết {vi_tri}, {bars_since} phiên trước."
    slope = state.get("hist_slope")
    if slope is not None and slope < 0:
        return "Histogram MACD đang thu hẹp, động lượng suy yếu dù chưa giao cắt."
    if slope is not None and slope > 0:
        return "Histogram MACD đang mở rộng, động lượng đang mạnh lên."
    return "MACD chưa cho tín hiệu rõ ràng do thiếu dữ liệu."


def _rsi_reason(state: dict) -> str:
    value, zone = state.get("value"), state.get("zone")
    upper, lower = state.get("upper"), state.get("lower")
    if value is None:
        return "Chưa đủ dữ liệu để tính RSI."
    if zone == "qua_mua":
        return f"RSI đang ở {value:.0f}, vượt ngưỡng thích ứng {upper:.0f} — vùng quá mua."
    if zone == "qua_ban":
        return f"RSI đang ở {value:.0f}, dưới ngưỡng thích ứng {lower:.0f} — vùng quá bán."
    return f"RSI đang ở {value:.0f}, trong vùng trung tính ({lower:.0f}-{upper:.0f})."


def _ichimoku_reason(state: dict) -> str:
    pos = state.get("price_vs_kumo")
    if pos is None:
        return "Chưa đủ dữ liệu để xác định vị trí so với mây Ichimoku."
    labels = {
        "tren_may": "trên mây Kumo",
        "trong_may": "trong mây Kumo",
        "duoi_may": "dưới mây Kumo",
    }
    label = labels[pos]
    cross, _, strength = state.get("tk_cross", (None, None, None))
    if cross is not None:
        huong = "tăng" if cross == "golden" else "giảm"
        muc_manh = {
            "manh": "tín hiệu mạnh",
            "trung_tinh": "tín hiệu trung tính",
            "yeu": "tín hiệu yếu",
        }
        do_manh = muc_manh.get(strength, "")
        return f"Giá đang {label}, Tenkan/Kijun vừa giao cắt {huong} ({do_manh})."
    return f"Giá đang {label}."


def recommend(
    frame: pd.DataFrame, symbol: str, weights: dict[str, float] | None = None
) -> Recommendation:
    """Chay ca ba he chi bao tren `frame`, gop diem va sinh khuyen nghi day du.

    `frame` can co cot time, open, high, low, close, volume (chuan OHLCV_COLUMNS
    cua data/base.py), sap xep tang dan theo thoi gian.
    """
    settings = get_settings()
    weights = weights or {
        "macd": settings.get("scoring.weights.macd", 0.30),
        "rsi": settings.get("scoring.weights.rsi", 0.25),
        "ichimoku": settings.get("scoring.weights.ichimoku", 0.45),
    }
    tenkan, kijun, senkou_b = _ichimoku_periods(settings)

    macd_st = macd_state(frame)
    rsi_st = rsi_state(frame)
    ichi_st = ichimoku_state(frame, tenkan=tenkan, kijun=kijun, senkou_b=senkou_b)
    ichi_lines = ichimoku(frame, tenkan=tenkan, kijun=kijun, senkou_b=senkou_b)
    divergence = detect_divergence(frame, macd(frame)["hist"])

    component_scores = {
        "macd": score_macd(macd_st),
        "rsi": score_rsi(rsi_st),
        "ichimoku": score_ichimoku(ichi_st),
    }
    total = (
        weights["macd"] * component_scores["macd"]
        + weights["rsi"] * component_scores["rsi"]
        + weights["ichimoku"] * component_scores["ichimoku"]
    )

    if divergence.get("type") == "bearish":
        total -= settings.get("scoring.divergence_penalty", 25.0)
    total = float(np.clip(total, -100.0, 100.0))

    action = _map_action(total, settings)

    vetoed = ichi_st.get("price_vs_kumo") == "duoi_may"
    if vetoed and action == ACTION_BUY:
        action = ACTION_ACCUMULATE

    confidence = "cao"
    vol_ratio = volume_ratio(frame, period=20).dropna()
    vol_ratio_last = float(vol_ratio.iloc[-1]) if not vol_ratio.empty else None
    low_volume_threshold = settings.get("scoring.low_volume_ratio", 0.5)
    if vol_ratio_last is not None and vol_ratio_last < low_volume_threshold:
        confidence = _downgrade_confidence(confidence)

    close = float(frame["close"].iloc[-1])
    atr_series = atr(frame).dropna()
    atr14 = float(atr_series.iloc[-1]) if not atr_series.empty else None

    kijun_series = ichi_lines["kijun"].dropna()
    kijun_val = float(kijun_series.iloc[-1]) if not kijun_series.empty else None

    k_sl = settings.get("signals.stop_loss_atr", 1.5)
    k_tp = settings.get("signals.take_profit_atr", 3.0)
    atr_stop = close - k_sl * (atr14 or 0.0)
    stop_loss = max(atr_stop, kijun_val) if kijun_val is not None else atr_stop
    stop_loss = min(stop_loss, close * 0.999)  # dam bao stop luon duoi gia hien tai

    target = close + k_tp * (atr14 or 0.0)
    target_resistance = _nearest_resistance(ichi_lines, close)

    risk = close - stop_loss
    risk_reward = (target - close) / risk if risk > 0 else None

    entry_low, entry_high = _entry_zone(close, atr14)
    reasons = _build_reasons(macd_st, rsi_st, ichi_st, divergence)

    return Recommendation(
        symbol=symbol.upper(),
        action=action,
        total_score=total,
        component_scores=component_scores,
        confidence=confidence,
        close=close,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target=target,
        target_resistance=target_resistance,
        risk_reward=risk_reward,
        reasons=reasons,
        vetoed_by_kumo=vetoed,
        macd_state=macd_st,
        rsi_state=rsi_st,
        ichimoku_state=ichi_st,
        divergence=divergence,
        volume_ratio=vol_ratio_last,
    )
