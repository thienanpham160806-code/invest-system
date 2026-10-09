"""Boi canh vi mo QUOC TE (FRED) va gop voi diem vi mo trong nuoc.

Cung cach lam voi analysis/macro.py: moi bien -> z so voi muc "trung tinh",
cat [-2, 2]; diem = 50 + 25 x trung binh co trong so. Muc trung tinh, do rong
va trong so la GIA DINH DINH TINH cua nhom (ghi trong bao cao), khong uoc luong
tu du lieu:

  bien        do theo        trung tinh   1 z      y nghia voi chung khoan VN
  fed_funds   muc (%)        3,0          1,5 dpt  lai suat USD cao -> rut von EM, ap luc ty gia
  ust_10y     muc (%)        4,0          1,0 dpt  chi phi von toan cau, dinh gia EM
  usd_broad   doi 3 thang %  0            3%       USD manh -> VND mat gia, von ngoai rut
  brent       doi 3 thang %  0            15%      chi phi dau vao, lam phat (dau khi huong loi)
  vix         muc (diem)     18           6        khau vi rui ro toan cau

Diem vi mo cuoi = (1 - w) x trong nuoc + w x quoc te, w = macro.intl_weight
(config/settings.yaml, mac dinh 0,30); thieu mot phan thi dung phan con lai.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings
from ..data.company import sector_config
from .macro import MacroResult

# key: (cach do, trung tinh, do rong 1 z, trong so diem chung)
INTL_MODEL: dict[str, tuple[str, float, float, float]] = {
    "fed_funds": ("level", 3.0, 1.5, -0.6),
    "ust_10y": ("level", 4.0, 1.0, -0.8),
    "usd_broad": ("chg_3m", 0.0, 0.03, -0.7),
    "brent": ("chg_3m", 0.0, 0.15, -0.3),
    "vix": ("level", 18.0, 6.0, -0.8),
}
RATE_KEYS = {"fed_funds", "fed_funds_daily", "ust_10y"}    # doi tinh bang diem phan tram
WINDOWS = {"chg_1m": 30, "chg_3m": 91, "chg_1y": 365}       # ngay lich
DEFAULT_WEIGHT = 0.30


@dataclass
class IntlResult:
    rows: list[dict] = field(default_factory=list)   # moi bien: gia tri, thay doi, sparkline, nhan dinh
    z: dict = field(default_factory=dict)
    score: float | None = None
    sector_score: float | None = None
    commentary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _value_on_or_before(values: pd.Series, when: pd.Timestamp) -> float | None:
    past = values[values.index <= when]
    return None if past.empty else float(past.iloc[-1])


def describe(key: str, values: pd.Series) -> dict:
    """Gia tri moi nhat, thay doi 1T/3T/1N (lai suat: diem %, con lai: %), sparkline tuan 1 nam."""
    values = values.dropna().sort_index()
    last_date = values.index[-1]
    last = float(values.iloc[-1])
    is_rate = key in RATE_KEYS
    out = {"key": key, "value": last, "date": last_date.strftime("%Y-%m-%d"),
           "change_unit": "điểm %" if is_rate else "%"}
    for name, days in WINDOWS.items():
        base = _value_on_or_before(values, last_date - pd.Timedelta(days=days))
        if base is None or (not is_rate and base == 0):
            out[name] = None
        else:
            out[name] = last - base if is_rate else last / base - 1
    year = values[values.index > last_date - pd.Timedelta(days=365)]
    weekly = year.resample("W").last().dropna()
    out["spark"] = [{"t": d.strftime("%Y-%m-%d"), "v": float(v)} for d, v in weekly.items()]
    return out


def _z(key: str, row: dict) -> float | None:
    basis, neutral, width, _ = INTL_MODEL[key]
    value = row["value"] if basis == "level" else row.get(basis)
    if value is None:
        return None
    return float(np.clip((value - neutral) / width, -2, 2))


def _weighted(z: dict, weights: dict) -> float | None:
    num = den = 0.0
    for k, w in weights.items():
        if k in z:
            num += w * z[k]
            den += abs(w)
    return None if den == 0 else float(np.clip(50 + 25 * num / den, 0, 100))


def _reading(key: str, row: dict) -> str:
    v, c3 = row["value"], row.get("chg_3m")
    if key == "fed_funds":
        trend = "" if c3 is None else (" và đang giảm" if c3 < -0.1 else " và đang tăng" if c3 > 0.1 else " và đi ngang")
        return (f"Lãi suất Fed {v:.2f}%{trend} — "
                + ("mặt bằng lãi suất USD cao, áp lực lên tỷ giá và dòng vốn ngoại." if v >= 4 else
                   "mặt bằng lãi suất USD trung tính." if v >= 2 else "lãi suất USD thấp, thuận lợi cho dòng vốn vào thị trường mới nổi."))
    if key == "ust_10y":
        return (f"Lợi suất TPCP Mỹ 10 năm {v:.2f}% — "
                + ("chi phí vốn toàn cầu cao, gây áp lực định giá cổ phiếu." if v >= 4.5 else
                   "chi phí vốn toàn cầu trung tính." if v >= 3 else "chi phí vốn toàn cầu thấp."))
    if key == "usd_broad":
        if c3 is None:
            return f"Chỉ số USD rộng {v:.1f} điểm."
        return (f"Chỉ số USD rộng {v:.1f} điểm, {c3:+.1%} trong 3 tháng — "
                + ("USD mạnh lên, áp lực mất giá VND và rút vốn ngoại." if c3 > 0.02 else
                   "USD yếu đi, giảm áp lực tỷ giá." if c3 < -0.02 else "USD ổn định."))
    if key == "brent":
        if c3 is None:
            return f"Giá dầu Brent {v:.1f} USD/thùng."
        return (f"Giá dầu Brent {v:.1f} USD/thùng, {c3:+.1%} trong 3 tháng — "
                + ("chi phí đầu vào và lạm phát tăng; doanh nghiệp dầu khí hưởng lợi." if c3 > 0.10 else
                   "chi phí nhiên liệu giảm, có lợi cho vận tải, hàng không; dầu khí bất lợi." if c3 < -0.10 else
                   "giá dầu ổn định."))
    if key == "vix":
        return (f"VIX {v:.1f} điểm — "
                + ("tâm lý toàn cầu căng thẳng, rủi ro bán ròng ở thị trường mới nổi." if v >= 25 else
                   "biến động toàn cầu trên trung bình." if v >= 20 else "tâm lý toàn cầu ổn định."))
    return ""


def sensitivity(company_type: str, icb1: str | None = None) -> dict:
    cfg = sector_config()
    weights = dict(cfg.get("macro_sensitivity_intl", {}).get(company_type, {}))
    weights.update(cfg.get("macro_sensitivity_intl_icb1", {}).get(icb1 or "", {}))
    return weights


def analyze_international(results: dict, company_type: str = "NON_FINANCIAL",
                          icb1: str | None = None, errors: dict | None = None) -> IntlResult:
    """`results`: {key: data.fred.FredResult} (FredClient.get_all)."""
    from ..data.fred import SERIES

    res = IntlResult(notes=[f"Không lấy được {SERIES[k].series_id}: {v}" for k, v in (errors or {}).items()
                            if k in SERIES])
    for key in INTL_MODEL:
        fr = results.get(key)
        if fr is None or fr.values.empty:
            continue
        row = describe(key, fr.values)
        spec = fr.series
        row.update({"label": spec.label, "unit": spec.unit, "series_id": spec.series_id, "url": spec.url,
                    "source": fr.source, "stale": fr.stale, "note": spec.note})
        z = _z(key, row)
        if z is not None:
            res.z[key] = z
            row["z"] = z
        row["reading"] = _reading(key, row)
        res.rows.append(row)
    res.score = _weighted(res.z, {k: m[3] for k, m in INTL_MODEL.items()})
    res.sector_score = _weighted(res.z, sensitivity(company_type, icb1))
    res.commentary = [r["reading"] for r in res.rows if r["reading"]]
    if res.score is not None:
        verdict = "THUẬN LỢI" if res.score >= 60 else "TRUNG TÍNH" if res.score >= 40 else "BẤT LỢI"
        res.commentary.append(f"Bối cảnh quốc tế {verdict} cho chứng khoán Việt Nam (điểm {res.score:.0f}/100).")
    return res


def intl_weight() -> float:
    return float(get_settings().get("macro.intl_weight", DEFAULT_WEIGHT))


def _blend(domestic: float | None, international: float | None, w: float) -> float | None:
    if domestic is None:
        return international
    if international is None:
        return domestic
    return float((1 - w) * domestic + w * international)


def blend(domestic: MacroResult, intl: IntlResult | None, weight: float | None = None) -> MacroResult:
    """Diem vi mo = (1 - w) x trong nuoc + w x quoc te; giu ca hai phan de hien thi."""
    w = intl_weight() if weight is None else weight
    out = dataclasses.replace(
        domestic,
        score=_blend(domestic.score, intl.score if intl else None, w),
        sector_score=_blend(domestic.sector_score, intl.sector_score if intl else None, w),
        commentary=list(domestic.commentary) + (list(intl.commentary) if intl else []),
        notes=list(domestic.notes) + (list(intl.notes) if intl else
                                      ["Không có dữ liệu quốc tế (FRED) — điểm vĩ mô chỉ gồm phần trong nước."]),
    )
    out.parts = {"domestic": {"score": domestic.score, "sector_score": domestic.sector_score, "weight": 1 - w},
                 "international": {"score": intl.score if intl else None,
                                   "sector_score": intl.sector_score if intl else None, "weight": w}}
    return out
