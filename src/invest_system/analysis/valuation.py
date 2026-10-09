"""Dinh gia THEO LOAI DOANH NGHIEP (tieu chi "ket qua phan tich danh gia thich hop").

Vi sao khac nhau: ngan hang khong co "doanh thu"/"EBITDA", dong tien cua ngan
hang khong tach duoc hoat dong va tai tro -> DCF FCFF/EV-EBITDA vo nghia. Ngan
hang/CTCK/bao hiem/BDS dinh gia chu yeu theo gia tri so sach (P/B).

  NON_FINANCIAL: P/E tuong doi, P/B tuong doi, EV/EBITDA tuong doi, DCF FCFF 5 nam
  BANK:          P/B hop ly = (ROE - g)/(Ke - g)  (Gordon), P/B & P/E tuong doi
  SECURITIES / INSURANCE / REAL_ESTATE: P/B & P/E tuong doi
                 (RNAV cho BDS can quy du an - de mo rong, xem README)

"Tuong doi" = so voi TRUNG VI nhom cung nganh; neu khong co du lieu nganh thi
so voi TRUNG BINH LICH SU 5 nam cua chinh doanh nghiep (ghi ro trong bao cao).
Ba kich ban: bi quan / co so / lac quan (phan vi 25/50/75 cua boi so nganh,
WACC +-1%, tang truong +-2%, ROE +-2 diem %).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings
from ..data.fundamentals import StandardFinancials

METHOD_LABELS = {
    "pe_relative": "P/E tương đối",
    "pb_relative": "P/B tương đối",
    "ev_ebitda": "EV/EBITDA tương đối",
    "dcf_fcff": "Chiết khấu dòng tiền (FCFF 5 năm)",
    "justified_pb": "P/B hợp lý (Gordon: (ROE−g)/(Ke−g))",
}
SCENARIOS = ("bear", "base", "bull")
SCENARIO_LABELS = {"bear": "Bi quan", "base": "Cơ sở", "bull": "Lạc quan"}


@dataclass
class MethodResult:
    key: str
    label: str
    values: dict[str, float]           # kich ban -> gia/CP
    weight: float = 0.0
    inputs: dict = field(default_factory=dict)
    note: str = ""


@dataclass
class ValuationResult:
    price: float | None
    methods: list[MethodResult] = field(default_factory=list)
    target: dict[str, float] = field(default_factory=dict)   # kich ban -> gia muc tieu
    upside: float | None = None
    assumptions: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    per_share: dict = field(default_factory=dict)

    @property
    def target_price(self) -> float | None:
        return self.target.get("base")


def cost_of_equity(beta: float | None, rf: float, erp: float) -> tuple[float, float]:
    s = get_settings()
    b = beta if beta is not None else s.get("valuation.default_beta", 1.0)
    b = float(np.clip(b, s.get("valuation.beta_floor", 0.6), s.get("valuation.beta_ceiling", 1.8)))
    # San Ke: CAPM voi beta thap + rf thap cho Ke ~9-10%, thap hon thuc tien dinh gia cua CTCK VN
    # (12-15%) va lam mo hinh Gordon/DCF bung no khi Ke - g qua nho.
    return max(rf + b * erp, s.get("valuation.ke_floor", 0.12)), b


def _multiple_triplet(sector_q: dict, key: str, own_hist: pd.Series | None):
    """(p25, p50, p75, nguon) cua boi so `key`."""
    q = sector_q.get(key)
    if q and all(v is not None and np.isfinite(v) and v > 0 for v in q):
        return (*q, "trung vị nhóm cùng ngành")
    if own_hist is not None:
        h = pd.to_numeric(own_hist, errors="coerce").dropna()
        h = h[(h > 0) & (h < 100)]
        if len(h) >= 3:
            return (float(h.quantile(0.25)), float(h.median()), float(h.quantile(0.75)),
                    f"lịch sử {len(h)} năm của chính DN")
    return None


def _round_price(v: float) -> float:
    return float(round(v / 100.0) * 100) if v is not None and np.isfinite(v) else None


def value_company(fin: StandardFinancials, company_type: str, price: float | None,
                  shares: float | None, ratios: pd.DataFrame, sector_quantiles: dict,
                  beta: float | None, rf: float | None = None) -> ValuationResult:
    s = get_settings()
    res = ValuationResult(price=price)
    rf = rf if rf is not None else s.get("valuation.risk_free_rate", 0.03)
    erp = s.get("valuation.equity_risk_premium", 0.08)
    ke, beta_used = cost_of_equity(beta, rf, erp)
    gT = s.get("valuation.terminal_growth", 0.03)
    g_floor, g_cap = s.get("valuation.growth_floor", -0.10), s.get("valuation.growth_cap", 0.20)
    res.assumptions = {"rf": rf, "erp": erp, "beta": beta_used, "beta_raw": beta, "ke": ke,
                       "terminal_growth": gT}

    if fin.empty or not shares or not price:
        res.skipped.append("Thiếu BCTC, số cổ phiếu lưu hành hoặc giá — không định giá được.")
        return res

    nip = fin.get("net_income_parent") or fin.get("net_income")
    equity = fin.get("equity")
    minority = fin.get("minority_interest") or 0.0
    eq_parent = (equity - minority) if equity else None
    eps = nip / shares if nip else None
    bvps = eq_parent / shares if eq_parent else None
    nip_series = fin.series("net_income_parent").dropna()
    from .ratios import cagr

    g_raw = cagr(nip_series) if len(nip_series) >= 3 else None
    g = float(np.clip(g_raw if g_raw is not None else 0.05, g_floor, g_cap))
    res.per_share = {"eps": eps, "bvps": bvps, "eps_fwd": eps * (1 + g) if eps else None,
                     "growth": g, "growth_raw": g_raw}
    res.assumptions["growth"] = g
    hist = fin.ratios_history if not fin.ratios_history.empty else pd.DataFrame()

    methods: list[MethodResult] = []
    scen_mult = {"bear": 0, "base": 1, "bull": 2}

    # ---- P/E tuong doi
    trip = _multiple_triplet(sector_quantiles, "pe", hist.get("pe") if not hist.empty else None)
    if trip and eps and eps > 0:
        fwd = eps * (1 + g)
        vals = {sc: fwd * trip[scen_mult[sc]] for sc in SCENARIOS}
        methods.append(MethodResult("pe_relative", METHOD_LABELS["pe_relative"], vals,
                                    inputs={"EPS dự phóng": fwd, "P/E mục tiêu": trip[1],
                                            "Nguồn bội số": trip[3]}))
    elif eps is not None and eps <= 0:
        res.skipped.append("P/E: EPS âm — không áp dụng.")
    # ---- P/B tuong doi
    trip = _multiple_triplet(sector_quantiles, "pb", hist.get("pb") if not hist.empty else None)
    if trip and bvps and bvps > 0:
        vals = {sc: bvps * trip[scen_mult[sc]] for sc in SCENARIOS}
        methods.append(MethodResult("pb_relative", METHOD_LABELS["pb_relative"], vals,
                                    inputs={"BVPS": bvps, "P/B mục tiêu": trip[1],
                                            "Nguồn bội số": trip[3]}))

    if company_type == "NON_FINANCIAL":
        _ev_ebitda(fin, shares, sector_quantiles, methods, res)
        _dcf(fin, shares, price, ke, gT, g, methods, res)
    if company_type == "BANK":
        _justified_pb(ratios, bvps, ke, methods, res)

    # ---- gop co trong so (chuan hoa tren phuong phap tinh duoc)
    weights = s.get(f"valuation.method_weights.{company_type}", {}) or {}
    usable = [m for m in methods if weights.get(m.key, 0) > 0 and
              all(np.isfinite(v) and v > 0 for v in m.values.values())]
    # Kiem soat ngoai lai: phuong phap lech > 2,5 lan so voi trung vi cac phuong phap
    # (vd DCF khi FCFF bat thuong) bi loai khoi binh quan, ghi ro ly do.
    if len(usable) >= 3:
        med = float(np.median([m.values["base"] for m in usable]))
        for m in list(usable):
            if not (med / 2.5 <= m.values["base"] <= med * 2.5):
                usable.remove(m)
                m.note = "Loại khỏi bình quân: lệch > 2,5 lần trung vị các phương pháp"
                res.skipped.append(f"{m.label}: {m.note}.")
    total_w = sum(weights[m.key] for m in usable)
    for m in methods:
        m.weight = weights.get(m.key, 0) / total_w if m in usable and total_w else 0.0
    res.methods = methods
    if usable:
        for sc in SCENARIOS:
            res.target[sc] = _round_price(sum(m.values[sc] * m.weight for m in usable))
        res.upside = res.target["base"] / price - 1
    else:
        res.skipped.append("Không có phương pháp định giá nào đủ dữ liệu.")
    return res


def _ev_ebitda(fin, shares, sector_q, methods, res):
    trip = _multiple_triplet(sector_q, "ev_ebitda", None)
    pbt, dep = fin.get("pbt"), fin.get("depreciation")
    if not trip or pbt is None or dep is None:
        return
    ebitda = pbt + abs(fin.get("interest_expense") or 0) + abs(dep)
    if ebitda <= 0:
        res.skipped.append("EV/EBITDA: EBITDA âm.")
        return
    debt = (fin.get("short_debt") or 0) + (fin.get("long_debt") or 0)
    cash = (fin.get("cash") or 0) + (fin.get("short_investments") or 0)
    minority = fin.get("minority_interest") or 0
    vals = {sc: (ebitda * trip[i] - debt + cash - minority) / shares
            for i, sc in enumerate(SCENARIOS)}
    methods.append(MethodResult("ev_ebitda", METHOD_LABELS["ev_ebitda"], vals,
                                inputs={"EBITDA": ebitda, "EV/EBITDA mục tiêu": trip[1],
                                        "Nợ vay": debt, "Tiền & ĐTNH": cash,
                                        "Nguồn bội số": trip[3]}))


def _dcf(fin, shares, price, ke, gT, g, methods, res):
    s = get_settings()
    cfo, capex = fin.series("cfo"), fin.series("capex")
    interest = fin.series("interest_expense").abs()
    tax = s.get("valuation.tax_rate", 0.20)
    if cfo.dropna().empty or capex.dropna().empty:
        res.skipped.append("DCF: thiếu dòng tiền HĐKD hoặc capex.")
        return
    fcff = (cfo + capex + interest.reindex(cfo.index).fillna(0) * (1 - tax)).dropna().tail(3)
    base = float(fcff.mean())
    if base <= 0:
        res.skipped.append("DCF: FCFF bình quân 3 năm âm — DN đang đầu tư mạnh, "
                           "DCF không phản ánh đúng; dùng phương pháp bội số.")
        return
    debt = (fin.get("short_debt") or 0) + (fin.get("long_debt") or 0)
    cash = (fin.get("cash") or 0) + (fin.get("short_investments") or 0)
    minority = fin.get("minority_interest") or 0
    avg_debt = float(((fin.series("short_debt").fillna(0) + fin.series("long_debt").fillna(0))
                      .tail(2)).mean()) if debt else 0
    kd = float(np.clip(interest.dropna().iloc[-1] / avg_debt, 0.05, 0.12)) if (
        avg_debt and not interest.dropna().empty) else s.get("valuation.default_cost_of_debt", 0.08)
    mcap = price * shares
    wd = debt / (debt + mcap) if debt + mcap else 0
    wacc = (1 - wd) * ke + wd * kd * (1 - tax)
    n = s.get("valuation.dcf_years", 5)
    res.assumptions.update({"wacc": wacc, "kd": kd, "wd": wd, "fcff_base": base})

    def run(wacc_, g_):
        if wacc_ <= gT + 0.01:
            return np.nan
        pv, f = 0.0, base
        for t in range(1, n + 1):
            gt = g_ + (gT - g_) * (t - 1) / max(n - 1, 1)  # giam dan ve tang truong dai han
            f *= 1 + gt
            pv += f / (1 + wacc_) ** t
        tv = f * (1 + gT) / (wacc_ - gT)
        ev = pv + tv / (1 + wacc_) ** n
        return (ev - debt + cash - minority) / shares

    vals = {"bear": run(wacc + 0.01, g - 0.02), "base": run(wacc, g), "bull": run(wacc - 0.01, g + 0.02)}
    methods.append(MethodResult("dcf_fcff", METHOD_LABELS["dcf_fcff"], vals,
                                inputs={"FCFF cơ sở (bq 3 năm)": base, "WACC": wacc,
                                        "Tăng trưởng giai đoạn đầu": g, "Tăng trưởng dài hạn": gT,
                                        "Ke": ke, "Kd": kd}))


def _justified_pb(ratios, bvps, ke, methods, res):
    if ratios is None or ratios.empty or "roe" not in ratios.columns or not bvps:
        return
    roe = float(ratios["roe"].dropna().tail(3).mean())
    payout = 0.25
    g_sus = float(np.clip(roe * (1 - payout), 0.0, ke - 0.02))
    # g dai han <= 6% va cach Ke >= 4 diem % (tranh mau so (Ke-g) qua nho -> P/B vo ly)
    g_sus = min(g_sus, get_settings().get("valuation.bank_g_cap", 0.06), ke - 0.04)
    res.assumptions.update({"bank_roe": roe, "bank_g": g_sus})

    def pb(roe_):
        return float(np.clip((roe_ - g_sus) / (ke - g_sus), 0.3, 4.0))

    vals = {"bear": bvps * pb(roe - 0.02), "base": bvps * pb(roe), "bull": bvps * pb(roe + 0.02)}
    methods.append(MethodResult("justified_pb", METHOD_LABELS["justified_pb"], vals,
                                inputs={"ROE bq 3 năm": roe, "Ke": ke, "g bền vững": g_sus,
                                        "P/B hợp lý": pb(roe), "BVPS": bvps}))
