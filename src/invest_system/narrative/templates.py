"""Nhan dinh bang QUY TAC + MAU CAU (luon chay duoc, khong can API).

Moi cau deu dien so tu ket qua da tinh -> truy duoc ve dung dong code/so lieu.
narrative/llm.py co the viet lai van phong muot hon, nhung CHI tu cac so nay.
"""
from __future__ import annotations

import pandas as pd

from ..analysis.valuation import SCENARIO_LABELS
from ..fmt import num, pct, price, times


def sector_paragraphs(ctx: dict) -> list[str]:
    sector, info = ctx["sector"], ctx["info"]
    out = []
    peers = sector.peers_table
    n = int((~peers["is_target"]).sum()) if not peers.empty and "is_target" in peers else 0
    label = info.industry or info.type_label
    if n:
        med = sector.medians
        out.append(f"Nhóm so sánh gồm {n} doanh nghiệp cùng ngành {label} "
                   f"({', '.join(peers[~peers['is_target']]['symbol'])}). Trung vị nhóm: "
                   f"P/E {times(med.get('pe'), 1)}, P/B {times(med.get('pb'), 2)}, "
                   f"ROE {pct(med.get('roe'))}.")
    perf = sector.performance
    if perf:
        out.append(f"Chỉ số ngành tự tính (bình quân giá các mã trong nhóm) biến động "
                   f"{pct(perf.get('sector_ret_3m'), sign=True)} trong 3 tháng và "
                   f"{pct(perf.get('sector_ret_1y'), sign=True)} trong 1 năm, so với "
                   f"{pct(perf.get('bench_ret_3m'), sign=True)} / {pct(perf.get('bench_ret_1y'), sign=True)} "
                   "của chỉ số thị trường.")
    pos = sector.position
    if "roe" in pos:
        out.append(f"Vị thế {info.symbol}: ROE nằm ở phân vị {pos['roe']*100:.0f} của nhóm"
                   + (f", tăng trưởng LN ở phân vị {pos['ni_cagr']*100:.0f}" if "ni_cagr" in pos else "")
                   + (f", P/E ở phân vị {pos['pe']*100:.0f} (càng thấp càng rẻ)" if "pe" in pos else "")
                   + ".")
    out.extend(sector.notes)
    return out


def company_paragraphs(ctx: dict) -> list[str]:
    ratios: pd.DataFrame = ctx["ratios"]
    growth, ctype, fin = ctx["growth"], ctx["company_type"], ctx["fin"]
    out = []
    if fin.empty:
        return ["Không có dữ liệu BCTC để phân tích doanh nghiệp."]
    yl = fin.last_year()
    if ctype == "BANK":
        out.append(f"Năm {yl}, tổng thu nhập hoạt động đạt {num((fin.get('total_operating_income') or 0)/1e9)} tỷ đồng, "
                   f"LNST công ty mẹ {num((fin.get('net_income_parent') or 0)/1e9)} tỷ đồng; "
                   f"CAGR {growth['years']}: thu nhập {pct(growth.get('top_line_cagr'))}, "
                   f"LNST {pct(growth.get('ni_cagr'))}.")
        if not ratios.empty:
            r = ratios.iloc[-1]
            out.append(f"Biên lãi thuần (NIM xấp xỉ) {pct(r.get('nim'), 2)}, CIR {pct(r.get('cir'))}, "
                       f"chi phí tín dụng {pct(r.get('credit_cost'), 2)}, LDR {pct(r.get('ldr'))}, "
                       f"ROE {pct(r.get('roe'))}.")
    else:
        out.append(f"Năm {yl}, doanh thu thuần đạt {num((fin.get('revenue') or 0)/1e9)} tỷ đồng, "
                   f"LNST công ty mẹ {num((fin.get('net_income_parent') or 0)/1e9)} tỷ đồng; "
                   f"CAGR {growth['years']}: doanh thu {pct(growth.get('top_line_cagr'))}, "
                   f"LNST {pct(growth.get('ni_cagr'))}.")
        if not ratios.empty:
            r = ratios.iloc[-1]
            out.append(f"Biên LN gộp {pct(r.get('gross_margin'))}, biên ròng {pct(r.get('net_margin'))}, "
                       f"ROE {pct(r.get('roe'))}, ROA {pct(r.get('roa'))}. Vay nợ/VCSH "
                       f"{times(r.get('debt_to_equity'))}, thanh toán hiện hành {times(r.get('current_ratio'))}, "
                       f"EBIT/lãi vay {times(r.get('interest_coverage'), 1)}.")
    if ctx.get("fintext_commentary"):
        out.append(ctx["fintext_commentary"])
    return out


def valuation_paragraphs(ctx: dict) -> list[str]:
    val, info = ctx["valuation"], ctx["info"]
    out = []
    if not val.methods:
        return val.skipped or ["Không định giá được."]
    used = [m for m in val.methods if m.weight > 0]
    out.append(f"Với đặc thù {info.type_label.lower()}, hệ thống sử dụng "
               + ", ".join(f"{m.label} ({m.weight*100:.0f}%)" for m in used) + ".")
    a = val.assumptions
    out.append(f"Chi phí vốn CSH Ke = {pct(a['rf'])} + β {num(a['beta'], 2)} × {pct(a['erp'])} = "
               f"{pct(a['ke'])}" + (f"; WACC {pct(a.get('wacc'))}" if a.get("wacc") else "")
               + f"; tăng trưởng giai đoạn đầu {pct(a.get('growth'))}.")
    t = val.target
    out.append(f"Giá mục tiêu kịch bản cơ sở {price(t.get('base'))} đ/cp "
               f"(bi quan {price(t.get('bear'))} – lạc quan {price(t.get('bull'))}), "
               f"tương ứng upside {pct(val.upside, sign=True)} so với giá hiện tại {price(val.price)}.")
    out.extend(val.skipped)
    return out


def technical_paragraphs(ctx: dict) -> list[str]:
    tech = ctx.get("technical")
    if tech is None:
        return ["Không đủ dữ liệu giá cho phân tích kỹ thuật."]
    out = [f"Điểm hợp lưu kỹ thuật {tech.total_score:+.0f}/100 → tín hiệu '{tech.action}' "
           f"(độ tin cậy {tech.confidence.replace('_', ' ')})."]
    out.extend(tech.reasons[:4])
    out.append(f"Vùng mua tham khảo {price(tech.entry_low)}–{price(tech.entry_high)}, cắt lỗ "
               f"{price(tech.stop_loss)}, mục tiêu ngắn hạn {price(tech.target)}.")
    return out


def scenario_rows(val) -> list[dict]:
    return [{"label": SCENARIO_LABELS[k], "price": val.target.get(k),
             "upside": (val.target.get(k) / val.price - 1) if val.target.get(k) and val.price else None}
            for k in ("bear", "base", "bull")]
