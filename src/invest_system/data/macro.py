"""Du lieu vi mo Viet Nam.

Hai nguon, ket hop:
  1. config/macro_vn.csv - so lieu NHOM TU DIEN tu GSO / NHNN, moi dong co cot
     nguon + ngay cong bo. Day la nguon UU TIEN (moi nhat, chinh thuc).
  2. World Bank Open Data API (khong can key) - chuoi dai han theo nam, dung
     de ve bieu do va bu cho chi tieu chua dien. Do tre ~1 nam.
Tin vi mo (RSS CafeF/VnExpress) lay qua data/macro_news.py (tai su dung).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import requests

from ..config import CONFIG_DIR
from ..logging_conf import get_logger
from ..provenance import SourceLog
from . import cache

log = get_logger(__name__)

MACRO_CSV = CONFIG_DIR / "macro_vn.csv"

INDICATORS = {
    # key: (nhan tieng Viet, don vi, ma World Bank)
    "gdp_growth": ("Tăng trưởng GDP thực", "%", "NY.GDP.MKTP.KD.ZG"),
    "cpi": ("Lạm phát CPI bình quân", "%", "FP.CPI.TOTL.ZG"),
    "policy_rate": ("Lãi suất tái cấp vốn (NHNN)", "%", None),
    "lending_rate": ("Lãi suất cho vay bình quân", "%", "FR.INR.LEND"),
    "credit_growth": ("Tăng trưởng tín dụng", "%", None),
    "usd_vnd": ("Tỷ giá USD/VND", "VND", "PA.NUS.FCRF"),
    "gov_bond_10y": ("Lợi suất TPCP 10 năm", "%", None),
    "gdp_growth_ytd": ("GDP lũy kế từ đầu năm", "%", None),
    "cpi_yoy": ("CPI tháng gần nhất (so cùng kỳ)", "%", None),
    "credit_growth_ytd": ("Tín dụng từ đầu năm", "%", None),
    "usd_vnd_ytd": ("Tỷ giá trung tâm thay đổi từ đầu năm", "%", None),
    "private_credit_gdp": ("Tín dụng tư nhân/GDP", "%", "FS.AST.PRVT.GD.ZS"),
}
_WB_URL = "https://api.worldbank.org/v2/country/VNM/indicator/{code}?format=json&per_page=60"


@dataclass
class MacroData:
    latest: dict[str, dict] = field(default_factory=dict)       # key -> {value, period, source, as_of}
    history: dict[str, pd.Series] = field(default_factory=dict)  # key -> Series(nam -> gia tri)
    notes: list[str] = field(default_factory=list)


def _period_key(period: str) -> tuple:
    text = str(period)
    year = int(text[:4]) if text[:4].isdigit() else 0
    sub = text[4:] or "Z"  # nam day du (Z) xep sau quy (Q1..Q4) cung nam
    return (year, sub)


def load_manual(path=MACRO_CSV) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"period": str}, encoding="utf-8-sig")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def fetch_world_bank(code: str) -> pd.Series:
    key = f"macro/wb/{code}"
    cached = cache.read_frame(key, max_age=7 * 86400)
    if cached is not None and not cached.empty:
        return cached.set_index("year")["value"]
    resp = requests.get(_WB_URL.format(code=code), timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 and payload[1] else []
    data = [(int(r["date"]), float(r["value"])) for r in rows if r.get("value") is not None]
    frame = pd.DataFrame(data, columns=["year", "value"]).sort_values("year")
    if not frame.empty:
        cache.write_frame(key, frame)
    return frame.set_index("year")["value"]


def load_macro(log_: SourceLog | None = None, demo_mode: bool = False,
               world_bank: bool = True) -> MacroData:
    data = MacroData()
    manual = load_manual()
    if demo_mode:
        from .demo import macro_frame

        manual = macro_frame()

    # 1) World Bank: chuoi lich su
    if not demo_mode and world_bank:
        for key, (label, _unit, code) in INDICATORS.items():
            if code is None:
                continue
            try:
                series = fetch_world_bank(code)
                if not series.empty:
                    data.history[key] = series
                    if log_:
                        log_.add(f"Vĩ mô: {label}", "World Bank Open Data API",
                                 str(int(series.index.max())))
            except Exception as exc:  # noqa: BLE001 - mat mang thi dung file tay
                log.info("World Bank %s loi: %s", code, exc)
        if not data.history:
            data.notes.append("Không gọi được World Bank API — chỉ dùng số liệu nhập tay.")

    # 2) So nhap tay: lay ky MOI NHAT co gia tri cho tung chi tieu
    if not manual.empty:
        filled = manual.dropna(subset=["value"])
        missing = manual[manual["value"].isna()]["indicator"].unique().tolist()
        if missing:
            data.notes.append(
                "Chưa nhập số liệu mới nhất cho: " + ", ".join(INDICATORS.get(m, (m,))[0]
                                                              for m in missing)
                + " (config/macro_vn.csv).")
        for key, grp in filled.groupby("indicator"):
            grp = grp.assign(_k=grp["period"].map(_period_key)).sort_values("_k")
            row = grp.iloc[-1]
            data.latest[key] = {"value": float(row["value"]), "period": str(row["period"]),
                                "source": str(row["source"]), "as_of": str(row.get("as_of", ""))}
            hist = grp[grp["period"].str.fullmatch(r"\d{4}")]
            if not hist.empty:
                manual_series = pd.Series(hist["value"].to_numpy(),
                                          index=hist["period"].astype(int))
                base = data.history.get(key, pd.Series(dtype=float))
                data.history[key] = manual_series.combine_first(base).sort_index()
        if log_:
            log_.add("Vĩ mô: số liệu nhập tay", "config/macro_vn.csv (GSO/NHNN)"
                     if not demo_mode else "DỮ LIỆU MẪU (giả lập)",
                     note=f"{len(filled)} dòng có giá trị")

    # 3) Bu chi tieu chua co bang gia tri WB moi nhat
    for key, series in data.history.items():
        if key not in data.latest and not series.empty:
            data.latest[key] = {"value": float(series.iloc[-1]), "period": str(series.index[-1]),
                                "source": "World Bank Open Data", "as_of": str(series.index[-1])}
    return data
