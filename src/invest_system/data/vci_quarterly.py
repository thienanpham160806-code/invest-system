"""BCTC QUY tu Vietcap (VCI) qua vnstock - che do RAW, kem NGAY CONG BO THAT.

Vi sao khong dung `fa.equity(...).income_statement(period="quarter")` nhu
data/vietcap.py: ham do cat con 4 quy (vnstock dat `limit=4` mac dinh) va bao
cao LCTT quy chi tra 1 dong. API VCI that ra tra MOT lan toan bo cac quy tu
2018; goi `Finance._get_report(mode="raw", limit=...)` lay du ma KHONG ton them
request. Moi ban ghi raw la mot ky (yearReport, lengthReport) kem `publicDate`
- gia tri gan lien voi ky cua no, tranh loi dao hang khi xoay bang (xem
vietcap.align_statement_years) va cho backtest/pit.py ngay cong bo that.

Ma chi tieu raw (isa22, bsa53, cfa19...) doi ra ten qua tu dien
`/financial-statement/metrics` cua VCI. Tu dien KHAC NHAU theo mau BCTC (doanh
nghiep / ngan hang / chung khoan / bao hiem: cung ma bsa2 la "tien" o DN nhung
"tien va kim loai quy" o ngan hang) nen cache theo mau.

Anh xa sang chi tieu chuan: ten chinh xac (EXTRA_EXACT + data/fundamentals
_VNSTOCK_CANDIDATES) truoc, roi moi den tu khoa - va tu khoa KHONG nhan dong
"other_*", "less_*", "profit_loss_from_*" (loi thuc te: tu khoa
['operating','activities'] khop "other_receipts_from_operating_activities" = 0
thay vi LCTT thuan tu HDKD). Moi lua chon ghi vao `mapping`.

Kiem tra (validate): TS = No + VCSH (lech <= 1%), don vi VND (TS trung vi >= 1
ty), co chi tieu doanh thu dung loai DN. Quy khong qua kiem tra bi loai khoi
TTM, khong bi sua so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from ..logging_conf import get_logger
from .fundamentals import _VNSTOCK_CANDIDATES

log = get_logger(__name__)

PARTS = {"income": "income_statement", "balance": "balance_sheet", "cashflow": "cash_flow"}
DICT_SECTION = {"income": "INCOME_STATEMENT", "balance": "BALANCE_SHEET", "cashflow": "CASH_FLOW"}
TEMPLATE_REP = {"CORPORATE": "FPT", "BANK": "VCB", "SECURITIES": "SSI", "INSURANCE": "BVH"}
RAW_LIMIT = 500             # > so quy VCI luu (2018 -> nay ~34); vnstock cat head(limit) tu ky CU nhat
BALANCE_TOLERANCE = 0.01
MIN_TOTAL_ASSETS = 1e9      # VND

# Ten VCI da doi chieu (FPT, VCB 09/10/2026), uu tien hon danh sach chung.
EXTRA_EXACT: dict[str, list[str]] = {
    "revenue": ["net_sales", "net_sales_from_insurance_business"],
    "cogs": ["cost_of_sales"],
    "selling_expense": ["selling_expenses"],
    "operating_profit": ["operating_profit_loss"],
    "interest_expense": ["interest_expenses", "interest_and_similar_expenses"],
    "pbt": ["net_accounting_profit_loss_before_tax"],
    "tax": ["corporate_income_tax_expenses", "business_income_tax_expenses"],
    "net_income": ["net_profit_loss_after_tax"],
    "net_income_parent": ["attributable_to_parent_company", "net_profit_attributable_to_shareholders_of_the_group"],
    "receivables": ["accounts_receivable"],
    "inventory": ["inventories_net", "inventories"],
    "minority_interest": ["minority_interests", "minority_interest"],
    "cfo": ["net_cash_inflows_outflows_from_operating_activities", "net_cash_from_operating_activities"],
    "cfi": ["net_cash_inflows_outflows_from_investing_activities", "net_cash_from_investing_activities"],
    "cff": ["net_cash_inflows_outflows_from_financing_activities", "net_cash_from_financing_activities"],
    "loans": ["loans_and_advances_to_customers_net", "loans_and_advances_to_customers"],
}
_BLOCKED = ("other_", "less_", "profit_loss_from_")
_PART_OF = {"income": "income", "balance": "balance", "cashflow": "cashflow"}


def template_for(company_type: str | None) -> str:
    return company_type if company_type in ("BANK", "SECURITIES", "INSURANCE") else "CORPORATE"


def _snake(text: str) -> str:
    try:
        from vnstock.core.utils.field.handler import FieldHandler  # type: ignore
        return FieldHandler().normalize_field_name(text, language="en")
    except Exception:  # noqa: BLE001 - khong co vnstock (test, Vercel): quy tac tuong duong
        return re.sub(r"_+", "_", re.sub(r"[^0-9a-z]+", "_", str(text).lower())).strip("_")


def code_names(dictionary: pd.DataFrame) -> dict[str, dict[str, str]]:
    """{part: {ma VCI: ten snake}} tu tu dien metrics."""
    out: dict[str, dict[str, str]] = {p: {} for p in PARTS}
    section_part = {v: k for k, v in DICT_SECTION.items()}
    for row in dictionary.itertuples():
        part = section_part.get(row.report_name)
        if part and pd.notna(row.en_name) and pd.notna(row.field_name):  # dong tieu de khong co ma
            out[part][str(row.field_name)] = _snake(row.en_name)
    return out


def pick_code(names: dict[str, str], standard: str,
              available: set[str] | None = None) -> tuple[str | None, str | None]:
    """(ma VCI, ten) cho chi tieu chuan `standard` trong mot bao cao.

    `available`: cac ma co trong du lieu raw cua ma nay - ma tu dien khong co so
    lieu thi bo qua de ung vien sau duoc xet."""
    _, exact, keywords = _VNSTOCK_CANDIDATES[standard]
    by_name: dict[str, str] = {}
    for code, name in names.items():
        if available is None or code in available:
            by_name.setdefault(name, code)      # trung ten: giu ma dau tien (dong tong)
    for name in [*EXTRA_EXACT.get(standard, []), *exact]:
        if name in by_name:
            return by_name[name], name
    if keywords:
        hits = [n for n in by_name if all(k in n for k in keywords) and not n.startswith(_BLOCKED)]
        hits.sort(key=lambda n: (not n.startswith("net_"), len(n)))
        if hits:
            return by_name[hits[0]], hits[0]
    return None, None


@dataclass
class QuarterlyResult:
    symbol: str
    frame: pd.DataFrame                    # moi dong mot quy: symbol, year, quarter, published_at, chi tieu...
    mapping: dict[str, str] = field(default_factory=dict)   # field -> "income.isa22 attributable_to_parent_company"
    rejected: list[str] = field(default_factory=list)       # "2024-Q3: TS != No + VCSH (lech 3.1%)"
    errors: list[str] = field(default_factory=list)         # loi muc ma -> khong dung duoc


def _periods(raw: pd.DataFrame) -> pd.DataFrame:
    """Chuan hoa cot ky; bo dong khong phai quy 1-4; trung ky -> ban updateDate moi nhat."""
    if raw is None or raw.empty or not {"yearReport", "lengthReport"}.issubset(raw.columns):
        return pd.DataFrame()
    frame = raw.copy()
    frame["year"] = pd.to_numeric(frame["yearReport"], errors="coerce")
    frame["quarter"] = pd.to_numeric(frame["lengthReport"], errors="coerce")
    frame = frame[frame["quarter"].between(1, 4) & frame["year"].notna()]
    frame[["year", "quarter"]] = frame[["year", "quarter"]].astype(int)
    order = "updateDate" if "updateDate" in frame.columns else "year"
    return frame.sort_values(order, kind="stable").drop_duplicates(["year", "quarter"], keep="last")


def standardize(symbol: str, raws: dict[str, pd.DataFrame], dictionary: pd.DataFrame) -> QuarterlyResult:
    names = code_names(dictionary)
    result = QuarterlyResult(symbol.upper(), pd.DataFrame())
    merged: pd.DataFrame | None = None
    for part in PARTS:
        raw = _periods(raws.get(part))
        if raw.empty:
            result.errors.append(f"không có dữ liệu {PARTS[part]}")
            continue
        cols = {"year": raw["year"], "quarter": raw["quarter"],
                f"published_{part}": pd.to_datetime(raw.get("publicDate"), errors="coerce")}
        for standard, (stmt, _, _) in _VNSTOCK_CANDIDATES.items():
            if _PART_OF[part] != stmt:
                continue
            code, name = pick_code(names[part], standard, set(raw.columns))
            if code is not None and code in raw.columns:
                cols[standard] = pd.to_numeric(raw[code], errors="coerce")
                result.mapping[standard] = f"{part}.{code} {name}"
        piece = pd.DataFrame(cols)
        merged = piece if merged is None else merged.merge(piece, on=["year", "quarter"], how="outer")
    if merged is None or merged.empty:
        return result
    published = merged.filter(like="published_")
    # Ky chi dung duoc khi DU ca ba bao cao da cong bo -> lay ngay MUON nhat.
    merged["published_at"] = published.max(axis=1)
    merged = merged.drop(columns=published.columns)
    merged.insert(0, "symbol", symbol.upper())
    result.frame = merged.sort_values(["year", "quarter"]).reset_index(drop=True)
    return result


def validate(result: QuarterlyResult, company_type: str | None) -> QuarterlyResult:
    """Loai quy sai phuong trinh can doi / sai don vi; loi muc ma neu thieu doanh thu dung loai DN."""
    frame = result.frame
    if frame.empty:
        result.errors.append("không có quý nào")
        return result
    top_line = ("total_operating_income", "net_interest_income") if company_type == "BANK" else ("revenue",)
    if not any(c in frame.columns and frame[c].notna().any() for c in top_line):
        result.errors.append(f"thiếu chỉ tiêu doanh thu theo loại DN ({' / '.join(top_line)})")
    needed = {"total_assets", "total_liabilities", "equity"}
    if not needed.issubset(frame.columns):
        result.errors.append(f"thiếu {sorted(needed - set(frame.columns))} để kiểm tra TS = Nợ + VCSH")
        return result
    assets, liabilities, equity = (frame[c] for c in ("total_assets", "total_liabilities", "equity"))
    gap = ((liabilities + equity - assets).abs() / assets.where(assets > 0))
    unit_ok = assets >= MIN_TOTAL_ASSETS
    ok = (gap <= BALANCE_TOLERANCE) & unit_ok
    for idx in frame.index[~ok]:
        label = f"{frame.at[idx, 'year']}-Q{frame.at[idx, 'quarter']}"
        if pd.isna(assets[idx]) or pd.isna(gap[idx]):
            result.rejected.append(f"{label}: thiếu TS/Nợ/VCSH")
        elif not unit_ok[idx]:
            result.rejected.append(f"{label}: tổng tài sản {assets[idx]:,.0f} < 1 tỷ (sai đơn vị?)")
        else:
            result.rejected.append(f"{label}: TS ≠ Nợ + VCSH (lệch {gap[idx]:.1%})")
    result.frame = frame[ok].reset_index(drop=True)
    if result.frame.empty:
        result.errors.append("không quý nào qua kiểm tra")
    return result


# ------------------------------------------------------------------ goi mang (chi chay khi giu vnstock.lock)
def _finance(symbol: str):
    from vnstock.explorer.vci.financial import Finance  # type: ignore
    return Finance(symbol=symbol.upper(), period="quarter", get_all=True, show_log=False)


def fetch_dictionary(symbol: str) -> pd.DataFrame:
    return _finance(symbol)._get_ratio_dict(format="dataframe")


def fetch_raw(symbol: str, part: str) -> pd.DataFrame:
    raw = _finance(symbol)._get_report(report_type=PARTS[part], mode="raw", period="quarter",
                                       limit=RAW_LIMIT, get_all=True)
    if raw is not None and len(raw) >= RAW_LIMIT:
        log.warning("%s %s: %d dòng = RAW_LIMIT, có thể thiếu quý mới nhất", symbol, part, len(raw))
    return raw if raw is not None else pd.DataFrame()


def latest_quarters(frame: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """n quy gan nhat cua moi ma."""
    if frame.empty:
        return frame
    ranked = frame.assign(_k=frame["year"] * 4 + frame["quarter"])
    keep = ranked.groupby("symbol")["_k"].rank(ascending=False, method="first") <= n
    return ranked[keep].drop(columns="_k").reset_index(drop=True)
