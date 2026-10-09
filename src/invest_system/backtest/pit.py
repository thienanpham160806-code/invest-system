"""BCTC POINT-IN-TIME: tai ngay `as_of` chi duoc thay cac ky DA CONG BO.

Backtest dung BCTC chua cong bo la nguon nhin truoc pho bien nhat: LNST nam
2024 chi co tu cuoi thang 3/2025, nhung bang BCTC ghi "2024" nen rat de dung no
cho tin hieu thang 1/2025. Module nay gan cho moi ky ngay `available_from` va
chi tra ve ky co `available_from <= as_of`.

Quy tac (docs/phase2/backtest-design.md, muc 3):
  - Co ngay cong bo that (`published_at`) -> dung tu ngay cong bo + 1 ngay
    (tin dang sau gio giao dich chi dung duoc tu phien sau).
  - Khong co -> BCTC nam: 01/04 nam sau; quy 1-3: cuoi quy + 45 ngay;
    quy 4: cuoi quy + 60 ngay. Day la dem bao thu so voi han nop cua
    TT 96/2020 (nam 90 ngay, quy 20/30 ngay).
  - `published_at` truoc ngay ket thuc ky la du lieu hong -> bo, dung quy tac.

Nhieu dong cung mot ky (ban goc + ban dieu chinh hoi to, moi dong co
`published_at` rieng) duoc hieu la cac "vintage": tai `as_of` lay ban MOI NHAT
da cong bo. Kho hien tai (arminer, vnstock) chi giu ban cuoi cung nen rui ro
restatement van con - ghi trong tai lieu thiet ke.

Dang du lieu: mot dong = mot (symbol, year, quarter); quarter = 0 la BCTC nam,
1-4 la quy; cot `published_at` tuy chon; cac cot con lai la chi tieu chuan
(data/fundamentals.STANDARD_FIELDS).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..logging_conf import get_logger

log = get_logger(__name__)

ANNUAL = 0
KEY_COLUMNS = ["symbol", "year", "quarter"]
META_COLUMNS = ["period_end", "available_from", "available_basis"]
BASIS_ACTUAL = "ngày công bố thật"
BASIS_RULE = "quy tắc trễ chuẩn"


@dataclass(frozen=True)
class DisclosureRules:
    """Do tre cong bo khi KHONG co ngay that."""

    annual_month: int = 4                                 # BCTC nam Y dung tu 01/04/Y+1
    annual_day: int = 1
    quarter_lag_days: tuple[int, int, int, int] = (45, 45, 45, 60)  # Q1..Q4
    actual_delay_days: int = 1                            # ngay cong bo that + 1


DEFAULT_RULES = DisclosureRules()


def period_end(year: int, quarter: int = ANNUAL) -> pd.Timestamp:
    """Ngay ket thuc ky. Nam tai chinh gia dinh ket thuc 31/12 (DN co nam tai
    chinh khac bi dung MUON hon thuc te - sai ve phia an toan)."""
    if quarter == ANNUAL:
        return pd.Timestamp(year=int(year), month=12, day=31)
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quý không hợp lệ: {quarter}")
    return pd.Timestamp(year=int(year), month=3 * int(quarter), day=1) + pd.offsets.MonthEnd(0)


def rule_available_from(year: int, quarter: int = ANNUAL,
                        rules: DisclosureRules = DEFAULT_RULES) -> pd.Timestamp:
    if quarter == ANNUAL:
        return pd.Timestamp(year=int(year) + 1, month=rules.annual_month, day=rules.annual_day)
    return period_end(year, quarter) + pd.Timedelta(days=rules.quarter_lag_days[int(quarter) - 1])


def available_from(year: int, quarter: int = ANNUAL, published_at=None,
                   rules: DisclosureRules = DEFAULT_RULES) -> tuple[pd.Timestamp, str]:
    """(ngay dau tien duoc dung ky nay, can cu)."""
    end = period_end(year, quarter)
    if published_at is not None and not pd.isna(published_at):
        published = pd.Timestamp(published_at).normalize()
        if published > end:
            return published + pd.Timedelta(days=rules.actual_delay_days), BASIS_ACTUAL
        log.warning("Ngày công bố %s trước ngày kết thúc kỳ %s Q%s - bỏ, dùng quy tắc",
                    published.date(), year, quarter)
    return rule_available_from(year, quarter, rules), BASIS_RULE


def annotate(statements: pd.DataFrame, rules: DisclosureRules = DEFAULT_RULES) -> pd.DataFrame:
    """Them period_end, available_from, available_basis cho moi dong."""
    missing = [c for c in KEY_COLUMNS if c not in statements.columns]
    if missing:
        raise ValueError(f"thiếu cột {missing}")
    frame = statements.copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["year"] = frame["year"].astype(int)
    frame["quarter"] = frame["quarter"].fillna(ANNUAL).astype(int)
    published = frame["published_at"] if "published_at" in frame.columns else [None] * len(frame)
    stamped = [available_from(y, q, p, rules)
               for y, q, p in zip(frame["year"], frame["quarter"], published, strict=True)]
    frame["period_end"] = [period_end(y, q) for y, q in zip(frame["year"], frame["quarter"], strict=True)]
    frame["available_from"] = [s[0] for s in stamped]
    frame["available_basis"] = [s[1] for s in stamped]
    return frame


def as_of_view(annotated: pd.DataFrame, as_of, freq: str = "all") -> pd.DataFrame:
    """Cac ky da cong bo tai `as_of` (ban moi nhat cua moi ky), sap theo period_end.

    freq: "all" | "annual" | "quarter".
    """
    cutoff = pd.Timestamp(as_of).normalize()
    view = annotated[annotated["available_from"] <= cutoff]
    if freq == "annual":
        view = view[view["quarter"] == ANNUAL]
    elif freq == "quarter":
        view = view[view["quarter"] != ANNUAL]
    elif freq != "all":
        raise ValueError(f"freq không hợp lệ: {freq}")
    if view.empty:
        return view.reset_index(drop=True)
    view = (view.sort_values([*KEY_COLUMNS, "available_from"], kind="stable")
                .drop_duplicates(KEY_COLUMNS, keep="last"))
    return view.sort_values(["symbol", "period_end", "quarter"], kind="stable").reset_index(drop=True)


class PointInTimeStore:
    """Kho BCTC da gan ngay cong bo; truy van theo (ma, ngay)."""

    def __init__(self, statements: pd.DataFrame, rules: DisclosureRules = DEFAULT_RULES):
        self.rules = rules
        self.frame = annotate(statements, rules) if not statements.empty else pd.DataFrame(
            columns=[*KEY_COLUMNS, *META_COLUMNS])
        self._by_symbol = {s: g for s, g in self.frame.groupby("symbol")} if not self.frame.empty else {}

    def available_financials(self, symbol: str, as_of, freq: str = "all") -> pd.DataFrame:
        part = self._by_symbol.get(str(symbol).upper())
        if part is None:
            return pd.DataFrame(columns=self.frame.columns)
        return as_of_view(part, as_of, freq)

    def latest(self, symbol: str, as_of, freq: str = "annual") -> pd.Series | None:
        view = self.available_financials(symbol, as_of, freq)
        return None if view.empty else view.iloc[-1]


# ------------------------------------------------------------------ kho mac dinh
def _quarterly_path() -> Path:
    from ..data.arminer_bctc import REF_DIR
    return REF_DIR / "bctc_quarterly.parquet"


def _annual_rows(symbol: str) -> pd.DataFrame:
    from ..data.arminer_bctc import from_arminer
    std = from_arminer(symbol)
    if std is None or std.empty:
        return pd.DataFrame()
    frame = std.frame.copy()
    frame.index.name = "year"
    frame = frame.reset_index()
    frame.insert(0, "symbol", symbol.upper())
    frame["quarter"] = ANNUAL
    return frame


def _quarterly_rows(symbol: str) -> pd.DataFrame:
    path = _quarterly_path()
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path, filters=[("symbol", "==", symbol.upper())])
    return frame


@lru_cache(maxsize=4096)
def _default_store(symbol: str) -> PointInTimeStore:
    parts = [p for p in (_annual_rows(symbol), _quarterly_rows(symbol)) if not p.empty]
    return PointInTimeStore(pd.concat(parts, ignore_index=True) if parts else pd.DataFrame())


def reset_default_store() -> None:
    """Xoa cache kho mac dinh - goi sau khi cap nhat BCTC (arminer / bctc_quarterly)
    trong cung tien trinh, neu khong se doc mai ban da nap lan dau."""
    _default_store.cache_clear()


def available_financials(symbol: str, as_of, freq: str = "all",
                         store: PointInTimeStore | None = None) -> pd.DataFrame:
    """BCTC cua `symbol` da cong bo tai `as_of`.

    `store=None`: BCTC nam arminer (+ vnstock bo sung) va BCTC quy
    `data/reference/bctc_quarterly.parquet` neu co. Ket qua co them cot
    period_end, available_from, available_basis de kiem tra.
    """
    store = store if store is not None else _default_store(str(symbol).upper())
    return store.available_financials(symbol, as_of, freq)
