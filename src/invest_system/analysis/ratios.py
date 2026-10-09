"""Chi so tai chinh tinh TU BCTC chuan hoa (khong lay so "ratios" co san cua
nguon - so co san chi dung de DOI CHIEU trong validation/checks.py).

Hai bo chi so:
  - Doanh nghiep phi tai chinh: bien LN, ROE/ROA, don bay, thanh khoan, vong quay,
    chat luong LN (CFO/LNST), tang truong.
  - Ngan hang: NIM (xap xi), CIR, chi phi tin dung, LDR, ROE/ROA, don bay.
ROE/ROA dung VCSH/tong TS BINH QUAN dau-cuoi ky (chuan CTCK), nam dau tien
dung so cuoi ky.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.fundamentals import StandardFinancials

RATIO_LABELS = {
    "gross_margin": ("Biên lợi nhuận gộp", "pct"),
    "operating_margin": ("Biên LN hoạt động", "pct"),
    "net_margin": ("Biên lợi nhuận ròng", "pct"),
    "roe": ("ROE (LNST CĐ mẹ / VCSH CĐ mẹ bq)", "pct"),
    "roa": ("ROA", "pct"),
    "debt_to_equity": ("Vay nợ/VCSH", "x"),
    "liabilities_to_assets": ("Nợ phải trả/Tổng TS", "pct"),
    "current_ratio": ("Thanh toán hiện hành", "x"),
    "quick_ratio": ("Thanh toán nhanh", "x"),
    "interest_coverage": ("Khả năng trả lãi (EBIT/lãi vay)", "x"),
    "asset_turnover": ("Vòng quay tổng tài sản", "x"),
    "inventory_days": ("Số ngày tồn kho", "d"),
    "cfo_to_ni": ("CFO/LNST", "x"),
    "fcf": ("Dòng tiền tự do (FCF)", "vnd"),
    "revenue_growth": ("Tăng trưởng doanh thu", "pct"),
    "ni_growth": ("Tăng trưởng LNST CĐ mẹ", "pct"),
    "nim": ("NIM (xấp xỉ, TNLT/Tổng TS bq)", "pct"),
    "cir": ("Chi phí/Thu nhập (CIR)", "pct"),
    "credit_cost": ("Chi phí tín dụng (dự phòng/dư nợ bq)", "pct"),
    "ldr": ("Cho vay/Tiền gửi (LDR, xấp xỉ)", "pct"),
    "equity_to_assets": ("VCSH/Tổng tài sản", "pct"),
    "loan_growth": ("Tăng trưởng cho vay", "pct"),
    "toi_growth": ("Tăng trưởng TN hoạt động", "pct"),
}

NONFIN_KEYS = ["gross_margin", "operating_margin", "net_margin", "roe", "roa", "debt_to_equity",
               "liabilities_to_assets", "current_ratio", "quick_ratio", "interest_coverage",
               "asset_turnover", "inventory_days", "cfo_to_ni", "fcf", "revenue_growth",
               "ni_growth"]
BANK_KEYS = ["nim", "cir", "credit_cost", "ldr", "roe", "roa", "equity_to_assets",
             "loan_growth", "toi_growth", "ni_growth"]


def _div(a: pd.Series, b: pd.Series) -> pd.Series:
    b = b.replace(0, np.nan)
    return a / b


def _avg(series: pd.Series) -> pd.Series:
    """Binh quan dau-cuoi ky; nam dau tien dung so cuoi ky."""
    avg = (series + series.shift(1)) / 2
    return avg.fillna(series)


def compute_ratios(fin: StandardFinancials, company_type: str) -> pd.DataFrame:
    """DataFrame index = nam, cot = khoa trong RATIO_LABELS (chi cot tinh duoc)."""
    if fin.empty:
        return pd.DataFrame()
    s = fin.series
    out = pd.DataFrame(index=fin.frame.index)
    nip = s("net_income_parent") if not s("net_income_parent").empty else s("net_income")
    equity, assets = s("equity"), s("total_assets")
    if not equity.empty:
        # ROE = LNST CD me / VCSH CD me binh quan (VCSH trong BCTC hop nhat GOM loi ich CD
        # khong kiem soat -> tru ra de tu so va mau so cung "phan cua CD me")
        minority = s("minority_interest")
        eq_parent = equity - minority.reindex(equity.index).fillna(0) if not minority.empty else equity
        out["roe"] = _div(nip, _avg(eq_parent))
    if not assets.empty:
        out["roa"] = _div(s("net_income") if not s("net_income").empty else nip, _avg(assets))
    if not nip.empty:
        out["ni_growth"] = nip.pct_change(fill_method=None).where(nip.shift(1) > 0)

    if company_type == "BANK":
        nii, toi, opex = s("net_interest_income"), s("total_operating_income"), s("operating_expense")
        loans, deposits, prov = s("loans"), s("deposits"), s("provision")
        if not nii.empty and not assets.empty:
            out["nim"] = _div(nii, _avg(assets))
        if not opex.empty and not toi.empty:
            out["cir"] = _div(opex.abs(), toi)
        if not prov.empty and not loans.empty:
            out["credit_cost"] = _div(prov.abs(), _avg(loans))
        if not loans.empty and not deposits.empty:
            out["ldr"] = _div(loans, deposits)
        if not loans.empty:
            out["loan_growth"] = loans.pct_change(fill_method=None)
        if not toi.empty:
            out["toi_growth"] = toi.pct_change(fill_method=None)
        if not equity.empty and not assets.empty:
            out["equity_to_assets"] = _div(equity, assets)
        return out.dropna(axis=1, how="all")

    rev = s("revenue")
    if not rev.empty:
        if not s("gross_profit").empty:
            out["gross_margin"] = _div(s("gross_profit"), rev)
        if not s("operating_profit").empty:
            out["operating_margin"] = _div(s("operating_profit"), rev)
        out["net_margin"] = _div(s("net_income") if not s("net_income").empty else nip, rev)
        out["revenue_growth"] = rev.pct_change(fill_method=None)
        if not assets.empty:
            out["asset_turnover"] = _div(rev, _avg(assets))
    debt = s("short_debt").fillna(0) + s("long_debt").fillna(0) if not (
        s("short_debt").empty and s("long_debt").empty) else pd.Series(dtype=float)
    if not debt.empty and not equity.empty:
        out["debt_to_equity"] = _div(debt, equity)
    if not s("total_liabilities").empty and not assets.empty:
        out["liabilities_to_assets"] = _div(s("total_liabilities"), assets)
    if not s("current_assets").empty and not s("current_liabilities").empty:
        out["current_ratio"] = _div(s("current_assets"), s("current_liabilities"))
        if not s("inventory").empty:
            out["quick_ratio"] = _div(s("current_assets") - s("inventory"), s("current_liabilities"))
    if not s("interest_expense").empty:
        ebit = (s("pbt") + s("interest_expense").abs()) if not s("pbt").empty else s("operating_profit")
        out["interest_coverage"] = _div(ebit, s("interest_expense").abs())
    if not s("inventory").empty and not s("cogs").empty:
        out["inventory_days"] = _div(_avg(s("inventory")), s("cogs").abs()) * 365
    if not s("cfo").empty and not nip.empty:
        out["cfo_to_ni"] = _div(s("cfo"), s("net_income") if not s("net_income").empty else nip)
    if not s("cfo").empty and not s("capex").empty:
        out["fcf"] = s("cfo") + s("capex")  # capex la so am
    return out.dropna(axis=1, how="all")


def cagr(series: pd.Series) -> float | None:
    series = series.dropna()
    if len(series) < 2 or series.iloc[0] <= 0 or series.iloc[-1] <= 0:
        return None
    years = int(series.index[-1]) - int(series.index[0])
    return float((series.iloc[-1] / series.iloc[0]) ** (1 / max(years, 1)) - 1)


def growth_summary(fin: StandardFinancials, company_type: str) -> dict:
    s = fin.series
    top_line = s("total_operating_income") if company_type == "BANK" else s("revenue")
    nip = s("net_income_parent") if not s("net_income_parent").empty else s("net_income")
    return {
        "top_line_label": "Tổng thu nhập hoạt động" if company_type == "BANK" else "Doanh thu thuần",
        "top_line_cagr": cagr(top_line) if not top_line.empty else None,
        "ni_cagr": cagr(nip) if not nip.empty else None,
        "years": f"{fin.years[0]}–{fin.years[-1]}" if fin.years else "",
    }
