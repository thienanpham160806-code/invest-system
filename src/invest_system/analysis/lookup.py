"""Tra cuu ma: ho so doanh nghiep, chi so tai chinh chinh, cap nhat gan day.

Giai quyet van de: nguoi dung go /tracuu MA can mot khoi thong tin tong hop
de biet minh dang xem cong ty gi, truoc khi quan tam den tin hieu ky thuat.
Moi du lieu di qua data/router.py (khong goi thang nha cung cap). Truong nao
KHONG lay duoc thi de None - formatters.py se hien "khong co du lieu", tuyet
doi khong bia so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from ..data.router import DataRouter, get_router
from ..logging_conf import get_logger

log = get_logger(__name__)

# Ten cot (item_id) DA XAC NHAN tren vnstock 4.0.8 thuc te (Fundamental().
# equity(symbol=...).ratios()) - vd trai vinh xem data/vietcap.py. Cac ten
# du phong o cuoi danh sach giu lai phong khi DNSE sau nay tu cung cap
# ratios (hien DNSE chi la PriceProvider, chua co FundamentalProvider).
_RATIO_COLUMN_MAP: dict[str, list[str]] = {
    "pe": ["pe_ratio", "pe", "P/E", "priceToEarning"],
    "pb": ["pb_ratio", "pb", "P/B", "priceToBook"],
    "eps": ["trailing_eps", "eps", "earningPerShare"],
    "roe": ["roe", "ROE", "roe_percent"],
    "roa": ["roa", "ROA", "roa_percent"],
    "net_margin": ["net_margin", "netProfitMargin", "postTaxMargin"],
    "debt_to_equity": ["debt_to_equity", "debtOnEquity", "de_ratio"],
    "dividend_yield": ["dividend_yield", "dividendYield"],
}
# vnstock (Vietcap, tier Guest) gioi han 20 request/phut. Moi peer ton 4
# request (income/balance/cashflow/ratios qua router.financials()), nen giu
# so peer nho de mot lan /tracuu khong tu vuot gioi han ngay o lan goi dau
# (truoc khi cache 24h phat huy tac dung).
_MAX_PEERS_FOR_MEDIAN = 3


@dataclass
class KeyMetric:
    """Mot chi so tai chinh, kem trung vi nganh de so sanh (neu lay duoc)."""

    value: float | None = None
    industry_median: float | None = None


@dataclass
class CompanyNewsItem:
    """Mot tin tuc / cong bo thong tin kem duong dan doc truc tiep tu bao chi."""

    title: str
    published_at: str | None = None
    url: str | None = None
    cafef_url: str | None = None

    def __str__(self) -> str:
        date_prefix = f"{self.published_at} — " if self.published_at else ""
        return f"{date_prefix}{self.title}"


@dataclass
class CompanyProfile:
    """Ket qua /tracuu: ho so, chi so chinh, cap nhat gan day cho mot ma."""

    symbol: str
    full_name: str | None = None
    exchange: str | None = None
    industry: str | None = None
    listed_date: str | None = None
    charter_capital: float | None = None
    shares_outstanding: float | None = None
    description: str | None = None

    price: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    market_cap: float | None = None
    pe: KeyMetric = field(default_factory=KeyMetric)
    pb: KeyMetric = field(default_factory=KeyMetric)
    eps: KeyMetric = field(default_factory=KeyMetric)
    roe: KeyMetric = field(default_factory=KeyMetric)
    roa: KeyMetric = field(default_factory=KeyMetric)
    net_margin: KeyMetric = field(default_factory=KeyMetric)
    debt_to_equity: KeyMetric = field(default_factory=KeyMetric)
    dividend_yield: KeyMetric = field(default_factory=KeyMetric)

    recent_events: list[str] = field(default_factory=list)
    latest_report_period: str | None = None
    news: list[CompanyNewsItem | str] = field(default_factory=list)
    data_notes: list[str] = field(default_factory=list)  # ghi lai phan nao thieu du lieu


def _extract(row: pd.Series, candidates: list[str]) -> float | None:
    for name in candidates:
        if name in row.index and pd.notna(row[name]):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                continue
    return None


def _industry_column(frame: pd.DataFrame) -> str | None:
    return next((c for c in ("industry", "icb_name3", "icb_name2") if c in frame.columns), None)


def _fill_listing(profile: CompanyProfile, router: DataRouter) -> None:
    try:
        listing = router.listing()
        row = listing.loc[listing["symbol"].astype(str).str.upper() == profile.symbol]
        if not row.empty:
            first = row.iloc[0]
            if pd.notna(first.get("exchange")):
                profile.exchange = str(first["exchange"])
            if pd.notna(first.get("organ_name")):
                profile.full_name = str(first["organ_name"])
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc danh sach niem yet: %s", profile.symbol, exc)
        profile.data_notes.append("Khong lay duoc thong tin niem yet tren san")

    try:
        industry_map = router.industry_map()
        col = _industry_column(industry_map)
        if col:
            row = industry_map.loc[industry_map["symbol"].astype(str).str.upper() == profile.symbol]
            if not row.empty and pd.notna(row.iloc[0][col]):
                profile.industry = str(row.iloc[0][col])
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc nganh: %s", profile.symbol, exc)

    try:
        overview = router.company_overview(profile.symbol)
    except Exception as exc:
        log.warning("lookup(%s): company_overview() loi: %s", profile.symbol, exc)
        overview = {}
    profile.full_name = overview.get("full_name", profile.full_name)
    profile.listed_date = overview.get("listed_date")
    profile.charter_capital = overview.get("charter_capital")
    profile.shares_outstanding = overview.get("shares_outstanding")
    profile.description = overview.get("description")
    if not overview:
        profile.data_notes.append(
            "Chua co nguon xac nhan cho ngay niem yet / von dieu le / mo ta hoat dong"
        )


def _fill_price_snapshot(profile: CompanyProfile, router: DataRouter) -> None:
    try:
        end = date.today()
        frame = router.ohlcv(profile.symbol, end - timedelta(days=15), end)
        if frame.empty:
            profile.data_notes.append("Khong co du lieu gia gan nhat")
            return
        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else last
        profile.price = float(last["close"])
        profile.volume = float(last["volume"])
        if prev["close"]:
            profile.change_pct = profile.price / float(prev["close"]) - 1
        if profile.shares_outstanding and profile.price:
            # Gia OHLCV tu DNSE/Vietcap co the la VND day du (vd 20400) hoac
            # nghin dong/CP (vd 20.40) - kiem tra de quy ve dung VND.
            price_vnd = profile.price if profile.price >= 1000 else profile.price * 1000
            profile.market_cap = price_vnd * profile.shares_outstanding
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc gia: %s", profile.symbol, exc)
        profile.data_notes.append("Khong lay duoc gia gan nhat")


def _fill_ratios(profile: CompanyProfile, router: DataRouter) -> None:
    try:
        financials = router.financials(profile.symbol, period="year")
        ratios = financials.get("ratios")
        if ratios is None or ratios.empty:
            profile.data_notes.append("Khong co du lieu chi so tai chinh (ratios)")
            return
        row = ratios.iloc[-1]
        for key, candidates in _RATIO_COLUMN_MAP.items():
            getattr(profile, key).value = _extract(row, candidates)
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc ratios: %s", profile.symbol, exc)
        profile.data_notes.append("Khong lay duoc chi so tai chinh")


def _fill_industry_median(profile: CompanyProfile, router: DataRouter) -> None:
    """Trung vi nganh, best-effort tren toi da _MAX_PEERS_FOR_MEDIAN ma cung nganh.

    Co the cham neu du lieu cua cac ma cung nganh chua co trong cache (moi
    ma thieu se phai goi mang qua router.financials). Loi tung ma bi nuot rieng
    de mot ma peer hong khong lam mat toan bo phep so sanh.
    """
    if not profile.industry:
        return
    try:
        industry_map = router.industry_map()
        col = _industry_column(industry_map)
        if not col:
            return
        peers = (
            industry_map.loc[industry_map[col] == profile.industry, "symbol"]
            .astype(str).str.upper().unique().tolist()
        )
        peers = [p for p in peers if p != profile.symbol][:_MAX_PEERS_FOR_MEDIAN]
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc danh sach cung nganh: %s", profile.symbol, exc)
        return

    collected: dict[str, list[float]] = {key: [] for key in _RATIO_COLUMN_MAP}
    for peer in peers:
        try:
            ratios = router.financials(peer, period="year").get("ratios")
            if ratios is None or ratios.empty:
                continue
            row = ratios.iloc[-1]
            for key, candidates in _RATIO_COLUMN_MAP.items():
                value = _extract(row, candidates)
                if value is not None:
                    collected[key].append(value)
        except Exception:
            continue

    for key, values in collected.items():
        if values:
            getattr(profile, key).industry_median = float(pd.Series(values).median())


_NEWS_WINDOW_DAYS = 180  # 6 thang gan nhat
_NEWS_MAX_ITEMS = 8


def _build_news_links(
    symbol: str, title: str, raw_url: str | None = None
) -> tuple[str | None, str]:
    """Tao link dan toi bao/tap chi chinh thong (Google Search va CafeF)."""
    if raw_url and raw_url.startswith("http"):
        read_url = raw_url
    else:
        read_url = None

    cafef_url = f"https://s.cafef.vn/tin-doanh-nghiep/{symbol.upper()}/Event.chn"
    return read_url, cafef_url


def _fill_recent_updates(profile: CompanyProfile, router: DataRouter) -> None:
    try:
        income = router.financials(profile.symbol, period="year").get("income")
        if income is not None and not income.empty:
            period_col = next(
                (c for c in ("year", "yearReport", "period") if c in income.columns), None
            )
            if period_col:
                profile.latest_report_period = str(income.iloc[-1][period_col])
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc ky BCTC gan nhat: %s", profile.symbol, exc)

    try:
        items = router.company_news(profile.symbol, days=_NEWS_WINDOW_DAYS)
    except Exception as exc:
        log.warning("lookup(%s): khong lay duoc tin tuc/cong bo: %s", profile.symbol, exc)
        items = []

    if items:
        for item in items[:_NEWS_MAX_ITEMS]:
            published = item.get("published_at")
            date_str = published.strftime("%d/%m/%Y") if pd.notna(published) else "?"
            title = str(item.get("title") or "").strip()
            raw_url = item.get("url") or item.get("news_source_link")
            read_url, cafef_url = _build_news_links(profile.symbol, title, raw_url)
            profile.news.append(
                CompanyNewsItem(
                    title=title,
                    published_at=date_str,
                    url=read_url,
                    cafef_url=cafef_url,
                )
            )
    else:
        profile.data_notes.append(
            f"Không tìm thấy công bố thông tin / tin tức nào trong {_NEWS_WINDOW_DAYS} ngày gần đây"
        )


def lookup(symbol: str) -> CompanyProfile:
    """Tong hop ho so, chi so chinh va cap nhat gan day cho mot ma.

    Khong bao gio raise vi loi tung nguon - moi buoc con tu bat loi rieng va
    ghi vao `data_notes`, de bot luon tra ve duoc mot the thong tin (co the
    thieu mot phan) thay vi sap.
    """
    router = get_router()
    profile = CompanyProfile(symbol=symbol.upper())

    _fill_listing(profile, router)
    _fill_price_snapshot(profile, router)
    _fill_ratios(profile, router)
    _fill_industry_median(profile, router)
    _fill_recent_updates(profile, router)

    return profile
