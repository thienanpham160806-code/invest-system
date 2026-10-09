"""Danh gia tong quan vi mo va tac dong len NGANH cua doanh nghiep.

Cach lam (minh bach, giai thich duoc khi bao ve):
  1. Moi chi tieu vi mo -> do lech chuan hoa z so voi muc "trung tinh" cua VN
     (BASELINES), cat trong [-2, 2].
  2. Diem vi mo chung = 50 + 25 x trung binh co trong so (dau +/- theo y nghia
     kinh te: GDP cao tot, lam phat/lai suat cao xau...).
  3. Tac dong len nganh = cung cong thuc nhung trong so lay tu ma tran do nhay
     config/sector_map.yaml: macro_sensitivity (vd BDS rat nhay voi lai suat).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..data.company import sector_config
from ..data.macro import INDICATORS, MacroData

# muc trung tinh (khong tot khong xau) va do rong 1 don vi z
BASELINES = {
    "gdp_growth": (6.0, 1.5),
    "cpi": (3.5, 1.5),
    "policy_rate": (4.5, 1.0),
    "credit_growth": (13.0, 3.0),
    "usd_vnd": (2.0, 2.0),  # % mat gia VND / nam
}
GENERAL_WEIGHTS = {"gdp_growth": 1.0, "cpi": -0.6, "policy_rate": -0.6, "credit_growth": 0.6,
                   "usd_vnd": -0.4}


@dataclass
class MacroResult:
    table: list[dict] = field(default_factory=list)   # dong cho bang PDF
    z: dict = field(default_factory=dict)
    score: float | None = None          # diem vi mo chung 0-100
    sector_score: float | None = None   # tac dong len nganh 0-100
    sector_label: str = ""
    commentary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _fx_change(data: MacroData) -> float | None:
    ytd = data.latest.get("usd_vnd_ytd")
    if ytd:  # so NHNN moi nhat (nhap tay) uu tien hon chuoi nam World Bank
        return float(ytd["value"])
    hist = data.history.get("usd_vnd")
    if hist is None or len(hist.dropna()) < 2:
        return None
    h = hist.dropna()
    return float((h.iloc[-1] / h.iloc[-2] - 1) * 100)


def _weighted(z: dict, weights: dict) -> float | None:
    num = den = 0.0
    for k, w in weights.items():
        if k in z:
            num += w * z[k]
            den += abs(w)
    return None if den == 0 else float(np.clip(50 + 25 * num / den, 0, 100))


def analyze_macro(data: MacroData, company_type: str) -> MacroResult:
    res = MacroResult(notes=list(data.notes))
    for key, (label, unit, _code) in INDICATORS.items():
        item = data.latest.get(key)
        if not item:
            continue
        res.table.append({"key": key, "label": label, "value": item["value"], "unit": unit,
                          "period": item["period"], "source": item["source"]})
    values = {r["key"]: r["value"] for r in res.table}
    fx = _fx_change(data)
    for key, (base, scale) in BASELINES.items():
        v = fx if key == "usd_vnd" else values.get(key)
        if v is not None:
            res.z[key] = float(np.clip((v - base) / scale, -2, 2))
    res.score = _weighted(res.z, GENERAL_WEIGHTS)
    sens = sector_config()["macro_sensitivity"].get(company_type, {})
    res.sector_score = _weighted(res.z, sens)
    res.sector_label = sector_config()["company_types"][company_type]["label"]
    res.commentary = _commentary(values, fx, res, company_type)
    return res


def _commentary(values: dict, fx: float | None, res: MacroResult, company_type: str) -> list[str]:
    out = []
    g = values.get("gdp_growth")
    if g is not None:
        tone = "cao hơn" if g > 6.5 else ("tương đương" if g >= 5.5 else "thấp hơn")
        out.append(f"Tăng trưởng GDP đạt {g:.2f}%, {tone} mức tăng trưởng tiềm năng ~6% của "
                   "Việt Nam — " + ("hỗ trợ nhu cầu tiêu dùng và đầu tư." if g > 6.5 else
                                   "môi trường tăng trưởng ở mức trung tính." if g >= 5.5 else
                                   "cầu nội địa chịu áp lực."))
    c = values.get("cpi")
    if c is not None:
        out.append(f"Lạm phát CPI {c:.2f}%, " + ("dưới ngưỡng mục tiêu ~4,5% của Quốc hội, tạo dư địa "
                   "cho chính sách tiền tệ nới lỏng." if c < 4.0 else
                   "tiệm cận ngưỡng mục tiêu, NHNN khó nới lỏng thêm." if c < 4.5 else
                   "vượt ngưỡng mục tiêu, rủi ro thắt chặt tiền tệ."))
    r = values.get("policy_rate")
    if r is not None:
        out.append(f"Lãi suất tái cấp vốn {r:.2f}% — " + ("mặt bằng lãi suất thấp, hỗ trợ chi phí vốn "
                   "và định giá cổ phiếu." if r <= 4.5 else "mặt bằng lãi suất cao, gây áp lực lên "
                   "chi phí vốn và định giá."))
    cg = values.get("credit_growth")
    if cg is not None:
        out.append(f"Tăng trưởng tín dụng {cg:.2f}% — " + ("dòng vốn vào nền kinh tế mạnh."
                   if cg >= 13 else "dòng vốn tín dụng chậm lại."))
    if fx is not None:
        out.append(f"Tỷ giá USD/VND biến động {fx:+.2f}% so với kỳ trước — " +
                   ("áp lực tỷ giá đáng kể với DN nhập khẩu/vay ngoại tệ." if fx > 3 else
                    "tỷ giá ổn định."))
    if res.sector_score is not None:
        verdict = ("THUẬN LỢI" if res.sector_score >= 60 else "TRUNG TÍNH"
                   if res.sector_score >= 40 else "BẤT LỢI")
        out.append(f"Tổng hợp theo độ nhạy của nhóm {res.sector_label.lower()}: môi trường vĩ mô "
                   f"{verdict} cho ngành (điểm {res.sector_score:.0f}/100).")
    return out
