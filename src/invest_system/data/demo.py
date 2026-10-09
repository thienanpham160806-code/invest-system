"""Du lieu GIA LAP de chay thu he thong khi khong co mang / chua co API.

Ma demo co dang "DEMO*" (5+ ky tu) nen KHONG BAO GIO trung voi ma that tren
HOSE/HNX/UPCOM (ma that co 3 ky tu). Bao cao sinh tu ma demo co dau
"DỮ LIỆU MẪU – KHÔNG PHẢI SỐ LIỆU THẬT" o moi trang (xem report/templates).

So lieu gia lap NHAT QUAN noi bo (vd Tong TS = No + VCSH) de kiem thu duoc
ca tang kiem tra du lieu (validation/checks.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .fundamentals import StandardFinancials

DEMO_BENCHMARKS = {"DEMOIDX"}

_UNIVERSE = {
    # ma: (ten, loai, nganh, so CP luu hanh, gia goc, drift nam, vol nam, seed)
    "DEMO": ("CTCP Sản xuất Mẫu DEMO (giả lập)", "NON_FINANCIAL", "Thép & vật liệu (mẫu)",
             500_000_000, 25_000, 0.12, 0.32, 11),
    "DEMOP1": ("CTCP Mẫu P1 (giả lập)", "NON_FINANCIAL", "Thép & vật liệu (mẫu)",
               300_000_000, 18_000, 0.05, 0.35, 12),
    "DEMOP2": ("CTCP Mẫu P2 (giả lập)", "NON_FINANCIAL", "Thép & vật liệu (mẫu)",
               800_000_000, 32_000, 0.08, 0.28, 13),
    "DEMOP3": ("CTCP Mẫu P3 (giả lập)", "NON_FINANCIAL", "Thép & vật liệu (mẫu)",
               200_000_000, 12_000, -0.02, 0.40, 14),
    "DEMOB": ("Ngân hàng TMCP Mẫu DEMOB (giả lập)", "BANK", "Ngân hàng (mẫu)",
              2_000_000_000, 40_000, 0.15, 0.25, 21),
    "DEMOB1": ("Ngân hàng Mẫu B1 (giả lập)", "BANK", "Ngân hàng (mẫu)",
               3_000_000_000, 36_000, 0.10, 0.27, 22),
    "DEMOB2": ("Ngân hàng Mẫu B2 (giả lập)", "BANK", "Ngân hàng (mẫu)",
               1_500_000_000, 26_000, 0.06, 0.30, 23),
}
_YEARS = [2021, 2022, 2023, 2024, 2025]


def is_demo(symbol: str) -> bool:
    return str(symbol).upper() in _UNIVERSE


def universe() -> list[str]:
    return list(_UNIVERSE)


def benchmark_for(symbol: str) -> str:
    return "DEMOIDX"


def peers(symbol: str) -> list[str]:
    kind = _UNIVERSE[symbol.upper()][2]
    return [s for s, v in _UNIVERSE.items() if v[2] == kind and s != symbol.upper()]


def overview(symbol: str) -> dict:
    name, kind, industry, shares, *_ = _UNIVERSE[symbol.upper()]
    return {
        "full_name": name, "industry": industry, "company_type": kind,
        "shares_outstanding": float(shares), "exchange": "HOSE",
        "listed_date": "2015-01-01",
        "description": "Doanh nghiệp GIẢ LẬP để chạy thử hệ thống. Không phải doanh nghiệp thật.",
    }


def ohlcv(symbol: str, days: int = 730) -> pd.DataFrame:
    symbol = symbol.upper()
    if symbol == "DEMOIDX":
        start, drift, vol, seed = 1250.0, 0.10, 0.18, 1
    else:
        _, _, _, _, start, drift, vol, seed = _UNIVERSE[symbol]
    rng = np.random.default_rng(seed)
    n = int(days * 5 / 7)
    times = pd.bdate_range(end=pd.Timestamp("2026-10-08"), periods=n)
    # chung yeu to thi truong de beta co y nghia
    market = np.random.default_rng(1).normal(0.10 / 252, 0.18 / np.sqrt(252), n)
    idio = rng.normal(0, vol / np.sqrt(252), n)
    rets = market * (1.0 if symbol == "DEMOIDX" else 1.1) + (drift - 0.10) / 252 + (
        0 if symbol == "DEMOIDX" else idio * 0.8)
    close = start * np.exp(np.cumsum(rets))
    close = np.round(close, 2 if symbol == "DEMOIDX" else -1)
    spread = np.abs(rng.normal(0, 0.008, n))
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum.reduce([high, open_, close])
    low = np.minimum.reduce([low, open_, close])
    volume = (rng.lognormal(14.2, 0.35, n)).astype(int)
    return pd.DataFrame({"time": times, "open": open_, "high": high, "low": low,
                         "close": close, "volume": volume})


def _nonfin(symbol: str) -> pd.DataFrame:
    seed = _UNIVERSE[symbol][7]
    rng = np.random.default_rng(seed)
    base = {"DEMO": 8e12, "DEMOP1": 5e12, "DEMOP2": 20e12, "DEMOP3": 2.5e12}[symbol]
    growth = {"DEMO": 0.12, "DEMOP1": 0.04, "DEMOP2": 0.07, "DEMOP3": -0.03}[symbol]
    rows = []
    equity = base * 0.45
    for i, year in enumerate(_YEARS):
        revenue = base * (1 + growth) ** i * (1 + rng.normal(0, 0.04))
        gm = 0.18 + rng.normal(0, 0.015) + (0.03 if symbol == "DEMO" else 0)
        gross = revenue * gm
        selling = revenue * 0.03
        admin = revenue * 0.025
        fin_inc = revenue * 0.005
        total_debt = revenue * 0.30
        interest = total_debt * 0.075
        op_profit = gross - selling - admin + fin_inc - interest
        pbt = op_profit
        tax = max(pbt, 0) * 0.20
        ni = pbt - tax
        nip = ni * 0.96
        dep = revenue * 0.035
        total_assets = revenue * 1.0
        payout = 0.30 * max(nip, 0)
        equity = equity + nip - payout if i else equity
        liabilities = total_assets - equity
        cur_assets = total_assets * 0.48
        cash = total_assets * 0.07
        inv = total_assets * 0.22
        recv = total_assets * 0.12
        sti = cur_assets - cash - inv - recv
        cur_liab = liabilities * 0.62
        short_debt = total_debt * 0.6
        long_debt = total_debt * 0.4
        cfo = ni + dep - revenue * 0.02 * rng.uniform(0.2, 1.0)
        capex = -revenue * 0.06
        rows.append({
            "year": year, "revenue": revenue, "cogs": -(revenue - gross), "gross_profit": gross,
            "selling_expense": -selling, "admin_expense": -admin, "operating_profit": op_profit,
            "financial_income": fin_inc, "interest_expense": -interest, "pbt": pbt, "tax": -tax,
            "net_income": ni, "net_income_parent": nip, "depreciation": dep,
            "cash": cash, "short_investments": sti, "receivables": recv, "inventory": inv,
            "current_assets": cur_assets, "fixed_assets": total_assets * 0.40,
            "total_assets": total_assets, "current_liabilities": cur_liab,
            "short_debt": short_debt, "long_debt": long_debt, "total_liabilities": liabilities,
            "equity": equity, "minority_interest": equity * 0.03, "cfo": cfo, "capex": capex,
            "cfi": capex * 1.1, "cff": -payout + revenue * 0.01, "dividends_paid": -payout,
        })
    return pd.DataFrame(rows).set_index("year")


def _bank(symbol: str) -> pd.DataFrame:
    seed = _UNIVERSE[symbol][7]
    rng = np.random.default_rng(seed)
    base_loans = {"DEMOB": 250e12, "DEMOB1": 350e12, "DEMOB2": 130e12}[symbol]
    growth = {"DEMOB": 0.15, "DEMOB1": 0.12, "DEMOB2": 0.09}[symbol]
    rows = []
    equity = base_loans * 0.11
    for i, year in enumerate(_YEARS):
        loans = base_loans * (1 + growth) ** i
        deposits = loans * 1.05
        total_assets = loans * 1.45
        nim = 0.035 + rng.normal(0, 0.002) + (0.004 if symbol == "DEMOB" else 0)
        nii = total_assets * 0.92 * nim
        fee = nii * 0.18
        toi = nii + fee + nii * 0.10
        opex = -toi * (0.33 + rng.normal(0, 0.01))
        provision = -loans * (0.010 + rng.normal(0, 0.0015))
        pbt = toi + opex + provision
        tax = -pbt * 0.20
        ni = pbt + tax
        equity = equity + ni * 0.85 if i else equity
        rows.append({
            "year": year, "net_interest_income": nii, "fee_income": fee,
            "total_operating_income": toi, "operating_expense": opex, "provision": provision,
            "pbt": pbt, "tax": tax, "net_income": ni, "net_income_parent": ni,
            "loans": loans, "deposits": deposits, "total_assets": total_assets,
            "equity": equity, "total_liabilities": total_assets - equity,
        })
    return pd.DataFrame(rows).set_index("year")


def financials(symbol: str) -> StandardFinancials:
    symbol = symbol.upper()
    kind = _UNIVERSE[symbol][1]
    frame = _bank(symbol) if kind == "BANK" else _nonfin(symbol)
    shares = _UNIVERSE[symbol][3]
    prices = ohlcv(symbol, 365 * 6)
    year_end = prices.set_index("time")["close"].resample("YE").last()
    year_end.index = year_end.index.year
    hist = pd.DataFrame(index=frame.index)
    eps = frame["net_income_parent"] / shares
    bvps = frame["equity"] / shares
    price_at = year_end.reindex(frame.index)
    # gia lap: neu chuoi gia khong phu het cac nam, dung gia goc
    price_at = price_at.fillna(_UNIVERSE[symbol][4])
    hist["pe"] = price_at / eps
    hist["pb"] = price_at / bvps
    hist["roe"] = frame["net_income_parent"] / frame["equity"] * 100
    hist["eps"] = eps
    mapping = {c: "DỮ LIỆU MẪU (giả lập)" for c in frame.columns}
    return StandardFinancials(symbol, frame, "DỮ LIỆU MẪU (giả lập)", mapping, hist)


def news(symbol: str) -> list[dict]:
    now = pd.Timestamp("2026-10-08")
    if _UNIVERSE[symbol.upper()][1] == "BANK":
        titles = [
            "[MẪU] Ngân hàng DEMOB được NHNN nới room tín dụng, mục tiêu tăng trưởng 16%",
            "[MẪU] DEMOB hoàn thành phát hành trái phiếu, tăng vốn cấp 2",
            "[MẪU] Nợ xấu nhóm 5 của DEMOB tăng nhẹ trong quý gần nhất",
        ]
    else:
        titles = [
            "[MẪU] DEMO lãi kỷ lục quý III, vượt 85% kế hoạch năm",
            "[MẪU] DEMO khởi công nhà máy mới, mở rộng công suất 30%",
            "[MẪU] Giá nguyên liệu đầu vào giảm, biên lợi nhuận ngành cải thiện",
            "[MẪU] DEMO bị phạt chậm công bố thông tin",
        ]
    return [{"title": t, "published_at": now - pd.Timedelta(days=7 * i), "source": "DỮ LIỆU MẪU",
             "link": ""} for i, t in enumerate(titles)]


def macro_frame() -> pd.DataFrame:
    rows = [
        ("gdp_growth", "2023", 5.05), ("gdp_growth", "2024", 7.09), ("gdp_growth", "2025", 7.5),
        ("cpi", "2023", 3.25), ("cpi", "2024", 3.63), ("cpi", "2025", 3.4),
        ("policy_rate", "2024", 4.50), ("policy_rate", "2025", 4.50),
        ("credit_growth", "2024", 15.08), ("credit_growth", "2025", 16.0),
        ("usd_vnd", "2025", 25_500), ("usd_vnd", "2026", 26_000),
        ("gov_bond_10y", "2026", 3.2),
    ]
    return pd.DataFrame([
        {"indicator": i, "period": p, "value": v, "unit": "VND" if i == "usd_vnd" else "%",
         "source": "DỮ LIỆU MẪU (giả lập)", "as_of": "2026-10-01", "note": ""}
        for i, p, v in rows
    ])
