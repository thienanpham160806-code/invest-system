"""Diem tong hop top-down va khuyen nghi cuoi cung.

  Vi mo (tac dong len nganh) -> Nganh -> Chat luong -> Tang truong
  -> Dinh gia (upside) -> Ky thuat -> Cam xuc tin tuc
Moi nhom 0-100; trong so o config/settings.yaml: composite.weights. Nhom nao
khong tinh duoc thi bo, trong so chuan hoa lai (ghi ro trong bao cao).

Khuyen nghi theo UPSIDE cua gia muc tieu (cach CTCK VN lam), roi DIEU CHINH
1 bac theo diem tong hop: diem rat cao (>=70) nang 1 bac, diem thap (<40) ha 1 bac.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings

RATING_ORDER = ["BÁN", "KÉM KHẢ QUAN", "NẮM GIỮ", "KHẢ QUAN", "MUA"]
RATING_COLORS = {"MUA": "#0f7b4a", "KHẢ QUAN": "#3f9b5a", "NẮM GIỮ": "#c8901a",
                 "KÉM KHẢ QUAN": "#d4652f", "BÁN": "#b3261e"}
GROUP_LABELS = {"macro": "Vĩ mô – ngành", "sector": "Ngành", "quality": "Chất lượng tài chính",
                "growth": "Tăng trưởng", "valuation": "Định giá", "technical": "Kỹ thuật",
                "sentiment": "Tin tức"}


@dataclass
class CompositeResult:
    scores: dict[str, float] = field(default_factory=dict)
    weights_used: dict[str, float] = field(default_factory=dict)
    total: float | None = None
    base_rating: str | None = None
    rating: str | None = None
    rating_reason: str = ""
    thesis: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


def _clip(v):
    return float(np.clip(v, 0, 100))


def quality_score(ratios: pd.DataFrame, company_type: str) -> float | None:
    if ratios is None or ratios.empty:
        return None
    last = ratios.iloc[-1]
    parts = []
    roe = last.get("roe")
    if roe is not None and pd.notna(roe):
        parts.append(_clip(20 + roe * 300))            # ROE 10% -> 50, 20% -> 80
    if company_type == "BANK":
        cir = last.get("cir")
        if cir is not None and pd.notna(cir):
            parts.append(_clip(100 - (cir - 0.25) * 200))  # CIR 30% -> 90, 50% -> 50
        cc = last.get("credit_cost")
        if cc is not None and pd.notna(cc):
            parts.append(_clip(100 - cc * 3000))           # 1% -> 70, 2% -> 40
        eta = last.get("equity_to_assets")
        if eta is not None and pd.notna(eta):
            parts.append(_clip(eta * 800))                 # 8% -> 64, 10% -> 80
    else:
        de = last.get("debt_to_equity")
        if de is not None and pd.notna(de):
            parts.append(_clip(100 - de * 40))             # D/E 1 -> 60, 2 -> 20
        cr = last.get("current_ratio")
        if cr is not None and pd.notna(cr):
            parts.append(_clip(30 + (cr - 0.8) * 50))
        cfo = ratios["cfo_to_ni"].dropna().tail(3).mean() if "cfo_to_ni" in ratios else None
        if cfo is not None and pd.notna(cfo):
            parts.append(_clip(30 + cfo * 40))             # CFO/LN 1 -> 70
        ic = last.get("interest_coverage")
        if ic is not None and pd.notna(ic):
            parts.append(_clip(ic * 12))                   # 5 lan -> 60
    return float(np.mean(parts)) if parts else None


def growth_score(growth: dict) -> float | None:
    vals = [v for v in (growth.get("top_line_cagr"), growth.get("ni_cagr")) if v is not None]
    if not vals:
        return None
    return _clip(45 + np.mean(vals) * 250)                 # CAGR 10% -> 70


def valuation_score(upside: float | None) -> float | None:
    return None if upside is None else _clip(50 + upside * 150)  # +20% -> 80


def technical_score(total_score: float | None) -> float | None:
    return None if total_score is None else _clip(50 + total_score / 2)


def base_rating(upside: float | None) -> str | None:
    if upside is None:
        return None
    bands = get_settings().get("composite.rating_bands", {})
    for name in ("MUA", "KHẢ QUAN", "NẮM GIỮ", "KÉM KHẢ QUAN", "BÁN"):
        if upside >= bands.get(name, -1.0):
            return name
    return "BÁN"


def combine(scores: dict[str, float | None], upside: float | None,
            valuation_confidence: str | None = None,
            valuation_confidence_reason: str | None = None) -> CompositeResult:
    s = get_settings()
    weights = s.get("composite.weights", {})
    res = CompositeResult()
    usable = {k: v for k, v in scores.items() if v is not None and k in weights}
    total_w = sum(weights[k] for k in usable)
    res.scores = {k: float(v) for k, v in usable.items()}
    res.weights_used = {k: weights[k] / total_w for k in usable} if total_w else {}
    if total_w and len(usable) >= 3:  # it hon 3 nhom -> khong du co so cham diem tong hop
        res.total = float(sum(usable[k] * res.weights_used[k] for k in usable))
    res.base_rating = base_rating(upside)
    rating = res.base_rating
    if rating and res.total is not None:
        idx = RATING_ORDER.index(rating)
        if res.total >= s.get("composite.upgrade_score", 70) and idx < len(RATING_ORDER) - 1:
            rating = RATING_ORDER[idx + 1]
            res.rating_reason = (f"Upside xếp hạng '{res.base_rating}', nâng 1 bậc do điểm tổng "
                                 f"hợp cao ({res.total:.0f}/100).")
        elif res.total < s.get("composite.downgrade_score", 40) and idx > 0:
            rating = RATING_ORDER[idx - 1]
            res.rating_reason = (f"Upside xếp hạng '{res.base_rating}', hạ 1 bậc do điểm tổng "
                                 f"hợp thấp ({res.total:.0f}/100).")
        else:
            res.rating_reason = (f"Xếp hạng theo upside của giá mục tiêu; điểm tổng hợp "
                                 f"{res.total:.0f}/100 không đổi bậc.")
    if valuation_confidence == "THẤP":
        res.base_rating = None
        rating = "THEO DÕI"
        res.rating_reason = ("THEO DÕI – định giá chưa đủ tin cậy: " + valuation_confidence_reason
                             if valuation_confidence_reason else
                             "THEO DÕI – định giá chưa đủ tin cậy theo số phương pháp hợp lệ, độ phân tán hoặc upside.")
    if rating == "BÁN" and sum(v > 65 for v in res.scores.values()) >= 3:
        res.rating_reason += " Các nhóm điểm cơ bản đang tích cực nhưng khuyến nghị BÁN vẫn dựa trên upside định giá; cần cân nhắc xung đột tín hiệu này."
    res.rating = rating
    return res


def build_thesis_and_risks(ctx: dict, res: CompositeResult) -> None:
    """Luan diem dau tu & rui ro tu QUY TAC tren so lieu da tinh (khong bia)."""
    th, rk = [], []
    ratios: pd.DataFrame = ctx.get("ratios", pd.DataFrame())
    last = ratios.iloc[-1] if ratios is not None and not ratios.empty else pd.Series(dtype=float)
    growth, val = ctx.get("growth", {}), ctx.get("valuation")
    sector, macro, tech, sent = ctx.get("sector"), ctx.get("macro"), ctx.get("technical"), ctx.get("sentiment")
    ctype = ctx.get("company_type")

    from ..fmt import num, pct, price

    roe = last.get("roe")
    med_roe = sector.medians.get("roe") if sector else None
    if roe is not None and pd.notna(roe):
        if med_roe is not None and roe > med_roe * 1.1:
            th.append(f"Hiệu quả sinh lời vượt trội: ROE {pct(roe)} so với trung vị ngành {pct(med_roe)}.")
        elif med_roe is not None and roe < med_roe * 0.8:
            rk.append(f"ROE {pct(roe)} thấp hơn trung vị ngành {pct(med_roe)}.")
    if growth.get("ni_cagr") is not None:
        g = growth["ni_cagr"]
        (th if g > 0.10 else rk if g < 0 else th).append(
            f"LNST công ty mẹ CAGR {growth.get('years','')}: {pct(g)}"
            + (" — tăng trưởng mạnh." if g > 0.10 else " — suy giảm." if g < 0 else "."))
    if val is not None and val.upside is not None and getattr(val, "confidence", "CAO") != "THẤP":
        (th if val.upside > 0.10 else rk if val.upside < -0.05 else th).append(
            f"Giá mục tiêu {price(val.target_price)} đ/cp, "
            f"{'tiềm năng tăng' if val.upside >= 0 else 'thấp hơn giá hiện tại'} {pct(abs(val.upside))}.")
    elif val is not None and getattr(val, "confidence", None) == "THẤP":
        rk.append(f"Định giá chưa đủ tin cậy: {val.confidence_reason}. Khuyến nghị theo dõi, không xếp MUA/BÁN.")
    if ctype == "BANK":
        cc = last.get("credit_cost")
        if cc is not None and pd.notna(cc) and cc > 0.015:
            rk.append(f"Chi phí tín dụng cao ({pct(cc)}) — rủi ro chất lượng tài sản.")
        cir = last.get("cir")
        if cir is not None and pd.notna(cir) and cir < 0.35:
            th.append(f"Vận hành hiệu quả: CIR {pct(cir)}.")
    else:
        de = last.get("debt_to_equity")
        if de is not None and pd.notna(de) and de > 1.5:
            rk.append(f"Đòn bẩy cao: vay nợ/VCSH {num(de, 2)} lần.")
        ic = last.get("interest_coverage")
        if ic is not None and pd.notna(ic) and ic < 3:
            rk.append(f"Khả năng trả lãi yếu: EBIT/lãi vay {num(ic, 1)} lần.")
        if "cfo_to_ni" in ratios:
            cfo = ratios["cfo_to_ni"].dropna().tail(3).mean()
            if pd.notna(cfo) and cfo < 0.8:
                rk.append(f"Chất lượng lợi nhuận thấp: CFO/LNST bq 3 năm {num(cfo, 2)} lần.")
            elif pd.notna(cfo) and cfo > 1.0:
                th.append(f"Lợi nhuận chuyển hóa tốt thành tiền: CFO/LNST bq 3 năm {num(cfo, 2)} lần.")
    if macro is not None and macro.sector_score is not None:
        if macro.sector_score >= 60:
            th.append(f"Vĩ mô thuận lợi cho nhóm {macro.sector_label.lower()} "
                      f"(điểm {macro.sector_score:.0f}/100).")
        elif macro.sector_score < 40:
            rk.append(f"Vĩ mô bất lợi cho nhóm {macro.sector_label.lower()} "
                      f"(điểm {macro.sector_score:.0f}/100).")
    if sector is not None and sector.performance:
        s3, b3 = sector.performance.get("sector_ret_3m"), sector.performance.get("bench_ret_3m")
        if s3 is not None and b3 is not None:
            if s3 < 0 and b3 < 0:
                relation = "giảm ít hơn" if s3 > b3 else "giảm nhiều hơn" if s3 < b3 else "giảm tương đương"
                good = s3 > b3
            elif s3 > 0 and b3 > 0:
                relation = "tăng nhiều hơn" if s3 > b3 else "tăng ít hơn" if s3 < b3 else "tăng tương đương"
                good = s3 > b3
            else:
                relation = "diễn biến tốt hơn" if s3 > b3 else "diễn biến kém hơn" if s3 < b3 else "diễn biến tương đương"
                good = s3 > b3
            (th if good else rk).append(
                f"Ngành {relation} thị trường trong 3 tháng qua ({pct(s3, sign=True)} so với {pct(b3, sign=True)}).")
    if tech is not None:
        if tech.vetoed_by_kumo:
            rk.append("Kỹ thuật: giá nằm dưới mây Ichimoku — xu hướng ngắn hạn chưa ủng hộ.")
        elif tech.total_score > 20:
            th.append(f"Kỹ thuật tích cực (điểm hợp lưu MACD/RSI/Ichimoku {tech.total_score:+.0f}).")
        elif tech.total_score < -20:
            rk.append(f"Kỹ thuật tiêu cực (điểm hợp lưu {tech.total_score:+.0f}).")
    if sent is not None and sent.score is not None:
        if sent.score < -0.2:
            rk.append(f"Tin tức gần đây nghiêng tiêu cực ({sent.n_neg} tin tiêu cực).")
        elif sent.score > 0.2:
            th.append(f"Dòng tin gần đây tích cực ({sent.n_pos} tin tích cực).")
    fin_risks = ctx.get("fintext_risks") or []
    for r in fin_risks[:2]:
        rk.append(r)
    rk.append("Rủi ro chung: biến động thị trường, thay đổi chính sách tiền tệ/tài khóa, "
              "sai lệch giả định định giá.")
    res.thesis, res.risks = th[:6], rk[:7]
