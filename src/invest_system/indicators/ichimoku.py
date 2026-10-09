"""Ichimoku Kinko Hyo - day du nam thanh phan, khong cat bot.

    Tenkan-sen  (Chuyen)   = (max(High,9)  + min(Low,9))  / 2
    Kijun-sen   (Co so)    = (max(High,26) + min(Low,26)) / 2
    Senkou A    (Dan A)    = (Tenkan + Kijun) / 2,  dich toi truoc 26 phien
    Senkou B    (Dan B)    = (max(High,52) + min(Low,52)) / 2,  dich toi truoc 26 phien
    Chikou      (Tre)      = Close,  dich lui 26 phien
    Kumo (may)             = vung giua Senkou A va Senkou B

Trong pandas, "dich toi truoc" (Senkou) dung Series.shift(+shift): gia tri
tinh tai thoi diem t-shift duoc dat vao vi tri t, tuc la may hien tren bieu
do TAI thoi diem hien tai chinh la may duoc tinh tu Tenkan/Kijun cua shift
phien TRUOC do. "Dich lui" (Chikou) dung Series.shift(-shift): gia dong cua
tai t duoc dat vao vi tri t-shift, hien thi gia hom nay lui ve qua khu.

Ve tham so 9-26-52: day la bo so GOC tu thi truong Nhat thap nien 1960, dua
tren TUAN LAM VIEC 6 NGAY (Kijun ~ mot nua thang lam viec, Senkou B ~ hai
thang lam viec). Thi truong hien nay giao dich 5 ngay/tuan, nen mot so nguon
de xuat bo so hieu chinh (7, 22, 44) de giu nguyen ty le thoi gian thuc te.
Nhom chon bo so qua config/settings.yaml (indicators.ichimoku_preset), mac
dinh dung bo goc vi day la chuan pho bien nhat va de doi chieu khi bao ve
do an; bo hieu chinh duoc giu san cho ai muon kiem thu so sanh.
"""
from __future__ import annotations

import pandas as pd

from .common import atr, detect_cross

ICHIMOKU_PRESETS: dict[str, tuple[int, int, int]] = {
    # (tenkan, kijun, senkou_b)
    "goc_nhat_6ngay": (9, 26, 52),
    "hieu_chinh_5ngay": (7, 22, 44),
}


def _donchian_mid(high: pd.Series, low: pd.Series, period: int) -> pd.Series:
    return (high.rolling(period, min_periods=period).max()
            + low.rolling(period, min_periods=period).min()) / 2


def _classify_vs_kumo(close: float, senkou_a: float, senkou_b: float) -> str:
    top, bottom = max(senkou_a, senkou_b), min(senkou_a, senkou_b)
    if close > top:
        return "tren_may"
    if close < bottom:
        return "duoi_may"
    return "trong_may"


def _kumo_break_bars(
    close: pd.Series, senkou_a: pd.Series, senkou_b: pd.Series
) -> int | None:
    """So phien ke tu khi gia VUOT LEN/XUONG khoi may VA GIU NGUYEN trang
    thai do lien tuc den phien cuoi. None neu dang trong may, hoac khong du
    du lieu de xac dinh (dung cho bo loc "dot pha" - dieu kien can tin hieu
    MOI, khong phai da vuot may tu hang chuc phien truoc).
    """
    valid = close.notna() & senkou_a.notna() & senkou_b.notna()
    idx = close.index[valid]
    if len(idx) < 2:
        return None

    zones = [_classify_vs_kumo(close[i], senkou_a[i], senkou_b[i]) for i in idx]
    current_zone = zones[-1]
    if current_zone == "trong_may":
        return None

    count = 0
    for zone in reversed(zones):
        if zone != current_zone:
            break
        count += 1
    return count - 1  # 0 = vua vuot dung phien nay


def ichimoku(
    frame: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, shift: int = 26
) -> pd.DataFrame:
    """Tra ve DataFrame cung do dai voi `frame`, gom:

      tenkan, kijun            duong Chuyen, Co so (chua dich)
      senkou_a, senkou_b       may Dan A/B, DA DICH toi truoc `shift` phien
      senkou_a_base, senkou_b_base   may Dan A/B TRUOC khi dich (dung de xet
                                      doan may sap hien ra phia truoc, xem
                                      ichimoku_state -> kumo_twist)
      chikou                   duong Tre, da dich lui `shift` phien
    """
    high, low, close = frame["high"], frame["low"], frame["close"]

    tenkan_line = _donchian_mid(high, low, tenkan)
    kijun_line = _donchian_mid(high, low, kijun)
    senkou_a_base = (tenkan_line + kijun_line) / 2
    senkou_b_base = _donchian_mid(high, low, senkou_b)

    return pd.DataFrame(
        {
            "tenkan": tenkan_line,
            "kijun": kijun_line,
            "senkou_a": senkou_a_base.shift(shift),
            "senkou_b": senkou_b_base.shift(shift),
            "senkou_a_base": senkou_a_base,
            "senkou_b_base": senkou_b_base,
            "chikou": close.shift(-shift),
        },
        index=frame.index,
    )


def ichimoku_state(
    frame: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, shift: int = 26
) -> dict:
    """Tom tat trang thai Ichimoku tai phien cuoi cua `frame`.

    Tra ve dict:
      price_vs_kumo   "tren_may" / "trong_may" / "duoi_may"
      tk_cross        (huong, bars_since, do_manh) giao cat Tenkan/Kijun;
                       do_manh = "manh" neu cat tren may, "trung_tinh" neu
                       cat trong may, "yeu" neu cat duoi may
      kumo_twist      True neu doan may PHIA TRUOC (chua hien ra) co Senkou A
                       cat Senkou B trong `shift` phien toi (doi mau may)
      chikou_free     True neu gia hien tai cao hon gia `shift` phien truoc
                       (Chikou nam thoang phia tren gia qua khu)
      kumo_thickness  do day may hien tai, chuan hoa theo ATR14
      kumo_break_bars So phien ke tu khi gia vuot LEN/XUONG khoi may VA GIU
                       NGUYEN trang thai do lien tuc den gio - None neu dang
                       trong may. 0 nghia la vua vuot dung phien nay.
    """
    lines = ichimoku(frame, tenkan, kijun, senkou_b, shift)
    close = frame["close"]

    senkou_a = lines["senkou_a"].dropna()
    senkou_b_col = lines["senkou_b"].dropna()
    if senkou_a.empty or senkou_b_col.empty:
        return {
            "price_vs_kumo": None, "tk_cross": (None, None, None),
            "kumo_twist": None, "chikou_free": None, "kumo_thickness": None,
            "kumo_break_bars": None,
        }

    last_close = float(close.iloc[-1])
    top = max(float(senkou_a.iloc[-1]), float(senkou_b_col.iloc[-1]))
    bottom = min(float(senkou_a.iloc[-1]), float(senkou_b_col.iloc[-1]))
    if last_close > top:
        price_vs_kumo = "tren_may"
    elif last_close < bottom:
        price_vs_kumo = "duoi_may"
    else:
        price_vs_kumo = "trong_may"

    cross, bars_since = detect_cross(lines["tenkan"], lines["kijun"])
    if cross is None:
        strength = None
    elif price_vs_kumo == "tren_may":
        strength = "manh"
    elif price_vs_kumo == "trong_may":
        strength = "trung_tinh"
    else:
        strength = "yeu"

    forward_a = lines["senkou_a_base"].tail(shift)
    forward_b = lines["senkou_b_base"].tail(shift)
    twist_cross, _ = detect_cross(forward_a, forward_b)
    kumo_twist = twist_cross is not None

    chikou_free = None
    if len(close) > shift:
        chikou_free = bool(last_close > float(close.iloc[-1 - shift]))

    atr_series = atr(frame).dropna()
    kumo_thickness = None
    if not atr_series.empty and atr_series.iloc[-1]:
        kumo_thickness = abs(float(senkou_a.iloc[-1]) - float(senkou_b_col.iloc[-1])) / float(
            atr_series.iloc[-1]
        )

    break_bars = _kumo_break_bars(close, lines["senkou_a"], lines["senkou_b"])

    return {
        "price_vs_kumo": price_vs_kumo,
        "tk_cross": (cross, bars_since, strength),
        "kumo_twist": kumo_twist,
        "chikou_free": chikou_free,
        "kumo_thickness": kumo_thickness,
        "kumo_break_bars": break_bars,
    }
