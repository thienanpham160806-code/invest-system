"""Bao cao tai chinh CHUAN HOA: mot bang (nam x chi tieu chuan) cho moi ma.

Van de: moi nguon dat ten chi tieu khac nhau (vnstock dung item_id tieng Anh
kieu snake_case, vnfinancialdata dung ten tieng Viet theo mau BCTC, file tay
cua nhom dung ten tu dat). Tang phan tich phia sau KHONG duoc biet ten goc -
no chi doc cac cot chuan trong STANDARD_FIELDS.

Chuoi nguon (dung nguon dau tien tra ve du lieu):
  1. vnstock qua data/router.py (Vietcap/VCI) - tu dong, co ca ngan hang.
  2. vnfinancialdata (Hugging Face, TS. Ngo Phu Thanh - UEL), 2014-2024, HSX/HNX.
  3. File tay data/manual/<MA>_financials.csv (mau: scripts/make_manual_template.py).
  4. Du lieu GIA LAP cho ma demo (data/demo.py) - bao cao co dau "DU LIEU MAU".

Moi lan anh xa, ten cot goc duoc ghi vao `mapping` -> in ra phu luc PDF de
nguoi cham kiem tra duoc "so nay lay tu dong nao".

DON VI: tat ca gia tri tien te quy ve VND (dong). Kiem tra don vi nam o
validation/checks.py (vd tong tai san < 1 ty dong voi DN niem yet -> canh bao).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from ..config import PROJECT_ROOT
from ..logging_conf import get_logger

log = get_logger(__name__)

MANUAL_DIR = PROJECT_ROOT / "data" / "manual"

# --------------------------------------------------------------- chi tieu chuan
NONFIN_FIELDS = [
    "revenue", "cogs", "gross_profit", "selling_expense", "admin_expense",
    "operating_profit", "financial_income", "interest_expense", "pbt", "tax",
    "net_income", "net_income_parent", "depreciation",
    "cash", "short_investments", "receivables", "inventory", "current_assets",
    "fixed_assets", "total_assets", "current_liabilities", "short_debt", "long_debt",
    "total_liabilities", "equity", "minority_interest",
    "cfo", "capex", "cfi", "cff", "dividends_paid",
]
BANK_FIELDS = [
    "net_interest_income", "fee_income", "total_operating_income", "operating_expense",
    "provision", "loans", "deposits",
]
STANDARD_FIELDS = list(dict.fromkeys(NONFIN_FIELDS + BANK_FIELDS))

FIELD_LABELS_VI = {
    "revenue": "Doanh thu thuần", "cogs": "Giá vốn hàng bán", "gross_profit": "Lợi nhuận gộp",
    "selling_expense": "Chi phí bán hàng", "admin_expense": "Chi phí QLDN",
    "operating_profit": "LN thuần từ HĐKD", "financial_income": "Doanh thu tài chính",
    "interest_expense": "Chi phí lãi vay", "pbt": "Lợi nhuận trước thuế", "tax": "Thuế TNDN",
    "net_income": "Lợi nhuận sau thuế", "net_income_parent": "LNST công ty mẹ",
    "depreciation": "Khấu hao", "cash": "Tiền & tương đương tiền",
    "short_investments": "Đầu tư tài chính ngắn hạn", "receivables": "Phải thu ngắn hạn",
    "inventory": "Hàng tồn kho", "current_assets": "Tài sản ngắn hạn",
    "fixed_assets": "Tài sản cố định", "total_assets": "Tổng tài sản",
    "current_liabilities": "Nợ ngắn hạn", "short_debt": "Vay ngắn hạn",
    "long_debt": "Vay dài hạn", "total_liabilities": "Nợ phải trả", "equity": "Vốn chủ sở hữu",
    "minority_interest": "Lợi ích cổ đông thiểu số", "cfo": "LCTT từ HĐKD",
    "capex": "Chi đầu tư TSCĐ", "cfi": "LCTT từ HĐĐT", "cff": "LCTT từ HĐTC",
    "dividends_paid": "Cổ tức đã trả", "net_interest_income": "Thu nhập lãi thuần",
    "fee_income": "Lãi thuần từ dịch vụ", "total_operating_income": "Tổng thu nhập hoạt động",
    "operating_expense": "Chi phí hoạt động", "provision": "Chi phí dự phòng rủi ro tín dụng",
    "loans": "Cho vay khách hàng", "deposits": "Tiền gửi của khách hàng",
}

# ---------------------------------------------- anh xa ten cot vnstock (item_id)
# Ten DA XAC NHAN tren vnstock 4.0.8 (xem analysis/fintext.py, data/vietcap.py)
# dat dau danh sach; cac ten sau la ung vien, cuoi cung la tu khoa tim mo.
_VNSTOCK_CANDIDATES: dict[str, tuple[str, list[str], list[str]]] = {
    # field: (bao cao, ten cot chinh xac, tu khoa bat buoc cung xuat hien)
    "revenue": ("income", ["revenue", "net_sales", "net_revenue"], ["net", "revenue"]),
    "cogs": ("income", ["cost_of_goods_sold", "cost_of_sales"], ["cost", "sold"]),
    "gross_profit": ("income", ["gross_profit"], ["gross", "profit"]),
    "selling_expense": ("income", ["selling_expenses"], ["selling", "expense"]),
    "admin_expense": ("income", ["general_and_admin_expenses", "general_administrative_expenses"],
                      ["admin", "expense"]),
    "operating_profit": ("income", ["operating_profit", "net_operating_profit",
                                    "operating_profit_loss"], ["operating", "profit"]),
    "financial_income": ("income", ["financial_income", "financial_revenue"], ["financial", "income"]),
    "interest_expense": ("income", ["interest_expenses", "of_which_interest_expenses"],
                         ["interest", "expense"]),
    "pbt": ("income", ["profit_before_tax", "accounting_profit_before_tax"], ["before", "tax"]),
    "tax": ("income", ["corporate_income_tax", "business_income_tax"], ["income", "tax"]),
    "net_income": ("income", ["net_profit", "profit_after_tax"], ["profit", "after", "tax"]),
    "net_income_parent": ("income", ["attributable_to_parent_company",
                                     "net_profit_attributable_to_the_parent_company",
                                     "profit_after_tax_for_shareholders_of_the_parent_company"],
                          ["parent"]),
    "depreciation": ("cashflow", ["depreciation_and_amortisation", "depreciation_and_amortization"],
                     ["depreciation"]),
    "cash": ("balance", ["cash_and_cash_equivalents"], ["cash", "equivalent"]),
    "short_investments": ("balance", ["short_term_investments", "short_term_financial_investments"],
                          ["short", "investment"]),
    "receivables": ("balance", ["short_term_receivables", "accounts_receivable"],
                    ["short", "receivable"]),
    "inventory": ("balance", ["inventories", "net_inventories", "inventory"], ["inventor"]),
    "current_assets": ("balance", ["current_assets", "short_term_assets"], ["current", "assets"]),
    "fixed_assets": ("balance", ["fixed_assets"], ["fixed", "assets"]),
    "total_assets": ("balance", ["total_assets"], ["total", "assets"]),
    "current_liabilities": ("balance", ["current_liabilities", "short_term_liabilities"],
                            ["current", "liabilities"]),
    "short_debt": ("balance", ["short_term_borrowings", "short_term_loans",
                               "short_term_borrowings_and_finance_lease_liabilities"],
                   ["short", "borrowing"]),
    "long_debt": ("balance", ["long_term_borrowings", "long_term_loans",
                              "long_term_borrowings_and_finance_lease_liabilities"],
                  ["long", "borrowing"]),
    "total_liabilities": ("balance", ["liabilities", "total_liabilities"], ["liabilities"]),
    "equity": ("balance", ["owners_equity", "owners_equity_2", "owners_equity_3", "equity",
                           "capital_and_reserves"], ["equity"]),
    "minority_interest": ("balance", ["minority_interests", "non_controlling_interests"],
                          ["minority"]),
    "cfo": ("cashflow", ["operating_cash_flow", "net_cash_flows_from_operating_activities"],
            ["operating", "activities"]),
    "capex": ("cashflow", ["purchase_of_fixed_assets",
                           "purchases_of_fixed_assets_and_other_long_term_assets"],
              ["purchase", "fixed"]),
    "cfi": ("cashflow", ["investing_cash_flow", "net_cash_flows_from_investing_activities"],
            ["investing", "activities"]),
    "cff": ("cashflow", ["financing_cash_flow", "net_cash_flows_from_financing_activities"],
            ["financing", "activities"]),
    "dividends_paid": ("cashflow", ["dividends_paid", "dividends_paid_to_owners"], ["dividend"]),
    "net_interest_income": ("income", ["net_interest_income"], ["net", "interest", "income"]),
    "fee_income": ("income", ["net_fee_and_commission_income"], ["fee", "commission"]),
    "total_operating_income": ("income", ["total_operating_income"], ["total", "operating", "income"]),
    "operating_expense": ("income", ["general_and_administrative_expenses", "operating_expenses"],
                          ["operating", "expenses"]),
    "provision": ("income", ["provision_for_credit_losses"], ["provision", "credit"]),
    "loans": ("balance", ["loans_advances_and_finance_leases_to_customers"], ["loans", "customers"]),
    "deposits": ("balance", ["deposits_from_customers"], ["deposits", "customers"]),
}

# ----------------------------- anh xa ten tieng Viet (vnfinancialdata / BCTC goc)
# Moi field: danh sach mau regex tren ten DA BO DAU, khop dong DAU TIEN.
_VI_PATTERNS: dict[str, list[str]] = {
    "revenue": [r"^doanh thu thuan( ve ban hang)?", r"^doanh thu thuan"],
    "cogs": [r"^gia von hang ban"],
    "gross_profit": [r"^loi nhuan gop"],
    "selling_expense": [r"^chi phi ban hang"],
    "admin_expense": [r"^chi phi quan ly doanh nghiep"],
    "operating_profit": [r"^loi nhuan thuan tu hoat dong kinh doanh"],
    "financial_income": [r"^doanh thu hoat dong tai chinh"],
    "interest_expense": [r"chi phi lai vay"],
    "pbt": [r"^tong loi nhuan ke toan truoc thue", r"^loi nhuan truoc thue"],
    "net_income": [r"^loi nhuan sau thue thu nhap doanh nghiep", r"^loi nhuan sau thue"],
    "net_income_parent": [r"cong ty me", r"chu so huu cua (cong ty|ngan hang) me"],
    "depreciation": [r"^khau hao"],
    "cash": [r"^tien va cac khoan tuong duong tien"],
    "inventory": [r"^hang ton kho"],
    "receivables": [r"^cac khoan phai thu ngan han"],
    "current_assets": [r"^tai san ngan han"],
    "fixed_assets": [r"^tai san co dinh"],
    "total_assets": [r"^tong (cong )?tai san"],
    "current_liabilities": [r"^no ngan han"],
    "short_debt": [r"^vay va no thue tai chinh ngan han", r"^vay ngan han"],
    "long_debt": [r"^vay va no thue tai chinh dai han", r"^vay dai han"],
    "total_liabilities": [r"^no phai tra"],
    "equity": [r"^von chu so huu", r"^von va cac quy"],
    "cfo": [r"^luu chuyen tien thuan tu hoat dong kinh doanh"],
    "capex": [r"^tien chi (de )?mua sam, xay dung tai san co dinh"],
    "cfi": [r"^luu chuyen tien thuan tu hoat dong dau tu"],
    "cff": [r"^luu chuyen tien thuan tu hoat dong tai chinh"],
    "dividends_paid": [r"co tuc, loi nhuan da tra"],
    "net_interest_income": [r"^thu nhap lai thuan"],
    "fee_income": [r"^lai thuan tu hoat dong dich vu"],
    "total_operating_income": [r"^tong thu nhap hoat dong"],
    "operating_expense": [r"^chi phi hoat dong"],
    "provision": [r"^chi phi du phong rui ro tin dung"],
    "loans": [r"^cho vay khach hang"],
    "deposits": [r"^tien gui cua khach hang"],
}


def strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower().strip()


@dataclass
class StandardFinancials:
    """BCTC nam da chuan hoa. `frame`: index = nam (int, tang dan), cot = field chuan."""

    symbol: str
    frame: pd.DataFrame
    source: str
    mapping: dict[str, str] = field(default_factory=dict)  # field -> ten cot goc
    ratios_history: pd.DataFrame = field(default_factory=pd.DataFrame)  # nam x (pe, pb, roe...)
    notes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.frame is None or self.frame.empty

    @property
    def years(self) -> list[int]:
        return [] if self.empty else [int(y) for y in self.frame.index]

    def get(self, name: str, year: int | None = None):
        """Gia tri mot chi tieu (nam gan nhat neu khong chi dinh). None neu khong co."""
        if self.empty or name not in self.frame.columns:
            return None
        series = self.frame[name]
        if year is None:
            series = series.dropna()
            return None if series.empty else float(series.iloc[-1])
        if year not in series.index or pd.isna(series.loc[year]):
            return None
        return float(series.loc[year])

    def series(self, name: str) -> pd.Series:
        if self.empty or name not in self.frame.columns:
            return pd.Series(dtype=float)
        return pd.to_numeric(self.frame[name], errors="coerce")

    def last_year(self) -> int | None:
        return self.years[-1] if self.years else None


# ------------------------------------------------------------------- tien ich
def _year_of(period) -> int | None:
    match = re.search(r"(19|20)\d{2}", str(period))
    return int(match.group(0)) if match else None


def _pick_column(frame: pd.DataFrame, exact: list[str], keywords: list[str]) -> str | None:
    if frame is None or frame.empty:
        return None
    cols = [str(c) for c in frame.columns]
    for name in exact:
        if name in cols:
            return name
    if keywords:
        for col in cols:
            low = col.lower()
            if all(k in low for k in keywords):
                return col
    return None


def standardize_vnstock(symbol: str, bundle: dict[str, pd.DataFrame]) -> StandardFinancials:
    """dict {income, balance, cashflow, ratios} (dang router.financials(period="year"))
    -> StandardFinancials."""
    out: dict[str, pd.Series] = {}
    mapping: dict[str, str] = {}
    for fld, (part, exact, keywords) in _VNSTOCK_CANDIDATES.items():
        frame = bundle.get(part)
        if frame is None or frame.empty or "period" not in frame.columns:
            continue
        col = _pick_column(frame.drop(columns=["period"]), exact, keywords)
        if col is None:
            continue
        years = frame["period"].map(_year_of)
        series = pd.Series(pd.to_numeric(frame[col], errors="coerce").to_numpy(), index=years)
        series = series[series.index.notna()]
        series.index = series.index.astype(int)
        out[fld] = series[~series.index.duplicated(keep="last")]
        mapping[fld] = f"vnstock/{part}.{col}"

    frame = pd.DataFrame(out).sort_index()
    if "capex" in frame.columns:
        frame["capex"] = -frame["capex"].abs()  # quy uoc: capex la so am (tien chi ra)
    ratios = _standardize_ratio_history(bundle.get("ratios"))
    return StandardFinancials(symbol.upper(), frame, "vnstock (Vietcap/VCI)", mapping, ratios)


_RATIO_HISTORY_CANDIDATES = {
    "pe": ["pe_ratio", "pe", "price_to_earning"],
    "pb": ["pb_ratio", "pb", "price_to_book"],
    "roe": ["roe"],
    "roa": ["roa"],
    "eps": ["trailing_eps", "eps", "earning_per_share"],
    "bvps": ["book_value_per_share", "bvps"],
    "ev_ebitda": ["ev_to_ebitda", "ev_ebitda", "value_before_ebitda"],
    "market_cap": ["market_capital", "market_cap"],
    "dividend_yield": ["dividend_yield"],
    "nim": ["nim", "net_interest_margin"],
}


def _standardize_ratio_history(ratios: pd.DataFrame | None) -> pd.DataFrame:
    if ratios is None or ratios.empty or "period" not in ratios.columns:
        return pd.DataFrame()
    years = ratios["period"].map(_year_of)
    out = {}
    for key, cands in _RATIO_HISTORY_CANDIDATES.items():
        col = _pick_column(ratios.drop(columns=["period"]), cands, [])
        if col:
            out[key] = pd.Series(pd.to_numeric(ratios[col], errors="coerce").to_numpy(), index=years)
    frame = pd.DataFrame(out)
    frame = frame[frame.index.notna()]
    frame.index = frame.index.astype(int)
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def standardize_long_vi(symbol: str, long: pd.DataFrame, source: str) -> StandardFinancials:
    """Bang dai (ticker, year, item_name, value) ten tieng Viet -> StandardFinancials.
    Dung cho vnfinancialdata va bat ky nguon nao co ten chi tieu theo mau BCTC VN."""
    if long is None or long.empty:
        return StandardFinancials(symbol.upper(), pd.DataFrame(), source)
    long = long.copy()
    long["norm"] = long["item_name"].map(strip_accents)
    long["year"] = pd.to_numeric(long["year"], errors="coerce")
    out, mapping = {}, {}
    for fld, patterns in _VI_PATTERNS.items():
        for pat in patterns:
            hit = long[long["norm"].str.contains(pat.replace("(", "(?:"), regex=True, na=False)]
            if hit.empty:
                continue
            first_name = hit["item_name"].iloc[0]
            rows = hit[hit["item_name"] == first_name]
            series = rows.groupby("year")["value"].last()
            out[fld] = pd.to_numeric(series, errors="coerce")
            mapping[fld] = f"{source}: {first_name}"
            break
    frame = pd.DataFrame(out).sort_index()
    frame = frame[frame.index.notna()]
    frame.index = frame.index.astype(int)
    if "capex" in frame.columns:
        frame["capex"] = -frame["capex"].abs()
    return StandardFinancials(symbol.upper(), frame, source, mapping)


# --------------------------------------------------------------------- nguon
def from_router(symbol: str) -> StandardFinancials | None:
    try:
        from .router import get_router

        bundle = get_router().financials(symbol, period="year")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.warning("router.financials(%s) loi: %s", symbol, exc)
        return None
    if all(f is None or f.empty for f in bundle.values()):
        return None
    std = standardize_vnstock(symbol, bundle)
    return None if std.empty else std


def from_vnfinancialdata(symbol: str, exchange: str | None = None) -> StandardFinancials | None:
    try:
        import vnfinancialdata as vfd  # type: ignore
    except ImportError:
        return None
    exchanges = [exchange] if exchange in ("HSX", "HNX") else ["HSX", "HNX"]
    if exchange == "HOSE":
        exchanges = ["HSX"]
    frames = []
    for exch in exchanges:
        for statement in ("income_statement", "balance_sheet", "cash_flow"):
            try:
                frames.append(vfd.get(ticker=symbol.upper(), statement=statement, exchange=exch))
            except Exception as exc:  # noqa: BLE001 - can dang nhap HF, khong co ma...
                log.debug("vnfinancialdata %s/%s/%s: %s", symbol, exch, statement, exc)
        if frames and any(not f.empty for f in frames):
            break
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return None
    std = standardize_long_vi(symbol, pd.concat(frames, ignore_index=True),
                              "vnfinancialdata (HuggingFace, Ngô Phú Thạnh – UEL)")
    return None if std.empty else std


def from_manual(symbol: str) -> StandardFinancials | None:
    path = MANUAL_DIR / f"{symbol.upper()}_financials.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "year" not in frame.columns:
        log.warning("%s thieu cot year", path)
        return None
    frame = frame.set_index("year").sort_index()
    frame.index = frame.index.astype(int)
    keep = [c for c in frame.columns if c in STANDARD_FIELDS]
    ratio_cols = [c for c in frame.columns if c in _RATIO_HISTORY_CANDIDATES]
    mapping = {c: f"file tay {path.name}" for c in keep}
    return StandardFinancials(symbol.upper(), frame[keep].apply(pd.to_numeric, errors="coerce"),
                              f"File nhập tay ({path.name})", mapping,
                              frame[ratio_cols].apply(pd.to_numeric, errors="coerce"))


def load_financials(symbol: str, exchange: str | None = None, years: int = 5,
                    allow_demo: bool = True) -> StandardFinancials:
    """Thu lan luot cac nguon, tra ve StandardFinancials (co the rong)."""
    symbol = symbol.upper()
    from . import demo

    if demo.is_demo(symbol):
        if not allow_demo:
            return StandardFinancials(symbol, pd.DataFrame(), "—", notes=["Ma demo bi tat"])
        std = demo.financials(symbol)
    else:
        std = None
        tried = []
        for name, loader in (("manual", lambda: from_manual(symbol)),
                             ("vnstock", lambda: from_router(symbol)),
                             ("vnfinancialdata", lambda: from_vnfinancialdata(symbol, exchange))):
            std = loader()
            tried.append(name)
            if std is not None and not std.empty:
                break
        if std is None or std.empty:
            return StandardFinancials(symbol, pd.DataFrame(), "—",
                                      notes=[f"Không lấy được BCTC từ: {', '.join(tried)}"])
    std.frame = std.frame.tail(years)
    _fill_derived(std)
    return std


def _fill_derived(std: StandardFinancials) -> None:
    """Bo sung chi tieu SUY RA TRUC TIEP tu chi tieu khac (ghi ro trong mapping)."""
    f = std.frame
    if f.empty:
        return
    def derive(name, values, how):
        if name not in f.columns or f[name].isna().all():
            f[name] = values
            std.mapping[name] = f"tính: {how}"
    if "net_income_parent" not in f.columns or f["net_income_parent"].isna().all():
        if "net_income" in f.columns:
            mi = f["minority_interest"] if "minority_interest" in f.columns else None
            derive("net_income_parent", f["net_income"], "= LNST (không tách được CĐ thiểu số)")
            del mi
    if "gross_profit" in f.columns and "revenue" in f.columns and "cogs" not in f.columns:
        derive("cogs", f["gross_profit"] - f["revenue"], "LN gộp − doanh thu")
    if {"total_assets", "equity"} <= set(f.columns):
        derive("total_liabilities", f["total_assets"] - f["equity"], "tổng TS − VCSH")
