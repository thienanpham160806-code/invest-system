"""BCTC NAM tu bo du lieu dong goi trong repo vn-annual-report-miner (Tumiqa, MIT).

Nguon goc: `src/arminer/data/bctc_data/{balance_sheet,income_statement,cash_flow}/{HSX,HNX}.parquet`
(cot: ticker, year, exchange, statement, item_code, item_name, value - don vi VND),
phu 2009-FY2025, HSX 409 ma + HNX 307 ma, KHONG co UPCOM, KHONG co quy.
Ban sao + giay phep: data/reference/arminer/ (xem docs/data-sources.md).

De doc nhanh tren Vercel (khong nap 1,9 trieu dong ~1 GB RAM moi request),
`repack()` gop 6 file thanh MOT parquet sap theo ticker, row group nho ->
`pyarrow` chi doc cac row group cua ma can xem (filter pushdown).

Anh xa item_code -> chi tieu chuan (StandardFinancials): moi chi tieu co danh
sach UNG VIEN (regex fullmatch) theo thu tu uu tien; ma co hau to hash (vd
`bs_von_chu_so_huu_4d280b22`) khop bang mau `[0-9a-f]{8}`. Ung vien dau tien
co gia tri khac 0 duoc dung, nam nao thieu thi bu tu ung vien sau. Moi lua chon
ghi vao `mapping` -> tab "Du lieu & nguon" / phu luc PDF.
"""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..config import PROJECT_ROOT
from ..logging_conf import get_logger
from .fundamentals import StandardFinancials

log = get_logger(__name__)

SOURCE_NAME = "BCTC năm – vn-annual-report-miner (Tumiqa, MIT)"
REF_DIR = Path(os.getenv("REFERENCE_DIR", str(PROJECT_ROOT / "data" / "reference")))
RAW_DIR = REF_DIR / "arminer" / "bctc_data"
PACKED = Path(os.getenv("WEBDATA_DIR", str(PROJECT_ROOT / "webdata"))) / "bctc_long.parquet"
VNSTOCK_PACKED = REF_DIR / "bctc_vnstock.parquet"
STATEMENTS = {"bs": "balance_sheet", "is": "income_statement", "cf": "cash_flow"}

_H = r"[0-9a-f]{8}"  # hau to hash cua item_code trung ten

# field -> danh sach regex item_code (fullmatch), theo thu tu uu tien
FIELD_CODES: dict[str, list[str]] = {
    # ---- KQKD
    "revenue": ["is_doanh_so_thuan", "is_tong_thu_nhap_hoat_dong", "is_doanh_thu_hoat_dong",
                "is_doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem", "is_doanh_thu_thuan"],
    "cogs": ["is_gia_von_hang_ban"],
    "gross_profit": ["is_lai_gop"],
    "selling_expense": ["is_chi_phi_ban_hang"],
    "admin_expense": ["is_chi_phi_quan_ly_doanh_nghiep"],
    "operating_profit": ["is_lai_lo_tu_hoat_dong_kinh_doanh"],
    "interest_expense": ["is_trong_do_chi_phi_lai_vay"],
    "pbt": ["is_lai_lo_rong_truoc_thue", "is_tong_loi_nhuan_truoc_thue",
            "is_tong_loi_nhuan_ke_toan_truoc_thue"],
    "net_income": ["is_lai_lo_thuan_sau_thue", "is_loi_nhuan_sau_thue",
                   "is_loi_nhuan_ke_toan_sau_thue", "is_loi_nhuan_sau_thue_thu_nhap_doanh_nghiep"],
    "net_income_parent": ["is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_co_dong_cua_cong_ty_me",
                          "is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu",
                          "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan"],
    "ebit": ["is_ebit"],
    "ebitda": ["is_ebitda"],
    "eps_reported": ["is_lai_co_ban_tren_co_phieu"],
    # ngan hang
    "net_interest_income": ["is_thu_nhap_lai_thuan"],
    "fee_income": ["is_lai_thuan_tu_hoat_dong_dich_vu"],
    "total_operating_income": ["is_tong_thu_nhap_hoat_dong"],
    "operating_expense": ["is_chi_phi_hoat_dong"],
    "provision": ["is_chi_phi_du_phong_rui_ro_tin_dung"],
    # ---- CDKT
    "total_assets": ["bs_tong_tai_san", "bs_tong_cong_tai_san"],
    "total_liabilities": ["bs_no_phai_tra", "bs_tong_no_phai_tra"],
    "current_liabilities": ["bs_no_ngan_han"],
    "current_assets": ["bs_tai_san_ngan_han"],
    "cash": ["bs_tien_va_tuong_duong_tien"],
    "short_investments": ["bs_gia_tri_thuan_dau_tu_ngan_han"],
    "receivables": ["bs_cac_khoan_phai_thu"],
    "inventory": [f"bs_hang_ton_kho_rong_{_H}", "bs_hang_ton_kho"],
    "fixed_assets": ["bs_tai_san_co_dinh"],
    "short_debt": ["bs_vay_ngan_han"],
    "long_debt": ["bs_vay_dai_han"],
    "equity": [f"bs_von_chu_so_huu_{_H}"],  # GOM loi ich CD khong kiem soat
    "minority_interest": ["bs_loi_ich_co_dong_khong_kiem_soat", "bs_loi_ich_co_dong_thieu_so"],
    "charter_capital": ["bs_von_gop", "bs_von_dieu_le", "bs_von_dau_tu_cua_chu_so_huu", "bs_von_co_phan"],
    "loans": ["bs_cho_vay_khach_hang"],
    "deposits": ["bs_tien_gui_cua_khach_hang"],
    # ---- LCTT
    "cfo": ["cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh",
            "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh",
            "cf_luu_chuyen_thuan_tu_hoat_dong_kinh_doanh_chung_khoan"],
    "capex": ["cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac",
              "cf_tien_chi_de_mua_sam_xay_dung_tscd_va_cac_tai_san_dai_han_khac"],
    "cfi": ["cf_luu_chuyen_tien_thuan_tu_hoat_dong_dau_tu", "cf_luu_chuyen_tu_hoat_dong_dau_tu"],
    "cff": ["cf_luu_chuyen_tien_thuan_tu_hoat_dong_tai_chinh",
            "cf_luu_chuyen_thuan_tu_hoat_dong_tai_chinh"],
    "depreciation": ["cf_khau_hao_tscd", "cf_khau_hao_tai_san_co_dinh"],
    "dividends_paid": ["cf_co_tuc_da_tra", "cf_co_tuc_loi_nhuan_da_tra_cho_chu_so_huu?"],
}
# chi tieu ma gia tri 0 chac chan la "khong co du lieu" (DN niem yet khong the = 0)
_ZERO_IS_MISSING = {"revenue", "total_assets", "equity", "total_liabilities", "net_income",
                    "net_income_parent", "pbt", "charter_capital", "eps_reported", "ebit", "ebitda"}


# ------------------------------------------------------------------ luu tru
def repack(out: Path = PACKED, row_group_size: int = 20_000) -> Path:
    """Gop 6 file goc -> mot parquet sap theo ticker (chay mot lan, local)."""
    frames = []
    for st in STATEMENTS.values():
        for exch in ("HSX", "HNX"):
            path = RAW_DIR / st / f"{exch}.parquet"
            if path.exists():
                frames.append(pd.read_parquet(path, columns=[
                    "ticker", "year", "exchange", "statement", "item_code", "item_name", "value"]))
    if not frames:
        raise FileNotFoundError(f"Khong thay du lieu arminer trong {RAW_DIR}")
    long = pd.concat(frames, ignore_index=True)
    # giu THU TU DONG GOC cua mau bieu (de hien BCTC dung trinh tu CDKT/KQKD/LCTT)
    long["line_no"] = long.groupby(["ticker", "statement", "year"]).cumcount().astype("int32")
    long = long.sort_values(["ticker", "statement", "year", "line_no"], kind="stable")
    for col in ("ticker", "exchange", "statement"):
        long[col] = long[col].astype(str)
    long.to_parquet(out, index=False, row_group_size=row_group_size, compression="zstd")
    log.info("repack arminer -> %s (%d dong)", out, len(long))
    return out


def _source_path() -> Path | None:
    if PACKED.exists():
        return PACKED
    return None


@lru_cache(maxsize=1)
def coverage() -> pd.DataFrame:
    """(ticker, exchange, first_year, last_year) cho moi ma co BCTC."""
    frames = []
    path = _source_path()
    if path is not None:
        frames.append(pd.read_parquet(path, columns=["ticker", "exchange", "year"]))
    supplement = _vnstock_supplement()
    if not supplement.empty:
        frames.append(supplement[["ticker", "exchange", "year"]])
    if not frames:
        return pd.DataFrame(columns=["ticker", "exchange", "first_year", "last_year"])
    frame = pd.concat(frames, ignore_index=True).drop_duplicates()
    return (frame.groupby("ticker").agg(exchange=("exchange", "first"),
                                        first_year=("year", "min"), last_year=("year", "max"))
            .reset_index())


def has_symbol(symbol: str) -> bool:
    cov = coverage()
    return not cov.empty and symbol.upper() in set(cov["ticker"])


@lru_cache(maxsize=128)
def _vnstock_supplement() -> pd.DataFrame:
    if VNSTOCK_PACKED.exists():
        return pd.read_parquet(VNSTOCK_PACKED)
    base = os.getenv("BLOB_BASE_URL", "").rstrip("/")
    if not base:
        return pd.DataFrame()
    try:
        import requests

        response = requests.get(f"{base}/universe/bctc_vnstock.parquet", timeout=8)
        response.raise_for_status()
        return pd.read_parquet(io.BytesIO(response.content))
    except Exception as exc:  # noqa: BLE001
        log.warning("Khong tai duoc BCTC vnstock tu Blob: %s", exc)
        return pd.DataFrame()


@lru_cache(maxsize=128)
def raw_long(symbol: str, exchange: str | None = None) -> pd.DataFrame:
    """Toan bo dong BCTC goc cua mot ma (dang dai)."""
    symbol = symbol.upper()
    exchange = exchange.upper() if exchange else None
    parts = []
    if exchange != "UPCOM":
        path = _source_path()
        if path is not None:
            parts.append(pd.read_parquet(path, filters=[("ticker", "==", symbol)]))
    supplement = _vnstock_supplement()
    if not supplement.empty:
        extra = supplement[supplement["ticker"].astype(str).str.upper() == symbol]
        if exchange:
            extra = extra[extra["exchange"].astype(str).str.upper() == exchange]
        if not extra.empty:
            parts.append(extra)
    if not parts:
        return pd.DataFrame()
    frame = pd.concat(parts, ignore_index=True)
    if "source" in frame.columns:
        # Keep the packaged source first; VCI only fills missing report rows.
        frame["_source_priority"] = frame["source"].isna().astype(int)
        frame = frame.sort_values("_source_priority").drop_duplicates(
            subset=["ticker", "year", "statement", "item_code"], keep="last"
        ).drop(columns="_source_priority")
    else:
        frame = frame.drop_duplicates(subset=["ticker", "year", "statement", "item_code"], keep="last")
    frame["year"] = frame["year"].astype(int)
    return frame


def raw_statement(symbol: str, statement: str, years: int = 5, exchange: str | None = None) -> pd.DataFrame:
    """Bao cao goc dang rong: hang = (item_code, item_name), cot = nam. Giu thu tu dong goc.
    Bo dong toan 0/NaN (mau bieu chung cua arminer gom ca chi tieu nganh khac)."""
    st = STATEMENTS.get(statement, statement)
    long = raw_long(symbol.upper(), exchange)
    if long.empty:
        return pd.DataFrame()
    part = long[long["statement"] == st]
    if part.empty:
        return pd.DataFrame()
    keep_years = sorted(part["year"].unique())[-years:]
    part = part[part["year"].isin(keep_years)]
    if "line_no" in part.columns:  # thu tu dong goc (nam gan nhat uu tien)
        part = part.sort_values(["year", "line_no"], ascending=[False, True])
    order = part.drop_duplicates("item_code")[["item_code", "item_name"]]
    wide = part.pivot_table(index="item_code", columns="year", values="value", aggfunc="last")
    wide = order.set_index("item_code").join(wide, how="left")
    values = wide.drop(columns=["item_name"])
    wide = wide[(values.fillna(0) != 0).any(axis=1)]
    return wide.reset_index()


# ---------------------------------------------------------------- chuan hoa
def _pick(long: pd.DataFrame, patterns: list[str], zero_missing: bool) -> tuple[pd.Series, list[str]]:
    codes = long["item_code"].unique()
    result = pd.Series(dtype=float)
    used: list[str] = []
    for pat in patterns:
        rx = re.compile(pat)
        hits = [c for c in codes if rx.fullmatch(c)]
        for code in hits:
            series = long[long["item_code"] == code].groupby("year")["value"].last()
            series = pd.to_numeric(series, errors="coerce")
            if zero_missing:
                series = series.where(series != 0)
            if series.dropna().empty or (series.fillna(0) == 0).all():
                continue
            if result.empty:
                result = series
            else:
                result = result.combine_first(series)
            used.append(code)
            break
    return result, used


def standardize(symbol: str, long: pd.DataFrame) -> StandardFinancials:
    out: dict[str, pd.Series] = {}
    mapping: dict[str, str] = {}
    names = long.drop_duplicates("item_code").set_index("item_code")["item_name"].to_dict()
    for fld, patterns in FIELD_CODES.items():
        series, used = _pick(long, patterns, fld in _ZERO_IS_MISSING)
        if series.empty:
            continue
        out[fld] = series
        mapping[fld] = "arminer: " + " | ".join(f"{c} ({names.get(c, '')})" for c in used)
    frame = pd.DataFrame(out).sort_index()
    frame.index = frame.index.astype(int)
    notes: list[str] = []
    # Loi nguon da gap (vd SSI): nam cuoi la BAN SAO nam truoc (TS, DT, LNST trung khop tung dong)
    key = [c for c in ("total_assets", "revenue", "net_income") if c in frame.columns]
    while len(frame) >= 2 and key:
        last, prev = frame.iloc[-1][key], frame.iloc[-2][key]
        if last.notna().all() and (last == prev).all():
            notes.append(f"FY{int(frame.index[-1])} trùng khớp hoàn toàn FY{int(frame.index[-2])} "
                         "(lỗi sao chép ở nguồn) – đã loại năm này")
            frame = frame.iloc[:-1]
        else:
            break
    if "capex" in frame.columns:
        frame["capex"] = -frame["capex"].abs()  # quy uoc: tien chi ra la so am
    if "eps_reported" in frame.columns:
        bad = frame["eps_reported"].abs() > 1e6  # vd SSI: nguon ghi nham LNST vao dong EPS
        if bad.any():
            frame.loc[bad, "eps_reported"] = float("nan")
            notes.append("EPS báo cáo bất thường (>1 triệu đ) ở một số năm – bỏ, dùng EPS tự tính")
    return StandardFinancials(symbol.upper(), frame, SOURCE_NAME, mapping, notes=notes)


def from_arminer(symbol: str, exchange: str | None = None) -> StandardFinancials | None:
    try:
        long = raw_long(symbol.upper(), exchange)
    except Exception as exc:  # noqa: BLE001
        log.warning("arminer %s loi: %s", symbol, exc)
        return None
    if long.empty:
        return None
    std = standardize(symbol, long)
    if "source" in long.columns:
        sources = sorted(set(long["source"].dropna().astype(str)))
        if sources:
            std.source = " + ".join(sources)
    return None if std.empty else std
