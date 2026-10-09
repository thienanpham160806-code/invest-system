"""Kiem tra chat luong du lieu TU DONG truoc khi dua vao bao cao.

Moi kiem tra tra ve PASS / WARN / FAIL / SKIP kem chi tiet. Ket qua in o
trang 1 (tom tat "x/y dat") va day du o phu luc PDF.
  - Dang thuc ke toan: Tong TS = No phai tra + VCSH (sai so <= 1%)
  - LN gop <= doanh thu; LNST CD me <= LNST (+ sai so)
  - Don vi: tong tai san DN niem yet phai >= 10 ty dong (phat hien nham don vi ty/trieu)
  - Do phu: du so nam BCTC, nam gan nhat khong qua cu
  - Gia: phien gan nhat khong qua 7 ngay; khong co gia <= 0; bien do ngay trong tran/san
  - Doi chieu: ROE tu tinh vs ROE cua nguon (lech <= 3 diem %), P/E tu tinh vs nguon (<= 15%)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from ..data.fundamentals import StandardFinancials

PRICE_BAND = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}


@dataclass
class Check:
    name: str
    status: str   # PASS | WARN | FAIL | SKIP
    detail: str

    def to_dict(self):
        return asdict(self)


def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-9)


def check_financials(fin: StandardFinancials, company_type: str, min_years: int = 3) -> list[Check]:
    out: list[Check] = []
    if fin.empty:
        return [Check("Có dữ liệu BCTC", "FAIL", "; ".join(fin.notes) or "Không có BCTC")]
    out.append(Check("Có dữ liệu BCTC", "PASS", f"{len(fin.years)} năm ({fin.years[0]}–{fin.years[-1]}), nguồn: {fin.source}"))
    out.append(Check("Đủ số năm phân tích", "PASS" if len(fin.years) >= min_years else "WARN",
                     f"{len(fin.years)} năm (cần tối thiểu {min_years})"))
    latest = fin.years[-1]
    this_year = pd.Timestamp.now().year
    out.append(Check("BCTC năm gần nhất còn mới", "PASS" if latest >= this_year - 2 else "WARN",
                     f"năm gần nhất {latest}"))

    derived = fin.mapping.get("total_liabilities", "").startswith("tính")
    a, liab, e = fin.series("total_assets"), fin.series("total_liabilities"), fin.series("equity")
    if derived or a.empty or liab.empty or e.empty:
        out.append(Check("Tổng TS = Nợ phải trả + VCSH", "SKIP",
                         "thiếu cột hoặc nợ phải trả được suy ra từ TS − VCSH"))
    else:
        both = pd.concat({"a": a, "le": liab + e}, axis=1).dropna()
        bad = [int(y) for y, r in both.iterrows() if _rel(r["le"], r["a"]) > 0.01]
        out.append(Check("Tổng TS = Nợ phải trả + VCSH", "FAIL" if bad else "PASS",
                         f"lệch > 1% ở năm {bad}" if bad else f"khớp {len(both)}/{len(both)} năm"))

    if not a.empty:
        tiny = a.dropna()[a.dropna() < 10e9]
        out.append(Check("Đơn vị tiền tệ hợp lý (VND)", "WARN" if not tiny.empty else "PASS",
                         f"Tổng TS < 10 tỷ đồng ở năm {list(tiny.index)} — kiểm tra đơn vị" if not tiny.empty
                         else f"Tổng TS năm {latest}: {a.dropna().iloc[-1]/1e9:,.0f} tỷ đồng"))

    if company_type != "BANK":
        rev, gp = fin.series("revenue"), fin.series("gross_profit")
        if not rev.empty and not gp.empty:
            bad = [int(y) for y in rev.index if pd.notna(rev[y]) and pd.notna(gp.get(y))
                   and gp[y] > rev[y] * 1.001]
            out.append(Check("LN gộp ≤ doanh thu", "FAIL" if bad else "PASS",
                             f"vi phạm ở năm {bad}" if bad else "hợp lệ mọi năm"))
    ni, nip = fin.series("net_income"), fin.series("net_income_parent")
    if not ni.empty and not nip.empty and not fin.mapping.get("net_income_parent", "").startswith("tính"):
        bad = [int(y) for y in ni.index if pd.notna(ni[y]) and pd.notna(nip.get(y))
               and ni[y] > 0 and nip[y] > ni[y] * 1.05]
        out.append(Check("LNST CĐ mẹ ≤ LNST hợp nhất", "WARN" if bad else "PASS",
                         f"bất thường ở năm {bad}" if bad else "hợp lệ"))
    missing = [k for k in (("net_interest_income", "loans", "deposits") if company_type == "BANK"
                           else ("revenue", "net_income", "equity", "cfo")) if fin.series(k).empty]
    out.append(Check("Đủ chỉ tiêu cốt lõi cho loại DN", "WARN" if missing else "PASS",
                     f"thiếu: {missing}" if missing else "đủ"))
    return out


def check_prices(ohlcv: pd.DataFrame, exchange: str | None, as_of: pd.Timestamp | None = None) -> list[Check]:
    out: list[Check] = []
    if ohlcv is None or ohlcv.empty:
        return [Check("Có dữ liệu giá", "FAIL", "không lấy được OHLCV")]
    last = pd.Timestamp(ohlcv["time"].iloc[-1])
    as_of = as_of or pd.Timestamp.now().normalize()
    lag = (as_of - last.normalize()).days
    out.append(Check("Có dữ liệu giá", "PASS", f"{len(ohlcv)} phiên, phiên cuối {last:%d/%m/%Y}"))
    out.append(Check("Giá còn mới (≤ 7 ngày)", "PASS" if lag <= 7 else "WARN", f"trễ {lag} ngày"))
    nonpos = int((ohlcv[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    out.append(Check("Không có giá ≤ 0", "FAIL" if nonpos else "PASS", f"{nonpos} phiên lỗi"))
    band = PRICE_BAND.get(exchange or "", 0.15)
    ch = ohlcv["close"].astype(float).pct_change().abs().dropna()
    # bien do vuot tran/san co the do dieu chinh gia (co tuc/thuong CP) - chi canh bao
    breach = int((ch > band + 0.005).sum())
    out.append(Check(f"Biến động ngày trong biên độ ±{band:.0%}", "WARN" if breach else "PASS",
                     f"{breach} phiên vượt biên độ (có thể do chưa điều chỉnh cổ tức/chia tách)"
                     if breach else "hợp lệ"))
    return out


def cross_check(fin: StandardFinancials, ratios: pd.DataFrame, own_pe: float | None) -> list[Check]:
    """Doi chieu chi so TU TINH voi chi so CO SAN cua nguon (neu nguon co)."""
    out: list[Check] = []
    hist = fin.ratios_history
    if hist is None or hist.empty or fin.source.startswith("DỮ LIỆU MẪU"):
        return [Check("Đối chiếu chỉ số với nguồn thứ hai", "SKIP", "nguồn không cung cấp bảng chỉ số")]
    if "roe" in hist.columns and ratios is not None and "roe" in ratios.columns:
        both = pd.concat({"src": hist["roe"] / 100, "calc": ratios["roe"]}, axis=1).dropna()
        if not both.empty:
            diff = (both["src"] - both["calc"]).abs()
            bad = [int(y) for y in diff.index if diff[y] > 0.03]
            out.append(Check("ROE tự tính ≈ ROE của nguồn (±3 điểm %)",
                             "WARN" if bad else "PASS",
                             f"lệch ở năm {bad} (khác cách tính bình quân/cuối kỳ)" if bad
                             else f"khớp {len(both)} năm"))
    if own_pe is not None and "pe" in hist.columns:
        src_pe = hist["pe"].dropna()
        if not src_pe.empty:
            r = _rel(own_pe, src_pe.iloc[-1])
            out.append(Check("P/E tự tính ≈ P/E của nguồn (±15%)", "PASS" if r <= 0.15 else "WARN",
                             f"tự tính {own_pe:.1f} / nguồn {src_pe.iloc[-1]:.1f} "
                             "(nguồn có thể dùng EPS 4 quý gần nhất)"))
    return out or [Check("Đối chiếu chỉ số với nguồn thứ hai", "SKIP", "không có cột tương ứng")]


def summarize(checks: list[Check]) -> dict:
    counted = [c for c in checks if c.status != "SKIP"]
    passed = sum(c.status == "PASS" for c in counted)
    return {"passed": passed, "total": len(counted),
            "warn": sum(c.status == "WARN" for c in counted),
            "fail": sum(c.status == "FAIL" for c in counted)}
