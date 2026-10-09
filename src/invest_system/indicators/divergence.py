"""Phat hien phan ky gia / chi bao (MACD hoac RSI).

Day la phan kho sao chep nhat trong bo ba chi bao, vi phai so sanh CHUOI
dinh/day qua nhieu phien, khong phai dieu kien cua mot phien don le.

Quy uoc:
  Phan ky DUONG (bullish) = gia tao day THAP hon lan truoc, nhung chi bao
                             tao day CAO hon lan truoc (dong luc giam ban da
                             yeu di du gia van con giam).
  Phan ky AM   (bearish)  = gia tao dinh CAO hon lan truoc, nhung chi bao
                             tao dinh THAP hon lan truoc.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Swing = tuple[int, float, str]  # (vi tri trong series, gia tri, "H" hoac "L")


def find_swings(series: pd.Series, order: int = 5) -> list[Swing]:
    """Tim dinh/day cuc bo bang cua so truot rong `order` phien moi ben.

    Vi tri i la DINH (H) neu gia tri tai i lon nhat trong [i-order, i+order];
    la DAY (L) neu nho nhat trong cung cua so. Tra ve danh sach theo thu tu
    thoi gian tang dan, vi tri la SO NGUYEN (positional, 0-based).
    """
    values = series.to_numpy(dtype=float)
    n = len(values)
    swings: list[Swing] = []
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        if np.isnan(window).any():
            continue
        center = window[order]
        if center == window.max() and np.argmax(window) == order:
            swings.append((i, float(center), "H"))
        elif center == window.min() and np.argmin(window) == order:
            swings.append((i, float(center), "L"))
    return swings


def _nearest(swings: list[Swing], position: int, tolerance: int) -> Swing | None:
    """Diem cung loai (H/L) trong `swings` gan `position` nhat, trong nguong `tolerance`."""
    candidates = [s for s in swings if abs(s[0] - position) <= tolerance]
    if not candidates:
        return None
    return min(candidates, key=lambda s: abs(s[0] - position))


def detect_divergence(
    frame: pd.DataFrame, oscillator: pd.Series, lookback: int = 60, order: int = 5
) -> dict:
    """So sanh hai day (hoac hai dinh) gan nhat cua gia voi chi bao tuong ung.

    `oscillator` phai cung do dai va cung chi so voi `frame` (vi du MACD hist
    hoac RSI). Chi xet trong `lookback` phien gan nhat.

    Tra ve dict: type ("bullish"/"bearish"/None), strength (do lech tuong doi
    giua hai day/dinh chi bao, 0 neu khong co phan ky), swing_points (dict
    "price" va "oscillator", danh sach Swing dung de ve minh hoa/kiem tra).
    """
    window = frame.tail(lookback).reset_index(drop=True)
    osc_window = oscillator.tail(lookback).reset_index(drop=True)
    tolerance = order * 2

    price_swings = find_swings(window["close"], order=order)
    osc_swings = find_swings(osc_window, order=order)
    price_lows = [s for s in price_swings if s[2] == "L"]
    price_highs = [s for s in price_swings if s[2] == "H"]
    osc_lows = [s for s in osc_swings if s[2] == "L"]
    osc_highs = [s for s in osc_swings if s[2] == "H"]

    result = {
        "type": None,
        "strength": 0.0,
        "swing_points": {"price": price_swings, "oscillator": osc_swings},
    }

    if len(price_lows) >= 2:
        (pos1, price1, _), (pos2, price2, _) = price_lows[-2], price_lows[-1]
        osc1 = _nearest(osc_lows, pos1, tolerance)
        osc2 = _nearest(osc_lows, pos2, tolerance)
        if osc1 and osc2 and price2 < price1 and osc2[1] > osc1[1]:
            result["type"] = "bullish"
            result["strength"] = _relative_strength(osc1[1], osc2[1])
            return result

    if len(price_highs) >= 2:
        (pos1, price1, _), (pos2, price2, _) = price_highs[-2], price_highs[-1]
        osc1 = _nearest(osc_highs, pos1, tolerance)
        osc2 = _nearest(osc_highs, pos2, tolerance)
        if osc1 and osc2 and price2 > price1 and osc2[1] < osc1[1]:
            result["type"] = "bearish"
            result["strength"] = _relative_strength(osc1[1], osc2[1])
            return result

    return result


def _relative_strength(first: float, second: float) -> float:
    """Do lech tuong doi giua hai gia tri chi bao, dung lam thuoc do "manh yeu"."""
    base = abs(first) if first else 1.0
    return float(abs(second - first) / base)
