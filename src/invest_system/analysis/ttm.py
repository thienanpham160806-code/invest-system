"""TTM (4 quy gan nhat) tu BCTC quy - thuan logic, khong goi mang.

  - KQKD va LCTT (chi tieu dong): TONG 4 quy lien tiep.
  - CDKT (chi tieu thoi diem): so cua quy gan nhat.
  - VCSH binh quan 5 diem: cuoi quy t va cuoi 4 quy truoc (t-1 ... t-4) - mau
    so ROE TTM, khop voi tu so la LNST 4 quy.

Phan loai dong/thoi diem lay tu data/fundamentals._VNSTOCK_CANDIDATES (cot dau
tien: income / cashflow / balance), khong giu danh sach thu hai.

Kiem tra truoc khi tinh:
  - quy THIEU trong chuoi 4 (hoac 5 voi VCSH binh quan) -> khong tinh, ghi ly do;
  - quy TRUNG: cung (nam, quy) xuat hien nhieu lan voi so KHAC nhau -> khong
    tinh (khong biet ban nao dung); giong het nhau -> bo ban sao, ghi chu;
  - chi tieu thieu so o bat ky quy nao -> TTM chi tieu do = NaN (khong cong mot
    phan roi goi la TTM).

LCTT quy cua DN Viet Nam thuong la LUY KE tu dau nam. `deaccumulate_ytd()` doi
ve so tung quy; `reconcile_annual()` phat hien loi nay (tong 4 quy lech xa so
nam) cung nhu loi don vi / dao hang.

Dang du lieu vao: moi dong mot quy, cot `year`, `quarter` (1-4) va cac chi tieu
chuan (cung dang voi backtest/pit.py; dong quarter = 0 - BCTC nam - bi bo qua).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data.fundamentals import _VNSTOCK_CANDIDATES

FLOW_FIELDS = tuple(k for k, (stmt, _, _) in _VNSTOCK_CANDIDATES.items() if stmt in ("income", "cashflow"))
CASHFLOW_FIELDS = tuple(k for k, (stmt, _, _) in _VNSTOCK_CANDIDATES.items() if stmt == "cashflow")
STOCK_FIELDS = tuple(k for k, (stmt, _, _) in _VNSTOCK_CANDIDATES.items() if stmt == "balance")
RECONCILE_TOLERANCE = 0.02


def qindex(year: int, quarter: int) -> int:
    return int(year) * 4 + int(quarter) - 1


def qlabel(idx: int) -> str:
    return f"{idx // 4}-Q{idx % 4 + 1}"


@dataclass
class QuarterCheck:
    missing: list[str] = field(default_factory=list)      # "2025-Q3"
    duplicates: list[str] = field(default_factory=list)   # trung, so KHAC nhau
    identical_copies: list[str] = field(default_factory=list)  # trung, so giong het (da bo)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.duplicates


@dataclass
class TTMResult:
    label: str | None                      # "TTM Q2/2026"
    end: tuple[int, int] | None            # (nam, quy) cua quy cuoi
    periods: list[str]                     # 4 quy da cong
    values: dict[str, float]               # dong: tong 4 quy; thoi diem: quy cuoi
    equity_avg_5: float | None             # VCSH binh quan 5 diem
    check: QuarterCheck
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.label is not None

    def get(self, name: str) -> float | None:
        value = self.values.get(name)
        return None if value is None or pd.isna(value) else float(value)

    @property
    def roe(self) -> float | None:
        ni = self.get("net_income_parent")
        if ni is None:
            ni = self.get("net_income")
        if ni is None or not self.equity_avg_5:
            return None
        return ni / self.equity_avg_5


def _quarterly(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["year", "quarter", "_q"])
    q = frame[frame["quarter"].fillna(0).astype(int).between(1, 4)].copy()
    q["_q"] = [qindex(y, s) for y, s in zip(q["year"], q["quarter"], strict=True)]
    return q


def dedupe_quarters(frame: pd.DataFrame, fields: list[str] | None = None) -> tuple[pd.DataFrame, QuarterCheck]:
    """Bo ban sao giong het; bao quy trung KHAC so (giu nguyen, de nguoi goi tu chan)."""
    q = _quarterly(frame)
    check = QuarterCheck()
    cols = [c for c in (fields or list(q.columns)) if c in q.columns and c not in ("_q",)]
    keep = []
    for idx, group in q.groupby("_q", sort=True):
        if len(group) == 1:
            keep.append(group)
            continue
        values = group[cols].astype(object).where(group[cols].notna(), None)
        if all(values.iloc[i].tolist() == values.iloc[0].tolist() for i in range(1, len(values))):
            check.identical_copies.append(qlabel(idx))
            keep.append(group.iloc[[0]])
        else:
            check.duplicates.append(qlabel(idx))
            keep.append(group)
    out = pd.concat(keep) if keep else q
    return out.sort_values("_q", kind="stable"), check


def check_quarters(frame: pd.DataFrame, end: int, count: int) -> QuarterCheck:
    """Kiem tra du `count` quy lien tiep ket thuc tai qindex `end`, khong trung."""
    q, check = dedupe_quarters(frame)
    present = set(q["_q"])
    check.missing = [qlabel(i) for i in range(end - count + 1, end + 1) if i not in present]
    window = {qlabel(i) for i in range(end - count + 1, end + 1)}
    check.duplicates = [d for d in check.duplicates if d in window]
    check.identical_copies = [d for d in check.identical_copies if d in window]
    return check


def compute_ttm(frame: pd.DataFrame, end: tuple[int, int] | None = None) -> TTMResult:
    """TTM ket thuc tai quy `end` (mac dinh: quy moi nhat co trong `frame`)."""
    q, _ = dedupe_quarters(frame)
    if q.empty:
        return TTMResult(None, None, [], {}, None, QuarterCheck(), ["không có số liệu quý"])
    end_idx = qindex(*end) if end is not None else int(q["_q"].max())
    end_tuple = (end_idx // 4, end_idx % 4 + 1)
    check = check_quarters(frame, end_idx, 4)
    periods = [qlabel(i) for i in range(end_idx - 3, end_idx + 1)]
    if not check.ok:
        notes = []
        if check.missing:
            notes.append(f"thiếu quý {', '.join(check.missing)}")
        if check.duplicates:
            notes.append(f"quý trùng với số khác nhau: {', '.join(check.duplicates)}")
        return TTMResult(None, end_tuple, periods, {}, None, check, notes)

    window = q[q["_q"].between(end_idx - 3, end_idx)].sort_values("_q")
    last = window.iloc[-1]
    values: dict[str, float] = {}
    notes: list[str] = []
    if check.identical_copies:
        notes.append(f"bỏ bản sao giống hệt: {', '.join(check.identical_copies)}")
    for name in FLOW_FIELDS:
        if name not in window.columns:
            continue
        column = pd.to_numeric(window[name], errors="coerce")
        if column.isna().all():
            continue
        if column.isna().any():
            values[name] = np.nan
            notes.append(f"{name}: thiếu số ở quý {', '.join(window.loc[column.isna(), '_q'].map(qlabel))}")
        else:
            values[name] = float(column.sum())
    for name in STOCK_FIELDS:
        if name in window.columns and pd.notna(last.get(name)):
            values[name] = float(last[name])

    equity_avg = None
    if "equity" in q.columns:
        eq = q[q["_q"].between(end_idx - 4, end_idx)].set_index("_q")["equity"]
        eq = pd.to_numeric(eq, errors="coerce").dropna()
        if len(eq) == 5:
            equity_avg = float(eq.mean())
        else:
            dup = sorted({qlabel(i) for i in eq.index[eq.index.duplicated()]})
            gaps = [qlabel(i) for i in range(end_idx - 4, end_idx + 1) if i not in set(eq.index)]
            reasons = ([f"thiếu {', '.join(gaps)}"] if gaps else []) + (
                [f"quý trùng với số khác nhau {', '.join(dup)}"] if dup else [])
            notes.append(f"VCSH bình quân 5 điểm: {'; '.join(reasons)}")

    label = f"TTM Q{end_tuple[1]}/{end_tuple[0]}"
    return TTMResult(label, end_tuple, periods, values, equity_avg, check, notes)


def deaccumulate_ytd(frame: pd.DataFrame, fields: tuple[str, ...] = CASHFLOW_FIELDS) -> pd.DataFrame:
    """So luy ke tu dau nam -> so tung quy: Q1 = YTD1, Qn = YTDn - YTD(n-1).

    Quy truoc trong cung nam thieu -> quy do NaN (khong doan). Quy TRUNG voi so
    luy ke KHAC nhau -> quy do va quy lien sau deu NaN (khong phu thuoc thu tu
    dong); trung giong het thi dung binh thuong."""
    out = frame.copy()
    q = _quarterly(frame)
    keys = list(zip(q["year"].astype(int), q["quarter"].astype(int), strict=True))
    for name in fields:
        if name not in out.columns:
            continue
        ytd = pd.to_numeric(q[name], errors="coerce")
        by_period: dict[tuple[int, int], float] = {}
        for key, values in ytd.groupby([q["year"].astype(int), q["quarter"].astype(int)], sort=False):
            distinct = set(values.dropna().tolist())
            conflict = len(distinct) > 1 or (distinct and values.isna().any())
            by_period[key] = np.nan if conflict or not distinct else distinct.pop()
        discrete = []
        for year, quarter in keys:
            value = by_period[(year, quarter)]
            prev = 0.0 if quarter == 1 else by_period.get((year, quarter - 1), np.nan)
            discrete.append(np.nan if pd.isna(prev) or pd.isna(value) else value - prev)
        out.loc[q.index, name] = discrete
    return out


def reconcile_annual(quarterly: pd.DataFrame, annual: pd.Series | dict, year: int,
                     fields: tuple[str, ...] = FLOW_FIELDS,
                     tolerance: float = RECONCILE_TOLERANCE) -> pd.DataFrame:
    """Doi chieu tong Q1-Q4 cua `year` voi BCTC nam. Lech <= `tolerance` la khop.

    Cot: field, quarters_sum, annual, diff_pct, status ("khớp" | "lệch" | "thiếu quý" |
    "quý trùng" | "thiếu số năm" | "thiếu số quý").
    """
    annual = pd.Series(annual, dtype=object)
    q, check = dedupe_quarters(quarterly)
    year_rows = q[q["year"].astype(int) == int(year)] if not q.empty else q
    have = sorted(int(x) for x in year_rows.get("quarter", pd.Series(dtype=int)).unique())
    duplicated = any(d.startswith(f"{int(year)}-") for d in check.duplicates)
    rows = []
    for name in fields:
        if name not in annual.index and name not in year_rows.columns:
            continue
        a = pd.to_numeric(pd.Series([annual.get(name)]), errors="coerce").iloc[0]
        row = {"field": name, "quarters_sum": np.nan, "annual": a, "diff_pct": np.nan}
        if duplicated:
            row["status"] = "quý trùng"
        elif have != [1, 2, 3, 4]:
            row["status"] = "thiếu quý"
        elif pd.isna(a):
            row["status"] = "thiếu số năm"
        else:
            col = pd.to_numeric(year_rows.get(name, pd.Series(dtype=float)), errors="coerce")
            if len(col) != 4 or col.isna().any():
                row["status"] = "thiếu số quý"
            else:
                total = float(col.sum())
                row["quarters_sum"] = total
                denom = abs(a) if a != 0 else max(abs(total), 1.0)
                row["diff_pct"] = (total - a) / denom
                row["status"] = "khớp" if abs(total - a) <= tolerance * denom else "lệch"
        rows.append(row)
    return pd.DataFrame(rows, columns=["field", "quarters_sum", "annual", "diff_pct", "status"])
