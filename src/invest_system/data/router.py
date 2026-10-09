"""Dieu phoi nguon du lieu: uu tien, du phong, cache, lui khi loi.

Day la diem duy nhat trong he thong biet ten cac nguon. Phan con lai chi goi
get_router().ohlcv(...) va khong quan tam du lieu den tu dau.

Moi loi tu mot nguon deu duoc bat bang `except (Exception, SystemExit)`,
KHONG chi `except Exception`: vnstock (qua vnai) da duoc quan sat thuc te
la goi thang sys.exit() khi cham gioi han rate limit thay vi nem mot
exception binh thuong - SystemExit ke thua tu BaseException nen "except
Exception" khong bat duoc, va se giet chet ca tien trinh bot (xuyen qua ca
middleware ErrorGuard). data/vietcap.py da chan truong hop nay tan goc, day
la lop phong thu thu hai o diem trung tam, phong khi mot nguon khac sau nay
cung lam vay.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from ..config import get_settings, now_local
from ..logging_conf import get_logger
from . import cache, market_store
from .base import FundamentalProvider, PriceProvider, ProviderError
from .cleaner import clean_ohlcv

log = get_logger(__name__)

# Phien dau cua cache duoc phep tre hon ngay bat dau duoc hoi toi da bay nhieu
# ngay (cuoi tuan, nghi Tet ~9 ngay) ma van coi la "du khoang".
_CACHE_START_SLACK_DAYS = 10


def _build(name: str):
    if name == "dnse":
        from .dnse import DnseProvider

        return DnseProvider()
    if name == "vietcap":
        from .vietcap import VietcapProvider

        return VietcapProvider()
    raise ValueError(f"Nguon du lieu khong ro: {name}")


class DataRouter:
    """Thu tung nguon theo thu tu uu tien, nga ve cache khi tat ca deu that bai."""

    def __init__(self) -> None:
        settings = get_settings()
        self._price_names: list[str] = settings.get("data.price_sources", ["dnse"])
        self._fund_names: list[str] = settings.get("data.fundamental_sources", ["vietcap"])
        self._ttl_daily: int = settings.get("data.cache_ttl_seconds.daily", 43200)
        self._ttl_fund: int = settings.get("data.cache_ttl_seconds.fundamental", 86400)
        self._instances: dict[str, object] = {}

    def _get(self, name: str):
        if name not in self._instances:
            self._instances[name] = _build(name)
        return self._instances[name]

    # ------------------------------------------------------------------- gia
    def ohlcv(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        resolution: str = "1D",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        end = end or date.today()
        start = start or (end - timedelta(days=365 * 3))
        key = f"ohlcv/{symbol.upper()}/{resolution}"

        # Kho toan san (data/market_store.py) la nguon UU TIEN NHAT: doc mot
        # file tren dia, khong goi mang. Chi ap dung cho nen "1D" (kho chi
        # chua du lieu ngay) va khi khong ep lam moi. Xem scripts/backfill_data.py.
        if not force_refresh and resolution == "1D":
            stored = market_store.load_ohlcv([symbol])
            if not stored.empty:
                last_stored_date = pd.to_datetime(stored.iloc[-1]["time"]).date()
                now_dt = now_local()  # gio VN, khong phai gio may chu (Render chay UTC)
                is_weekday = now_dt.weekday() < 5
                is_after_close = (now_dt.hour > 15) or (now_dt.hour == 15 and now_dt.minute >= 15)
                today = now_dt.date()
                is_stale = (
                    is_weekday and is_after_close and (end >= today) and (last_stored_date < today)
                )
                if not is_stale:
                    return _slice(stored, start, end)

        if not force_refresh:
            cached = cache.read_frame(key, max_age=self._ttl_daily)
            if cached is not None and not cached.empty:
                last_cached_date = pd.to_datetime(cached.iloc[-1]["time"]).date()
                now_dt = now_local()
                is_weekday = now_dt.weekday() < 5
                is_after_close = (now_dt.hour > 15) or (now_dt.hour == 15 and now_dt.minute >= 15)
                today = now_dt.date()
                is_stale = (
                    is_weekday and is_after_close and (end >= today) and (last_cached_date < today)
                )
                # Cache chi chua khoang da hoi LAN TRUOC: hoi 3 thang roi hoi 6
                # thang thi cache khong du - phai tai lai (ban cu tra ve ban 3
                # thang, backtest 6 thang lay nham loi nhuan VN-Index 3 thang).
                first_cached_date = pd.to_datetime(cached.iloc[0]["time"]).date()
                covers_start = first_cached_date <= start + timedelta(days=_CACHE_START_SLACK_DAYS)
                if not is_stale and covers_start:
                    return _slice(cached, start, end)

        errors: list[str] = []
        for name in self._price_names:
            try:
                provider: PriceProvider = self._get(name)  # type: ignore[assignment]
                raw = provider.ohlcv(symbol, start, end, resolution)
                frame = clean_ohlcv(raw, symbol)
                if frame.empty:
                    raise ProviderError("khung du lieu rong sau khi lam sach")
                cache.write_frame(key, frame)
                log.info("%s: lay %d phien tu nguon %s", symbol, len(frame), name)
                return _slice(frame, start, end)
            except (Exception, SystemExit) as exc:
                errors.append(f"{name}: {exc}")
                log.warning("Nguon %s that bai cho %s -> %s", name, symbol, exc)

        stale = cache.read_frame(key)
        if stale is not None and not stale.empty:
            age = cache.age_seconds(key)
            log.warning(
                "Tat ca nguon that bai cho %s, dung cache cu (%.0f phut truoc)",
                symbol, (age or 0) / 60,
            )
            return _slice(stale, start, end)

        raise ProviderError(f"Khong lay duoc du lieu {symbol}. Chi tiet: {'; '.join(errors)}")

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        key = "listing/all"
        cached = cache.read_frame(key, max_age=self._ttl_fund)
        if cached is not None and not cached.empty:
            return cached

        for name in self._price_names + self._fund_names:
            try:
                frame = self._get(name).listing(exchanges)  # type: ignore[attr-defined]
                if not frame.empty:
                    cache.write_frame(key, frame)
                    return frame
            except (Exception, SystemExit) as exc:
                log.warning("listing() that bai o nguon %s: %s", name, exc)

        stale = cache.read_frame(key)
        if stale is not None:
            return stale
        raise ProviderError("Khong lay duoc danh sach ma tu bat ky nguon nao")

    def foreign_flow(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        for name in self._price_names:
            try:
                frame = self._get(name).foreign_flow(symbol, start, end)  # type: ignore
                if frame is not None and not frame.empty:
                    return frame
            except (Exception, SystemExit) as exc:
                log.debug("foreign_flow khong co o nguon %s: %s", name, exc)
        return pd.DataFrame(columns=["time", "foreign_buy_volume", "foreign_sell_volume"])

    # ----------------------------------------------------------- bao cao tai chinh
    def financials(self, symbol: str, period: str = "quarter") -> dict[str, pd.DataFrame]:
        """Tra ve dict gom income, balance, cashflow, ratios."""
        key = f"fin/{symbol.upper()}/{period}"
        cached = cache.read_frame(key + "/income", max_age=self._ttl_fund)
        if cached is not None:
            result = {}
            for part in ("income", "balance", "cashflow", "ratios"):
                frame = cache.read_frame(f"{key}/{part}")
                # LUU Y: "frame or pd.DataFrame()" se loi ("truth value cua
                # DataFrame la ambiguous") vi DataFrame khong ho tro bool() -
                # phai kiem tra "is None" tuong minh.
                result[part] = frame if frame is not None else pd.DataFrame()
            return _align_years(result, period)

        for name in self._fund_names:
            try:
                provider: FundamentalProvider = self._get(name)  # type: ignore[assignment]
                bundle = {
                    "income": provider.income_statement(symbol, period),
                    "balance": provider.balance_sheet(symbol, period),
                    "cashflow": provider.cash_flow(symbol, period),
                    "ratios": provider.ratios(symbol, period),
                }
                for part, frame in bundle.items():
                    cache.write_frame(f"{key}/{part}", frame)
                return _align_years(bundle, period)
            except (Exception, SystemExit) as exc:
                log.warning("financials() that bai o nguon %s cho %s: %s", name, symbol, exc)

        return {p: pd.DataFrame() for p in ("income", "balance", "cashflow", "ratios")}

    def ratios(self, symbol: str, period: str = "year") -> pd.DataFrame:
        """Chi rieng bang chi so tai chinh (P/E, P/B, ROE...) - nhe hon
        financials() vi khong keo them income/balance/cashflow. Dung cho
        scripts/backfill_fundamentals.py (quet ca vu tru thanh khoan)."""
        key = f"ratios/{symbol.upper()}/{period}"
        cached = cache.read_frame(key, max_age=self._ttl_fund)
        if cached is not None:
            return cached
        for name in self._fund_names:
            try:
                frame = self._get(name).ratios(symbol, period)  # type: ignore[attr-defined]
                if not frame.empty:
                    cache.write_frame(key, frame)
                    return frame
            except (Exception, SystemExit) as exc:
                log.warning("ratios() that bai o nguon %s cho %s: %s", name, symbol, exc)
        return pd.DataFrame()

    def industry_map(self) -> pd.DataFrame:
        key = "industry/map"
        cached = cache.read_frame(key, max_age=self._ttl_fund)
        if cached is not None:
            return cached
        for name in self._fund_names:
            try:
                frame = self._get(name).industry_map()  # type: ignore[attr-defined]
                if not frame.empty:
                    cache.write_frame(key, frame)
                    return frame
            except (Exception, SystemExit) as exc:
                log.warning("industry_map() that bai o nguon %s: %s", name, exc)
        return pd.DataFrame(columns=["symbol", "industry"])

    def company_overview(self, symbol: str) -> dict:
        """Ho so doanh nghiep (ten, ngay niem yet, von dieu le...). Xem
        FundamentalProvider.company_overview trong data/base.py.
        """
        for name in self._fund_names:
            try:
                overview = self._get(name).company_overview(symbol)  # type: ignore[attr-defined]
                if overview:
                    return overview
            except (Exception, SystemExit) as exc:
                log.warning("company_overview() that bai o nguon %s cho %s: %s", name, symbol, exc)
        return {}

    def company_news(self, symbol: str, days: int = 180) -> list[dict]:
        """Cong bo thong tin / tin tuc gan day. Xem
        FundamentalProvider.company_news trong data/base.py.
        """
        for name in self._fund_names:
            try:
                news = self._get(name).company_news(symbol, days)  # type: ignore[attr-defined]
                if news:
                    return news
            except (Exception, SystemExit) as exc:
                log.warning("company_news() that bai o nguon %s cho %s: %s", name, symbol, exc)
        return []


def _align_years(bundle: dict[str, pd.DataFrame], period: str) -> dict[str, pd.DataFrame]:
    """Bao cao nam cua vnstock co the bi dao thu tu nam - xem
    data/vietcap.py:align_statement_years(). Ap dung ca khi doc tu cache (du
    lieu cu luu truoc khi sua) - ham idempotent nen goi nhieu lan van dung."""
    if period != "year":
        return bundle
    from .vietcap import align_statement_years

    try:
        return align_statement_years(bundle)
    except Exception as exc:  # noqa: BLE001 - khong duoc lam hong /fin, /info
        log.warning("Khong kiem tra duoc thu tu nam cua BCTC: %s", exc)
        return bundle


def _slice(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
    mask = (frame["time"] >= pd.Timestamp(start)) & (frame["time"] < end_ts)
    return frame.loc[mask].reset_index(drop=True)


@lru_cache(maxsize=1)
def get_router() -> DataRouter:
    return DataRouter()
