"""Ho so doanh nghiep, nganh, loai DN (quyet dinh phuong phap dinh gia), tin tuc."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd
import yaml

from ..config import CONFIG_DIR
from ..logging_conf import get_logger
from ..provenance import SourceLog
from . import demo
from .fundamentals import strip_accents

log = get_logger(__name__)


@lru_cache(maxsize=1)
def sector_config() -> dict:
    with open(CONFIG_DIR / "sector_map.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class CompanyInfo:
    symbol: str
    name: str = ""
    exchange: str | None = None
    industry: str | None = None
    company_type: str = "NON_FINANCIAL"
    type_reason: str = ""
    shares_outstanding: float | None = None
    listed_date: str | None = None
    description: str | None = None
    peers: list[str] = field(default_factory=list)
    is_demo: bool = False

    @property
    def type_label(self) -> str:
        return sector_config()["company_types"][self.company_type]["label"]


def classify(symbol: str, industry: str | None) -> tuple[str, str]:
    """(loai DN, ly do). Uu tien nganh ICB tu nguon, sau do danh sach tham chieu."""
    cfg = sector_config()
    if industry:
        norm = strip_accents(industry)
        for kind, spec in cfg["company_types"].items():
            for kw in spec.get("icb_keywords", []):
                if strip_accents(kw) in norm:
                    return kind, f"ngành ICB '{industry}'"
    for kind, tickers in cfg.get("static_types", {}).items():
        if symbol.upper() in tickers:
            return kind, "danh sách mã tham chiếu (config/sector_map.yaml)"
    return "NON_FINANCIAL", "mặc định (không thuộc nhóm tài chính/BĐS)"


def load_company(symbol: str, log_: SourceLog | None = None) -> CompanyInfo:
    symbol = symbol.upper()
    if demo.is_demo(symbol):
        ov = demo.overview(symbol)
        info = CompanyInfo(symbol, ov["full_name"], ov["exchange"], ov["industry"],
                           ov["company_type"], "dữ liệu mẫu", ov["shares_outstanding"],
                           ov["listed_date"], ov["description"], demo.peers(symbol), True)
        if log_:
            log_.add(f"Hồ sơ {symbol}", "DỮ LIỆU MẪU (giả lập)")
        return info

    from .prices import get_exchange
    from .router import get_router

    router = get_router()
    info = CompanyInfo(symbol)
    info.exchange = get_exchange(symbol)

    try:
        listing = router.listing()
        hit = listing[listing["symbol"].astype(str).str.upper() == symbol]
        if not hit.empty:
            info.name = str(hit.iloc[0].get("organ_name") or hit.iloc[0].get("name") or "")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.info("listing loi: %s", exc)

    industry_map = pd.DataFrame()
    try:
        industry_map = router.industry_map()
        hit = industry_map[industry_map["symbol"].astype(str).str.upper() == symbol]
        if not hit.empty:
            info.industry = str(hit.iloc[0]["industry"])
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.info("industry_map loi: %s", exc)

    try:
        ov = router.company_overview(symbol)
        info.shares_outstanding = ov.get("shares_outstanding")
        info.listed_date = ov.get("listed_date")
        info.description = ov.get("description")
        if ov and log_:
            log_.add(f"Hồ sơ {symbol}", "vnstock (Vietcap/VCI) – company.info()")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.info("company_overview loi: %s", exc)

    info.company_type, info.type_reason = classify(symbol, info.industry)
    info.peers = find_peers(symbol, info, industry_map)
    if log_ and info.industry:
        log_.add(f"Ngành ICB {symbol}", "vnstock (Vietcap/VCI) – list_by_industry()",
                 note=info.industry)
    return info


def find_peers(symbol: str, info: CompanyInfo, industry_map: pd.DataFrame,
               limit: int = 6) -> list[str]:
    """Ma cung nganh, xep theo thanh khoan (gia tri GD TB 20 phien tu kho gia local)."""
    candidates: list[str] = []
    if info.industry and not industry_map.empty:
        same = industry_map[industry_map["industry"] == info.industry]["symbol"].astype(str)
        candidates = [s.upper() for s in same if s.upper() != symbol]
    if not candidates:
        static = sector_config().get("static_types", {}).get(info.company_type, [])
        candidates = [s for s in static if s != symbol]
    try:
        from . import market_store

        store = market_store.load_ohlcv(candidates)
        if not store.empty:
            tail = store.sort_values("time").groupby("symbol").tail(20)
            liq = (tail["close"] * tail["volume"]).groupby(tail["symbol"]).mean()
            ranked = liq.sort_values(ascending=False).index.tolist()
            candidates = ranked + [c for c in candidates if c not in ranked]
    except Exception:  # noqa: BLE001
        pass
    return candidates[:limit]


def load_news(info: CompanyInfo, days: int = 180, log_: SourceLog | None = None) -> list[dict]:
    """Cong bo thong tin chinh thuc (vnstock/VCI) + tin bao chi RSS co nhac den ma/ten DN."""
    if info.is_demo:
        if log_:
            log_.add(f"Tin tức {info.symbol}", "DỮ LIỆU MẪU (giả lập)")
        return demo.news(info.symbol)
    items: list[dict] = []
    try:
        from .router import get_router

        for row in get_router().company_news(info.symbol, days):
            items.append({"title": row["title"], "published_at": row["published_at"],
                          "source": "Công bố thông tin (Vietcap/VCI)", "link": ""})
        if items and log_:
            log_.add(f"Công bố thông tin {info.symbol}", "vnstock (VCI) – company.news()",
                     items[0]["published_at"], note=f"{len(items)} tin")
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.info("company_news loi: %s", exc)
    try:
        short = strip_accents(info.name.split("Công ty")[-1]) if info.name else ""
        rss = 0
        for it in macro_headlines():
            text = f" {it.title} {it.summary} "
            if f" {info.symbol} " in text or f"({info.symbol})" in text or (
                    short and len(short) > 6 and short in strip_accents(text)):
                items.append({"title": it.title, "published_at": it.published_at,
                              "source": it.source, "link": it.link})
                rss += 1
        if rss and log_:
            log_.add(f"Tin báo chí {info.symbol}", "RSS CafeF / VnExpress", note=f"{rss} tin")
    except Exception as exc:  # noqa: BLE001
        log.info("RSS loi: %s", exc)
    items.sort(key=lambda x: pd.Timestamp(x["published_at"]).tz_localize(None)
               if pd.Timestamp(x["published_at"]).tzinfo else pd.Timestamp(x["published_at"]),
               reverse=True)
    return items[:25]


_HEADLINES: list | None = None


def macro_headlines() -> list:
    """Tin vi mo/thi truong tu RSS (tai mot lan moi tien trinh)."""
    global _HEADLINES
    if _HEADLINES is None:
        try:
            from .macro_news import fetch_all_macro_news

            _HEADLINES = fetch_all_macro_news()
        except Exception as exc:  # noqa: BLE001
            log.info("RSS loi: %s", exc)
            _HEADLINES = []
    return _HEADLINES
