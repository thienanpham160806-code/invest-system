"""Dich vu cho web API: doc universe + BCTC arminer + gia, chay lai cac module phan tich san co.

Nguyen tac: moi khoi du lieu tra ve kem `provenance` = {source, as_of, fetched_at};
thieu so -> None + ly do (khong bia, khong dung du lieu demo cho ma that).
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..analysis import composite as comp
from ..analysis import sector as sector_mod
from ..analysis.macro import analyze_macro
from ..analysis.ratios import BANK_KEYS, NONFIN_KEYS, RATIO_LABELS, compute_ratios, growth_summary
from ..analysis.sentiment import analyze_news
from ..analysis.valuation import value_company
from ..config import get_settings
from ..data import arminer_bctc
from ..data.fundamentals import FIELD_LABELS_VI, StandardFinancials, _fill_derived
from ..data.macro import INDICATORS, load_macro

try:  # nhan dinh vi mo bang LLM (tuy chon); ban llm.py chua co ham nay -> dung nhan dinh theo quy tac
    from ..narrative.llm import analyze_macro as analyze_macro_narrative
except ImportError:
    def analyze_macro_narrative(ctx: dict) -> list[str]:
        return list(ctx["macro"].commentary)
from ..validation import checks
from .universe import (
    COMPANY_TYPE_LABELS,
    UNCLASSIFIED,
    load_ohlcv_snapshot,
    load_sector_index,
    load_universe,
    load_vnindex_snapshot,
    node_key,
    zenodo_index,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ZENODO_RECORD = "https://zenodo.org/records/20949551"
CAFEF_CDN = "https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{name}"


class NotFound(Exception):
    pass


def now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M")


def prov(source: str, as_of=None, note: str | None = None, **extra) -> dict:
    out = {"source": source, "as_of": _iso(as_of), "fetched_at": now_str()}
    if note:
        out["note"] = note
    out.update(extra)
    return out


def _iso(v):
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v)


def jsonable(obj):
    """Chuyen ve kieu JSON: NaN/inf -> None, numpy -> python, Timestamp -> chuoi."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return [jsonable(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if dataclasses.is_dataclass(obj):
        return jsonable(dataclasses.asdict(obj))
    if obj is pd.NA or obj is pd.NaT:
        return None
    return str(obj)


# ------------------------------------------------------------------ universe
UNIVERSE_COLS = [
    "symbol", "name", "exchange", "icb1", "icb2", "icb3", "icb4", "industry_source", "company_type",
    "price", "change_1d", "ret_1m", "ret_3m", "ret_ytd", "ret_1y", "avg_value_20d", "shares",
    "shares_source", "market_cap", "pe", "pb", "ev_ebitda", "roe", "net_margin", "ni_growth",
    "debt_to_equity", "eps", "fin_year", "liquidity_flag", "has_bctc", "as_of_price", "as_of_fin",
    "pe_ttm", "ttm_label", "net_income_parent", "equity_parent", "ni_ttm", "eps_ttm",
]


def universe_prov(meta: dict) -> dict:
    src = meta.get("sources", {})
    return prov("Bảng toàn thị trường: " + "; ".join(f"{k}: {v}" for k, v in src.items()),
                meta.get("as_of_price"), origin=meta.get("origin"), built_at=meta.get("built_at"),
                as_of_fin=meta.get("as_of_fin_max"))


@lru_cache(maxsize=1)
def _uni() -> tuple[pd.DataFrame, dict]:
    uni, meta = load_universe()
    return uni, meta


def search(q: str, limit: int = 2000, exchange: str = "ALL") -> dict:
    uni, meta = _uni()
    q = (q or "").strip()
    if not q:
        return {"items": [], "provenance": universe_prov(meta)}
    if exchange.strip().upper() not in {"ALL", "HOSE", "HNX", "UPCOM"}:
        raise ValueError("exchange phải là ALL, HOSE, HNX hoặc UPCOM")
    from .symbol_search import rank_symbol_rows

    hits = rank_symbol_rows(uni, q, exchange).head(max(1, min(limit, 2000)))
    cols = [c for c in ["symbol", "name", "brand", "exchange", "icb2", "icb4", "price", "market_cap"] if c in hits.columns]
    return {"items": jsonable(hits[cols]), "provenance": universe_prov(meta)}


def symbols(exchange: str = "ALL") -> dict:
    """Small symbol directory for the client-side exchange/name picker."""
    uni, meta = _uni()
    exchange = exchange.strip().upper()
    if exchange not in {"ALL", "HOSE", "HNX", "UPCOM"}:
        raise ValueError("exchange phải là ALL, HOSE, HNX hoặc UPCOM")
    rows = uni if exchange == "ALL" else uni[uni["exchange"] == exchange]
    cols = [c for c in ("symbol", "name", "brand", "exchange", "icb1", "has_bctc", "market_cap") if c in rows.columns]
    return {"items": jsonable(rows[cols].sort_values("symbol")),
            "counts": uni["exchange"].value_counts().to_dict(), "provenance": universe_prov(meta)}


def universe_table(exchange: str | None = None, icb: str | None = None, sort: str = "market_cap",
                   order: str = "desc", min_value: float | None = None, page: int = 1,
                   page_size: int = 50, q: str | None = None) -> dict:
    uni, meta = _uni()
    f = uni
    if exchange:
        f = f[f["exchange"].isin([e.strip().upper() for e in exchange.split(",")])]
    if icb:
        m = re.match(r"^([1-4])-(.+)$", icb)
        if m:
            lvl = int(m.group(1))
            f = f[f[f"icb{lvl}"].map(lambda n: node_key(lvl, n)) == icb]
    if min_value:
        f = f[f["avg_value_20d"].fillna(0) >= min_value]
    if q:
        f = f[f["symbol"].str.contains(q.upper()) | f["name"].fillna("").str.lower().str.contains(q.lower())]
    if sort in f.columns:
        f = f.sort_values(sort, ascending=(order == "asc"), na_position="last")
    total = len(f)
    page_size = max(1, min(page_size, 2000))
    page = max(1, page)
    rows = f.iloc[(page - 1) * page_size: page * page_size]
    return {"total": total, "page": page, "page_size": page_size,
            "items": jsonable(rows[[c for c in UNIVERSE_COLS if c in rows.columns]]),
            "provenance": universe_prov(meta)}


def opportunities(exchange: str | None = None, min_value: float | None = None,
                  eligible_only: bool = True, limit: int = 100, q: str | None = None,
                  industry: str | None = None, rating: str | None = None,
                  confidence: str | None = None, min_upside: float | None = None,
                  min_market_cap: float | None = None) -> dict:
    """Read the last precomputed, auditable full-universe opportunity ranking."""
    path = Path(__file__).resolve().parents[3] / "webdata" / "snapshot" / "opportunities.json"
    if not path.exists():
        return {"items": [], "total": 0, "ready": False,
                "note": "Chưa có snapshot xếp hạng. Chạy scripts/build_opportunities.py --resume.",
                "provenance": prov("Chưa tạo snapshot")}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("items", [])
    if eligible_only:
        rows = [r for r in rows if r.get("eligible")]
    if exchange:
        exchanges = {x.strip().upper() for x in exchange.split(",")}
        rows = [r for r in rows if str(r.get("exchange", "")).upper() in exchanges]
    if min_value is not None:
        rows = [r for r in rows if (r.get("avg_value_20d") or 0) >= min_value]
    if q:
        term = q.casefold()
        rows = [r for r in rows if term in str(r.get("symbol", "")).casefold()
                or term in str(r.get("name", "")).casefold()]
    if industry:
        rows = [r for r in rows if industry.casefold() in str(r.get("industry", "")).casefold()]
    if rating:
        rows = [r for r in rows if str(r.get("rating", "")).upper() == rating.upper()]
    if confidence:
        rows = [r for r in rows if str(r.get("confidence", "")).upper() == confidence.upper()]
    if min_upside is not None:
        rows = [r for r in rows if isinstance(r.get("upside"), (int, float))
                and r["upside"] >= min_upside]
    if min_market_cap is not None:
        rows = [r for r in rows if (r.get("market_cap") or 0) >= min_market_cap]
    rows.sort(key=lambda r: (r.get("score") or -1, r.get("upside") or -10,
                             r.get("avg_value_20d") or 0), reverse=True)
    total = len(rows)
    rows = [dict(row, rank=index + 1) for index, row in enumerate(rows)]
    return {"items": rows[:max(1, min(limit, 2000))], "total": total, "ready": True,
            "universe_count": data.get("universe_count"), "analyzed_count": data.get("analyzed_count"),
            "generated_at": data.get("generated_at"), "errors": data.get("errors", 0),
            "upside_distribution": data.get("upside_distribution", {}),
            "outlier_upside_count": data.get("outlier_upside_count"),
            "provenance": prov("Snapshot định giá theo pipeline cổ phiếu", data.get("generated_at"),
                                note="Định giá theo dữ liệu snapshot; kiểm tra độ tin cậy và ngày dữ liệu trước khi dùng.")}


def market_map(period: str = "ret_1m") -> dict:
    """Full ICB1→ICB4→ticker hierarchy with market-cap area and return color."""
    allowed = {"change_1d", "ret_1m", "ret_3m", "ret_ytd", "ret_1y"}
    if period not in allowed:
        raise ValueError(f"period phải thuộc {', '.join(sorted(allowed))}")
    uni, meta = _uni()
    rows = uni.copy()

    def make_node(group: pd.DataFrame, level: int) -> list[dict]:
        if level > 4:
            return [{"name": str(r.symbol), "slug": f"ticker-{r.symbol}", "symbol": str(r.symbol),
                     "size": float(r.market_cap) if pd.notna(r.market_cap) else 0.0,
                     "value": getattr(r, period, None), "children": []}
                    for r in group.itertuples(index=False)]
        col = f"icb{level}"
        out = []
        for name, members in group.groupby(col, dropna=False, sort=True):
            label = str(name) if pd.notna(name) else "Chưa phân loại"
            children = make_node(members, level + 1)
            out.append({"name": label, "slug": node_key(level, label), "size": float(members["market_cap"].fillna(0).sum()),
                        "value": float(members[period].median()) if members[period].notna().any() else None,
                        "count": int(len(members)), "children": children})
        return out

    return jsonable({"period": period, "items": make_node(rows, 1), "ticker_count": int(rows["symbol"].nunique()),
                     "market_cap_available": int(rows["market_cap"].notna().sum()),
                     "provenance": universe_prov(meta)})


# ------------------------------------------------------------------ thi truong
_VNI_CACHE: dict = {}
_LIVE_CACHE: dict[str, tuple[float, dict]] = {}


def _vnindex_live(days: int = 400) -> tuple[pd.DataFrame, dict]:
    hit = _VNI_CACHE.get("v")
    if hit and time.time() - hit[0] < 300 and len(hit[1]) >= min(days, len(hit[1])):
        return hit[1].tail(days), hit[2]
    out = _vnindex_fetch(max(days, 800))
    _VNI_CACHE["v"] = (time.time(), out[0], out[1])
    return out[0].tail(days), out[1]


def _vnindex_fetch(days: int) -> tuple[pd.DataFrame, dict]:
    frame = _gap_chart("VNINDEX", days)
    if frame is not None and not frame.empty:
        return frame, prov("Vietcap public API gap-chart (live)", frame["time"].iloc[-1])
    snap = load_vnindex_snapshot()
    if not snap.empty:
        return snap, prov("Vietcap gap-chart – bản chụp khi dựng universe", snap["time"].iloc[-1],
                          note="Không gọi được nguồn live từ máy chủ; dùng bản chụp")
    return pd.DataFrame(), prov("—", note="Không có dữ liệu VN-Index")


def _gap_chart(symbol: str, count_back: int) -> pd.DataFrame | None:
    """Goi gap-chart DUNG MOT LAN, timeout ngan (khong treo request web)."""
    try:
        from ..data.vietcap import probe_endpoint

        payload = {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": int(time.time()),
                   "countBack": count_back}
        status, data, _err = probe_endpoint("POST", "/chart/OHLCChart/gap-chart", payload, timeout=6)
        if status != 200 or not data:
            return None
        item = (data if isinstance(data, list) else data.get("data", []))[0]
        if not item or "t" not in item:
            return None
        response_symbol = str(item.get("symbol") or "").upper()
        if response_symbol != symbol.upper():
            return None
        frame = pd.DataFrame({
            "time": pd.to_datetime(pd.Series(item["t"], dtype="int64"), unit="s"),
            "open": item.get("o"), "high": item.get("h"), "low": item.get("l"),
            "close": item.get("c"), "volume": item.get("v"),
            "accumulated_volume": item.get("accumulatedVolume"),
            "accumulated_value": item.get("accumulatedValue"),
        })
        frame["time"] = frame["time"].dt.tz_localize("UTC").dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize()
        return frame.dropna(subset=["close"]).sort_values("time").reset_index(drop=True)
    except Exception:  # noqa: BLE001
        return None


def market() -> dict:
    uni, meta = _uni()
    vni, vprov = _vnindex_live(300)
    vn = {}
    if not vni.empty:
        c = vni["close"].astype(float)
        def r(n):
            return float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else None
        ystart = vni[vni["time"] < pd.Timestamp(datetime.now().year, 1, 1)]["close"]
        vn = {"close": float(c.iloc[-1]), "change_1d": r(1), "ret_1m": r(21), "ret_3m": r(63),
              "ret_1y": r(250) if len(c) > 250 else None,
              "ret_ytd": float(c.iloc[-1] / ystart.iloc[-1] - 1) if len(ystart) else None,
              "as_of": _iso(vni["time"].iloc[-1]),
              "series": [{"time": _iso(t), "close": float(v)}
                         for t, v in zip(vni["time"], c, strict=True)][-260:]}
    adv = int((uni["change_1d"] > 0).sum())
    dec = int((uni["change_1d"] < 0).sum())
    stats = {
        "n_symbols": int(len(uni)), "by_exchange": uni["exchange"].value_counts().to_dict(),
        "market_cap": float(uni["market_cap"].sum()), "advancers": adv, "decliners": dec,
        "unchanged": int(len(uni) - adv - dec),
        "n_with_bctc": int(uni["has_bctc"].sum()), "n_liquid": int(uni["liquidity_flag"].sum()),
        "n_unclassified": int((uni["icb1"] == UNCLASSIFIED).sum()),
        "industry_coverage": float((uni["icb1"] != UNCLASSIFIED).mean()),
        "industry_source": uni["industry_source"].value_counts().to_dict(),
        "pe_aggregate": _agg_pe(uni),
        "top_gainers": jsonable(uni[uni["liquidity_flag"]].nlargest(5, "change_1d")[["symbol", "price", "change_1d"]]),
        "top_losers": jsonable(uni[uni["liquidity_flag"]].nsmallest(5, "change_1d")[["symbol", "price", "change_1d"]]),
    }
    return jsonable({"vnindex": vn, "vnindex_provenance": vprov, "stats": stats,
                     "checks": meta.get("checks"), "provenance": universe_prov(meta)})


def _market_session(now: datetime | None = None) -> str:
    now = now or datetime.now(TZ)
    if now.weekday() >= 5:
        return "Ngày nghỉ"
    t = now.time()
    if t < datetime.strptime("09:00", "%H:%M").time():
        return "Chưa mở cửa"
    if t < datetime.strptime("09:15", "%H:%M").time():
        return "ATO"
    if t < datetime.strptime("11:30", "%H:%M").time():
        return "Liên tục"
    if t < datetime.strptime("13:00", "%H:%M").time():
        return "Nghỉ trưa"
    if t < datetime.strptime("14:30", "%H:%M").time():
        return "Liên tục"
    if t < datetime.strptime("14:45", "%H:%M").time():
        return "ATC"
    return "Đóng cửa"


def _live_quote(symbol: str, is_index: bool = False) -> dict:
    sym = symbol.upper()
    cached = _LIVE_CACHE.get(sym)
    if cached and time.time() - cached[0] < 10:
        return cached[1]
    try:
        if not is_index:
            from ..data.vietcap import fetch_price_board

            board = fetch_price_board([sym], delay=0)
            if not board.empty:
                row = board.iloc[0]
                current = pd.to_numeric(row.get("matchPrice.matchPrice"), errors="coerce")
                reference = pd.to_numeric(row.get("matchPrice.referencePrice"), errors="coerce")
                if pd.notna(current) and current > 0:
                    volume = pd.to_numeric(row.get("matchPrice.accumulatedVolume"), errors="coerce")
                    value_million = pd.to_numeric(row.get("matchPrice.accumulatedValue"), errors="coerce")
                    quote = {"symbol": sym, "price": float(current),
                             "change": float(current - reference) if pd.notna(reference) and reference else None,
                             "change_pct": float(current / reference - 1) if pd.notna(reference) and reference else None,
                             "volume": float(volume) if pd.notna(volume) else None,
                             "turnover": float(value_million * 1e6) if pd.notna(value_million) else None,
                             "as_of": _iso(row.get("matchPrice.time")), "stale": False,
                             "source": "Vietcap price board live"}
                    _LIVE_CACHE[sym] = (time.time(), quote)
                    return quote
        from ..data.vietcap import fetch_daily_bars
        frame = fetch_daily_bars(sym, count_back=3)
        frame = frame.dropna(subset=["close"]).sort_values("time") if not frame.empty else frame
        if frame.empty:
            raise RuntimeError("Nguồn live chưa trả nến")
        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else None
        close = float(last["close"])
        previous = float(prev["close"]) if prev is not None else None
        volume = float(last["volume"]) if pd.notna(last.get("volume")) else None
        row = {"symbol": sym, "price": close, "change": close - previous if previous else None,
               "change_pct": close / previous - 1 if previous else None, "volume": volume,
               "turnover": close * volume if volume is not None and not is_index else None,
               "as_of": _iso(last["time"]), "stale": False, "source": "Vietcap gap-chart (nến live)"}
        _LIVE_CACHE[sym] = (time.time(), row)
        return row
    except Exception as exc:  # noqa: BLE001
        if cached:
            return {**cached[1], "stale": True, "error": str(exc)}
        try:
            from ..web.universe import load_ohlcv_snapshot, load_vnindex_snapshot
            fallback = load_vnindex_snapshot() if sym == "VNINDEX" else load_ohlcv_snapshot(sym)
            if not fallback.empty:
                fallback = fallback.dropna(subset=["close"]).sort_values("time")
                last = fallback.iloc[-1]
                prev = fallback.iloc[-2] if len(fallback) > 1 else None
                close = float(last["close"])
                previous = float(prev["close"]) if prev is not None else None
                volume = float(last["volume"]) if pd.notna(last.get("volume")) else None
                return {"symbol": sym, "price": close, "change": close - previous if previous else None,
                        "change_pct": close / previous - 1 if previous else None, "volume": volume,
                        "turnover": close * volume if volume is not None and not is_index else None,
                        "as_of": _iso(last["time"]), "stale": True,
                        "source": "Bản chụp đóng gói", "error": str(exc)}
        except Exception:  # noqa: BLE001
            pass
        return {"symbol": sym, "price": None, "change": None, "change_pct": None,
                "volume": None, "turnover": None, "as_of": None, "stale": True,
                "source": "Vietcap gap-chart", "error": str(exc)}


def market_live() -> dict:
    session = _market_session()
    indices = (("VNINDEX", "VN-Index"), ("HNXIndex", "HNX-Index"), ("HNXUpcomIndex", "UPCOM-Index"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        quotes = list(pool.map(lambda pair: _index_live_quote(pair[0]), indices))
    rows, unavailable = [], []
    vn_price = next((q.get("price") for (s, _), q in zip(indices, quotes, strict=True) if s == "VNINDEX"), None)
    for (symbol, label), quote in zip(indices, quotes, strict=True):
        duplicate = symbol != "VNINDEX" and quote.get("price") is not None and quote.get("price") == vn_price
        if quote.get("price") is not None and not duplicate:
            rows.append({"name": label, **quote})
        elif symbol != "VNINDEX":
            unavailable.append({"name": label, "reason": "chưa lấy được" if not duplicate else
                                "nguồn trả cùng giá trị với VN-Index; đã ẩn để tránh nhầm dữ liệu"})
    return {"session": session, "is_open": session in {"ATO", "Liên tục", "ATC"},
            "updated_at": now_str(), "indices": rows, "unavailable_indices": unavailable}


def _index_live_quote(symbol: str) -> dict:
    """Fetch a canonical, case-sensitive index symbol and preserve stale data."""
    cache_key = symbol.upper()
    cached = _LIVE_CACHE.get(cache_key)
    try:
        frame = _gap_chart(symbol, 260)
        if frame is None or frame.empty:
            raise RuntimeError("Vietcap gap-chart returned no index history")
        frame = frame.dropna(subset=["close"]).sort_values("time")
        close = pd.to_numeric(frame["close"], errors="coerce").dropna()
        price = float(close.iloc[-1])
        history = close.tail(250)
        if price <= 0 or history.empty or not 0.5 * float(history.min()) <= price <= 2.0 * float(history.max()):
            raise RuntimeError("Index close is outside its own historical validation range")
        previous = float(close.iloc[-2]) if len(close) > 1 else None
        volume = pd.to_numeric(frame.iloc[-1].get("accumulated_volume"), errors="coerce")
        value = pd.to_numeric(frame.iloc[-1].get("accumulated_value"), errors="coerce")
        quote = {
            "symbol": cache_key, "price": price,
            "change": price - previous if previous else None,
            "change_pct": price / previous - 1 if previous else None,
            "volume": float(volume) if pd.notna(volume) else None,
            "turnover": _index_turnover_vnd(value, volume),
            "as_of": _iso(frame.iloc[-1]["time"]), "stale": False,
            "source": "Vietcap gap-chart live",
        }
        _LIVE_CACHE[cache_key] = (time.time(), quote)
        return quote
    except Exception as exc:  # noqa: BLE001
        if cached:
            return {**cached[1], "stale": True, "error": str(exc)}
        try:
            from ..web.universe import load_ohlcv_snapshot

            fallback = load_ohlcv_snapshot(cache_key)
            if not fallback.empty:
                fallback = fallback.dropna(subset=["close"]).sort_values("time")
                last = fallback.iloc[-1]
                prev = fallback.iloc[-2] if len(fallback) > 1 else None
                price = float(last["close"])
                return {"symbol": cache_key, "price": price,
                        "change": price - float(prev["close"]) if prev is not None else None,
                        "change_pct": price / float(prev["close"]) - 1 if prev is not None else None,
                        "volume": None, "turnover": None, "as_of": _iso(last["time"]),
                        "stale": True, "source": "Packaged snapshot", "error": str(exc)}
        except Exception:  # noqa: BLE001
            pass
        return {"symbol": cache_key, "price": None, "change": None, "change_pct": None,
                "volume": None, "turnover": None, "as_of": None, "stale": True,
                "source": "Vietcap gap-chart", "error": str(exc)}


def _index_turnover_vnd(value, volume) -> float | None:
    """Normalize accumulatedValue to VND from its implied traded share price."""
    value = pd.to_numeric(value, errors="coerce")
    volume = pd.to_numeric(volume, errors="coerce")
    if pd.isna(value) or pd.isna(volume) or value <= 0 or volume <= 0:
        return None
    candidates = [float(value) * scale for scale in (1, 1_000, 1_000_000)]
    plausible = [amount for amount in candidates if 1_000 <= amount / float(volume) <= 1_000_000]
    return min(plausible) if plausible else None


def stock_live(symbol: str) -> dict:
    _row(symbol)
    return {**_live_quote(symbol), "session": _market_session(),
            "is_open": _market_session() in {"ATO", "Liên tục", "ATC"}}


def _agg_pe(f: pd.DataFrame) -> float | None:
    g = f[f["market_cap"].notna() & f["net_income_parent"].notna()]
    ni = g["net_income_parent"].sum()
    return float(g["market_cap"].sum() / ni) if ni > 0 else None


# ------------------------------------------------------------------ vi mo
_MACRO_CACHE: dict = {}


def macro_data(world_bank: bool = False):
    key = f"wb{world_bank}"
    hit = _MACRO_CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    md = load_macro(world_bank=world_bank)
    _MACRO_CACHE[key] = (time.time(), md)
    return md


def macro(company_type: str = "NON_FINANCIAL", world_bank: bool = True) -> dict:
    md = macro_data(world_bank)
    res = analyze_macro(md, company_type)
    from ..data.macro import load_manual

    manual = load_manual()
    rows = []
    for r in manual.dropna(subset=["value"]).itertuples():
        label = INDICATORS.get(r.indicator, (r.indicator, r.unit))[0]
        rows.append({"key": r.indicator, "label": label, "period": r.period, "value": r.value,
                     "unit": r.unit, "source": r.source, "as_of": r.as_of, "note": r.note})
    hist = {k: [{"year": int(y), "value": float(v)} for y, v in s.dropna().items()]
            for k, s in md.history.items()}
    impact = {}
    for ct in COMPANY_TYPE_LABELS:
        impact[ct] = analyze_macro(md, ct).sector_score
    return jsonable({
        "latest": md.latest, "table": rows, "score": res.score, "sector_impact": impact,
        "company_type": company_type, "sector_score": res.sector_score, "z": res.z,
        "commentary": analyze_macro_narrative({"macro": res}), "notes": md.notes, "history": hist,
        "provenance": prov("config/macro_vn.csv (GSO/NSO, NHNN, HNX – có URL từng dòng)"
                           + (" + World Bank Open Data API (chuỗi lịch sử)" if world_bank else ""),
                           max((r["as_of"] for r in rows if isinstance(r["as_of"], str)), default=None)),
    })


def _macro_impacts() -> dict:
    md = macro_data(False)
    return {ct: analyze_macro(md, ct).sector_score for ct in COMPANY_TYPE_LABELS}


# ------------------------------------------------------------------ nganh
def _bench_returns() -> dict:
    vni, _ = _vnindex_live(300)
    if vni.empty:
        return {}
    c = vni["close"].astype(float)
    ystart = vni[vni["time"] < pd.Timestamp(datetime.now().year, 1, 1)]["close"]
    out = {}
    for k, n in (("ret_1m", 21), ("ret_3m", 63), ("ret_1y", 250)):
        out[k] = float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else None
    out["ret_ytd"] = float(c.iloc[-1] / ystart.iloc[-1] - 1) if len(ystart) else None
    return out


def _historical_multiples(fin: StandardFinancials, ohlcv: pd.DataFrame, shares: float | None) -> dict:
    """Five completed FY multiples at adjusted year-end prices and current shares."""
    if fin.empty or ohlcv is None or ohlcv.empty or not shares:
        return {}
    frame = ohlcv.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["time", "close"]).sort_values("time")
    frame = frame[frame["time"].dt.month == 12].groupby(frame["time"].dt.year).tail(1)
    close_by_year = {int(row.time.year): float(row.close) for row in frame.itertuples()}
    multiples: dict[str, list[float]] = {"pe": [], "pb": []}
    for year in fin.years[-5:]:
        close = close_by_year.get(year)
        ni = fin.get("net_income_parent", year)
        equity = fin.get("equity", year)
        minority = fin.get("minority_interest", year) or 0.0
        parent_equity = equity - minority if equity is not None else None
        cap = close * shares if close is not None else None
        if cap and ni and ni > 0 and cap / ni < 60:
            multiples["pe"].append(cap / ni)
        if cap and parent_equity and parent_equity > 0 and cap / parent_equity <= 20:
            multiples["pb"].append(cap / parent_equity)
    return {
        key: tuple(float(pd.Series(values).quantile(q)) for q in (0.25, 0.5, 0.75))
        for key, values in multiples.items() if len(values) >= 3
    }


_SECTOR_CACHE: dict = {}


def sectors(level: int = 1, exchange: str | None = None) -> dict:
    level = int(min(max(level, 1), 4))
    uni, meta = _uni()
    if exchange:  # tinh lai chi so nganh chi tren cac ma cua san da chon
        uni = uni[uni["exchange"].isin([e.strip().upper() for e in exchange.split(",")])]
    ck = (level, exchange, meta.get("built_at"))
    hit = _SECTOR_CACHE.get(ck)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    bench = _bench_returns()
    impacts = _macro_impacts()
    total_cap = float(uni["market_cap"].sum())
    col = f"icb{level}"
    items = []
    for name, members in uni.groupby(col):
        st = sector_mod.node_stats(members, total_cap, bench)
        ctype = members.groupby("company_type")["market_cap"].sum().idxmax() \
            if members["market_cap"].notna().any() else members["company_type"].mode().iloc[0]
        sc = sector_mod.sector_score_universe(st, impacts.get(ctype))
        parent = {f"icb{parent_level}": members[f"icb{parent_level}"].iloc[0]
                  for parent_level in range(1, level)}
        items.append({"slug": node_key(level, name), "name": name, "level": level, **parent,
                      "company_type": ctype, **st, "score": sc["score"], "score_components": sc["components"]})
    for k in ("ret_1m", "ret_3m", "ret_ytd", "ret_1y", "score"):
        vals = sorted([i[k] for i in items if i.get(k) is not None], reverse=True)
        for i in items:
            i[f"rank_{k}"] = vals.index(i[k]) + 1 if i.get(k) is not None else None
    items.sort(key=lambda i: i["market_cap"], reverse=True)
    out = jsonable({
        "level": level, "exchange": exchange, "items": items, "benchmark": {"name": "VN-Index", **bench},
        "coverage": {"n_symbols": int(len(uni)), "n_classified": int((uni[col] != UNCLASSIFIED).sum()),
                     "sum_nodes": int(sum(i["n_symbols"] for i in items)),
                     "industry_source": uni["industry_source"].value_counts().to_dict()},
        "method": {
            "multiples": "Trung vị/P25/P75 chỉ trên mã đủ thanh khoản (GTGD TB20 ≥ 1 tỷ), loại P/E ≤ 0 hoặc > 100, P/B ≤ 0 hoặc > 20",
            "returns": "Hiệu suất ngành = bình quân gia quyền vốn hoá của lợi suất từng mã (≈ chỉ số cap-weighted)",
            "pe_aggregate": "P/E gộp = tổng vốn hoá / tổng LNST CĐ mẹ (năm BCTC gần nhất), chỉ mã có BCTC",
            "score": "Điểm ngành 0–100 = 40% động lực giá (3T & 1N so VN-Index) + 30% ROE trung vị + 30% tác động vĩ mô theo loại DN",
        },
        "provenance": universe_prov(meta),
    })
    _SECTOR_CACHE[ck] = (time.time(), out)
    return out


def sector_detail(slug: str) -> dict:
    m = re.match(r"^([1-4])-(.+)$", slug)
    if not m:
        raise NotFound(f"slug ngành không hợp lệ: {slug}")
    level = int(m.group(1))
    uni, meta = _uni()
    col = f"icb{level}"
    keys = uni[col].map(lambda n: node_key(level, n))
    members = uni[keys == slug]
    if members.empty:
        raise NotFound(f"Không có ngành {slug}")
    name = members[col].iloc[0]
    bench = _bench_returns()
    st = sector_mod.node_stats(members, float(uni["market_cap"].sum()), bench)
    ctype = members.groupby("company_type")["market_cap"].sum().idxmax()
    sc = sector_mod.sector_score_universe(st, _macro_impacts().get(ctype))
    idx = load_sector_index()
    series = idx[idx["node"].isin([slug, "VNINDEX"])].pivot_table(index="time", columns="node", values="value")
    series = series.rename(columns={slug: "sector", "VNINDEX": "vnindex"}).reset_index()
    children = []
    if level < 4:
        for cname, cm in members.groupby(f"icb{level + 1}"):
            children.append({"slug": node_key(level + 1, cname), "name": cname, "n_symbols": int(len(cm)),
                             "market_cap": float(cm["market_cap"].sum())})
    parents = [{"slug": node_key(parent_level, members[f"icb{parent_level}"].iloc[0]),
                "name": members[f"icb{parent_level}"].iloc[0], "level": parent_level}
               for parent_level in range(1, level)]
    cols = [c for c in UNIVERSE_COLS if c in members.columns]
    return jsonable({
        "slug": slug, "name": name, "level": level, "company_type": ctype, "parents": parents,
        "children": sorted(children, key=lambda c: -c["market_cap"]), "stats": st, "score": sc,
        "index_series": series, "benchmark": bench,
        "members": members.sort_values("market_cap", ascending=False)[cols],
        "provenance": universe_prov(meta),
    })


# ------------------------------------------------------------------ co phieu
def _row(symbol: str) -> pd.Series:
    uni, _ = _uni()
    hit = uni[uni["symbol"] == symbol.upper()]
    if hit.empty:
        raise NotFound(f"Không có mã {symbol} trong danh sách HOSE/HNX/UPCOM")
    return hit.iloc[0]


def profile(symbol: str) -> dict:
    row = _row(symbol)
    _, meta = _uni()
    cov = arminer_bctc.coverage()
    has = symbol.upper() in set(cov["ticker"])
    return jsonable({
        "symbol": row["symbol"], "name": row.get("name"), "exchange": row["exchange"],
        "icb": {f"icb{industry_level}": row[f"icb{industry_level}"] for industry_level in range(1, 5)},
        "icb_slugs": {f"icb{industry_level}": node_key(industry_level, row[f"icb{industry_level}"])
                      for industry_level in range(1, 5)},
        "industry_source": row["industry_source"], "website": row.get("website"),
        "company_type": row["company_type"], "company_type_label": COMPANY_TYPE_LABELS[row["company_type"]],
        "shares": row.get("shares"), "shares_source": row.get("shares_source"),
        "market_cap": row.get("market_cap"), "price": row.get("price"), "as_of_price": row.get("as_of_price"),
        "bctc_available": has,
        "bctc_note": None if has else "Chưa có nguồn BCTC (bộ dữ liệu arminer chỉ phủ HSX/HNX; "
                                      "vnstock không chạy được trên máy chủ web)",
        "provenance": universe_prov(meta),
    })


_PRICE_CACHE: dict = {}


def price_frame(symbol: str, days: int = 750) -> tuple[pd.DataFrame, dict]:
    sym = symbol.upper()
    cache_key = (sym, days)
    hit = _PRICE_CACHE.get(cache_key)
    if hit and time.time() - hit[0] < 300:
        return hit[1], hit[2]
    live = _gap_chart(sym, max(days, 500))
    if live is not None and len(live) > 5:
        frame, p = live, prov("Vietcap public API gap-chart (live)", live["time"].iloc[-1])
    else:
        frame = load_ohlcv_snapshot(sym)
        p = prov("Vietcap gap-chart – kho giá chụp khi dựng universe",
                 frame["time"].iloc[-1] if not frame.empty else None,
                 note="Không gọi được nguồn live; dùng bản chụp")
    frame = frame[["time", "open", "high", "low", "close", "volume"]].copy() if not frame.empty else frame
    _PRICE_CACHE[cache_key] = (time.time(), frame, p)
    return frame, p


def price(symbol: str, days: int = 365) -> dict:
    _row(symbol)
    frame, p = price_frame(symbol)
    f = frame.tail(days)
    vni, vp = _vnindex_live(max(days, 300))
    return jsonable({"symbol": symbol.upper(), "bars": f, "vnindex": vni.tail(days)[["time", "close"]] if not vni.empty else [],
                     "provenance": p, "vnindex_provenance": vp})


def financials_std(symbol: str, years: int = 10) -> StandardFinancials:
    row = _row(symbol)
    std = arminer_bctc.from_arminer(symbol, exchange=row["exchange"])
    if std is None:
        return StandardFinancials(symbol.upper(), pd.DataFrame(), "—",
                                  notes=["Chưa có nguồn BCTC cho mã này (arminer chỉ phủ HSX/HNX)"])
    std.frame = std.frame.tail(years)
    _fill_derived(std)
    return std


_KEY_ORDER = {
    "is": ["revenue", "net_interest_income", "fee_income", "total_operating_income", "cogs", "gross_profit",
           "selling_expense", "admin_expense", "operating_expense", "operating_profit", "provision",
           "interest_expense", "ebit", "ebitda", "pbt", "net_income", "net_income_parent", "eps_reported"],
    "bs": ["current_assets", "cash", "short_investments", "receivables", "inventory", "loans", "fixed_assets",
           "total_assets", "total_liabilities", "current_liabilities", "short_debt", "long_debt", "deposits",
           "equity", "charter_capital", "minority_interest"],
    "cf": ["cfo", "depreciation", "capex", "cfi", "dividends_paid", "cff"],
}


def _key_rank(std: StandardFinancials, statement: str) -> dict[str, tuple[int, str]]:
    """item_code -> (thu tu, ten chi tieu chuan) cho cac dong da anh xa."""
    out = {}
    for i, fld in enumerate(_KEY_ORDER[statement]):
        for code in re.findall(r"([a-z]{2}_[a-z0-9_]+) \(", std.mapping.get(fld, "")):
            out.setdefault(code, (i, FIELD_LABELS_VI.get(fld, fld)))
    return out


def financials(symbol: str, statement: str = "is", years: int = 5) -> dict:
    row = _row(symbol)
    statement = statement if statement in ("bs", "is", "cf") else "is"
    raw = arminer_bctc.raw_statement(symbol, statement, years, exchange=row["exchange"])
    if raw.empty:
        return {"symbol": symbol.upper(), "statement": statement, "rows": [], "years": [],
                "note": "Chưa có nguồn BCTC cho mã này", "provenance": prov("—")}
    year_cols = [c for c in raw.columns if isinstance(c, (int, np.integer))]
    base_code = {"bs": r"bs_tong_(cong_)?tai_san$", "is": r"is_(doanh_so_thuan|tong_thu_nhap_hoat_dong|doanh_thu_hoat_dong|doanh_thu_thuan_tu_hoat_dong_kinh_doanh_bao_hiem)$",
                 "cf": None}[statement]
    base = None
    if base_code:
        b = raw[raw["item_code"].str.match(base_code)]
        if not b.empty:
            base = b.iloc[0]
    std = financials_std(symbol, years)
    rank = _key_rank(std, statement)
    raw = raw.assign(_rank=raw["item_code"].map(lambda c: rank.get(c, (1000, ""))[0]))
    raw = raw.sort_values(["_rank", "item_name"], kind="stable").drop(columns="_rank")
    rows = []
    for r in raw.itertuples(index=False):
        d = r._asdict()
        vals = {int(y): raw.loc[raw["item_code"] == r.item_code, y].iloc[0] for y in year_cols}
        common = {y: (vals[y] / base[y] if base is not None and base[y] else None) for y in year_cols}
        yoy = {}
        for i, y in enumerate(year_cols[1:], 1):
            prev = vals[year_cols[i - 1]]
            yoy[y] = (vals[y] / prev - 1) if prev and pd.notna(prev) and prev > 0 and pd.notna(vals[y]) else None
        is_eps = "tren_co_phieu" in d["item_code"]
        rows.append({"item_code": d["item_code"], "item_name": d["item_name"], "values": vals,
                     "common_size": {y: None for y in year_cols} if is_eps else common, "yoy": yoy,
                     "unit": "VND/cp" if is_eps else "VND",
                     "group": "key" if d["item_code"] in rank else "detail",
                     "std_label": rank.get(d["item_code"], (0, None))[1]})
    return jsonable({
        "symbol": symbol.upper(), "statement": statement, "years": [int(y) for y in year_cols],
        "rows": rows, "common_size_base": None if base is None else base["item_name"],
        "unit": "VND", "mapping": std.mapping, "notes": std.notes,
        "provenance": prov(std.source, f"FY{max(year_cols)}",
                           note="BCTC năm hợp nhất; tên chỉ tiêu tiếng Việt gốc từ nguồn"),
    })


def ratios(symbol: str, years: int = 5) -> dict:
    row = _row(symbol)
    std = financials_std(symbol, years + 1)
    ctype = row["company_type"]
    if std.empty:
        return {"symbol": symbol.upper(), "groups": [], "note": "; ".join(std.notes), "provenance": prov("—")}
    r = compute_ratios(std, ctype).tail(years)
    keys = BANK_KEYS if ctype == "BANK" else NONFIN_KEYS
    formulas = {
        "gross_margin": "LN gộp / Doanh thu thuần", "operating_margin": "LN thuần HĐKD / Doanh thu thuần",
        "net_margin": "LNST / Doanh thu thuần", "roe": "LNST CĐ mẹ / VCSH CĐ mẹ bình quân",
        "roa": "LNST / Tổng tài sản bình quân", "debt_to_equity": "(Vay ngắn hạn + Vay dài hạn) / VCSH",
        "liabilities_to_assets": "Nợ phải trả / Tổng tài sản", "current_ratio": "TS ngắn hạn / Nợ ngắn hạn",
        "quick_ratio": "(TS ngắn hạn − Hàng tồn kho) / Nợ ngắn hạn",
        "interest_coverage": "(LNTT + Chi phí lãi vay) / Chi phí lãi vay",
        "asset_turnover": "Doanh thu / Tổng TS bình quân", "inventory_days": "Hàng tồn kho bq / Giá vốn × 365",
        "cfo_to_ni": "LCTT HĐKD / LNST", "fcf": "LCTT HĐKD − Capex", "revenue_growth": "DT năm t / DT năm t−1 − 1",
        "ni_growth": "LNST CĐ mẹ năm t / năm t−1 − 1", "nim": "Thu nhập lãi thuần / Tổng TS bình quân (xấp xỉ)",
        "cir": "Chi phí hoạt động / Tổng thu nhập hoạt động", "credit_cost": "Chi phí dự phòng / Cho vay KH bình quân",
        "ldr": "Cho vay KH / Tiền gửi KH", "equity_to_assets": "VCSH / Tổng tài sản",
        "loan_growth": "Cho vay KH năm t / năm t−1 − 1", "toi_growth": "TN hoạt động năm t / năm t−1 − 1",
    }
    groups_def = (
        [("Đặc thù ngân hàng", ["nim", "cir", "credit_cost", "ldr", "equity_to_assets"]),
         ("Sinh lời", ["roe", "roa"]), ("Tăng trưởng", ["loan_growth", "toi_growth", "ni_growth"])]
        if ctype == "BANK" else
        [("Sinh lời", ["gross_margin", "operating_margin", "net_margin", "roe", "roa"]),
         ("Cơ cấu vốn & thanh toán", ["debt_to_equity", "liabilities_to_assets", "current_ratio", "quick_ratio", "interest_coverage"]),
         ("Hiệu quả hoạt động & dòng tiền", ["asset_turnover", "inventory_days", "cfo_to_ni", "fcf"]),
         ("Tăng trưởng", ["revenue_growth", "ni_growth"])])
    groups = []
    for title, ks in groups_def:
        items = []
        for k in ks:
            if k not in r.columns or k not in keys:
                continue
            label, kind = RATIO_LABELS.get(k, (k, "x"))
            items.append({"key": k, "label": label, "kind": kind, "formula": formulas.get(k, ""),
                          "values": {int(y): v for y, v in r[k].items()}})
        if items:
            groups.append({"title": title, "items": items})
    return jsonable({"symbol": symbol.upper(), "company_type": ctype, "years": [int(y) for y in r.index],
                     "groups": groups, "growth": growth_summary(std, ctype), "notes": std.notes,
                     "provenance": prov(arminer_bctc.SOURCE_NAME + " → tự tính", f"FY{std.last_year()}")})


# ------------------------------------------------------------------ tin tuc & tai lieu
def _cafef_topic(symbol: str, timeout: float = 6) -> list[dict]:
    """Trang chu de theo ma tren CafeF (giong CafeFScraper cua vn-annual-report-miner)."""
    import html as htmlmod

    import requests

    url = f"https://cafef.vn/{symbol.lower()}.html"
    resp = requests.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"})
    if resp.status_code != 200:
        return []
    items, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="([^"]+-(\d{12,})\.chn)"[^>]*?(?:title="([^"]+)")?[^>]*>(.*?)</a>', resp.text, re.S):
        href, idnum, title_attr, inner = m.groups()
        title = htmlmod.unescape(re.sub(r"<[^>]+>", "", title_attr or inner or "")).strip()
        if len(title) < 15 or href in seen:
            continue
        seen.add(href)
        link = href if href.startswith("http") else f"https://cafef.vn{href if href.startswith('/') else '/' + href}"
        # ma bai CafeF dang 188YYMMDDhhmm... -> ngay dang
        pub = None
        dm = re.match(r"\d{3}(\d{2})(\d{2})(\d{2})", idnum)
        if dm:
            try:
                pub = datetime(2000 + int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            except ValueError:
                pub = None
        items.append({"title": title, "link": link, "published_at": pub, "source": "CafeF (trang chủ đề mã)"})
        if len(items) >= 25:
            break
    return items


def news(symbol: str) -> dict:
    row = _row(symbol)
    sym = row["symbol"]
    items: list[dict] = []
    status = {}

    def topic():
        return _cafef_topic(sym)

    def rss():
        from ..data.macro_news import fetch_all_macro_news

        return fetch_all_macro_news()

    with ThreadPoolExecutor(max_workers=2) as ex:
        ft, fr = ex.submit(topic), ex.submit(rss)
        wait([ft, fr], timeout=12)
        try:
            got = ft.result(timeout=0) if ft.done() else []
            # trang chu de co ca tin o thanh ben -> chi giu tieu de nhac den ma / ten / thuong hieu
            from ..news_matching import match_reason

            rel = []
            for g in got:
                reason = match_reason(sym, g.get("title", ""), name=row.get("name"), brand=row.get("brand"))
                if reason:
                    rel.append({**g, "match_reason": reason})
            items.extend(rel)
            status["cafef_topic"] = (f"{len(rel)}/{len(got)} tin nhắc tới {sym}" if ft.done() else "quá thời gian")
        except Exception as exc:  # noqa: BLE001
            status["cafef_topic"] = f"lỗi: {exc}"
        macro_items = []
        try:
            heads = fr.result(timeout=0) if fr.done() else []
            from ..news_matching import match_reason

            for it in heads:
                d = {"title": it.title, "link": it.link, "published_at": it.published_at, "source": it.source}
                reason = match_reason(sym, it.title, it.summary, row.get("name"), row.get("brand"))
                if reason:
                    items.append({**d, "match_reason": reason})
                macro_items.append(d)
            status["rss"] = f"{len(heads)} tin vĩ mô/thị trường" if fr.done() else "quá thời gian"
        except Exception as exc:  # noqa: BLE001
            status["rss"] = f"lỗi: {exc}"
    # khu trung: cung bai xuat hien o trang chu de CafeF va RSS (link khac nhau) -> giu ban co gio dang
    from ..news_matching import normalize as _norm

    best: dict[str, dict] = {}
    for i in items:
        k = _norm(i["title"])
        ts = pd.Timestamp(i["published_at"]) if i.get("published_at") is not None else None
        has_time = ts is not None and (ts.hour or ts.minute)
        if k not in best or (has_time and not best[k].get("_t")):
            best[k] = {**i, "_t": bool(has_time)}
    items = [{k: v for k, v in i.items() if k != "_t"} for i in best.values()]
    dated = [i for i in items if i.get("published_at") is not None]
    for i in dated:
        ts = pd.Timestamp(i["published_at"])
        i["published_at"] = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).tz_convert(TZ).tz_localize(None)
    sent = analyze_news(dated, pd.Timestamp.now(tz=TZ).tz_localize(None))
    scored = {i["link"]: i for i in sent.items}
    out_items = []
    for i in items:
        s = scored.get(i["link"], {})
        out_items.append({**i, "sentiment": s.get("sentiment"), "pos": s.get("pos"), "neg": s.get("neg")})
    out_items.sort(key=lambda x: pd.Timestamp(x["published_at"]) if x.get("published_at") is not None else pd.Timestamp(0), reverse=True)
    return jsonable({
        "symbol": sym, "items": out_items[:30], "macro_headlines": macro_items[:8],
        "sentiment": {"score": sent.score, "score_100": sent.score_100, "n_pos": sent.n_pos, "n_neg": sent.n_neg},
        "status": status,
        "provenance": prov("CafeF trang chủ đề mã + RSS CafeF/VnExpress; chấm cảm xúc bằng từ điển tài chính tiếng Việt (analysis/sentiment.py)",
                           datetime.now(TZ)),
    })


def documents(symbol: str) -> dict:
    _row(symbol)
    z = zenodo_index()
    hit = z[(z["ticker_file"] == symbol.upper())] if not z.empty else z
    items = []
    for r in hit.sort_values("year_full", ascending=False).itertuples():
        items.append({"year": int(r.year_full), "type": r.document_type, "file_name": r.file_name,
                      "size_mb": r.file_size_mb, "status": r.status,
                      "zenodo": ZENODO_RECORD, "cafef_cdn": CAFEF_CDN.format(name=r.file_name)})
    return jsonable({"symbol": symbol.upper(), "items": items,
                     "provenance": prov("Zenodo master index – Ngô Phú Thạnh (2025), DOI 10.5281/zenodo.20949551; "
                                        "link dự phòng CDN CafeF theo mẫu tên file của zenodo_downloader.py",
                                        None, note="Chỉ hiện link, không xử lý PDF trên máy chủ")})


# ------------------------------------------------------------------ phan tich tong hop
class _SectorView:
    """Doi tuong tuong thich SectorResult cho composite.build_thesis_and_risks."""

    def __init__(self, medians, quantiles, performance, score):
        self.medians, self.quantiles, self.performance, self.score = medians, quantiles, performance, score


def _pb_roe_adjust(peers: pd.DataFrame, roe_own, quant: dict) -> tuple[dict, dict | None]:
    """Adjust the peer P/B median only when a liquid-peer ROE fit is credible."""
    if roe_own is None or pd.isna(roe_own) or "pb" not in quant:
        return quant, None
    liq = sector_mod._clean_multiples(peers)[["pb", "roe"]].dropna()
    liq = liq[(liq["roe"] > -0.2) & (liq["roe"] < 0.6)]
    if len(liq) < 8:
        return quant, None
    b, a = np.polyfit(liq["roe"], liq["pb"], 1)
    r2 = float(np.corrcoef(liq["roe"], liq["pb"])[0, 1] ** 2)
    if not np.isfinite(b) or not np.isfinite(r2) or b <= 0 or r2 < 0.10:
        return quant, None
    pred = float(np.clip(a + b * roe_own, liq["pb"].quantile(0.25), liq["pb"].quantile(0.9)))
    adj = dict(quant)
    adj["pb"] = (quant["pb"][0], pred, max(pred, quant["pb"][2]))
    return adj, {"a": float(a), "b": float(b), "r2": r2, "n": int(len(liq)), "roe": float(roe_own),
                 "pb_median": quant["pb"][1], "pb_target": pred}


def _beta(ohlcv: pd.DataFrame, bench: pd.DataFrame) -> float | None:
    from ..data.prices import beta

    try:
        return beta(ohlcv, bench)
    except Exception:  # noqa: BLE001
        return None


def analysis(symbol: str, years: int = 5, with_news: bool = True) -> dict:
    row = _row(symbol)
    sym, ctype = row["symbol"], row["company_type"]
    uni, meta = _uni()
    sources = [{"item": "Danh mục, ngành, số CP", **universe_prov(meta)}]
    ohlcv, pprov = price_frame(sym, 1900)
    sources.append({"item": f"Giá OHLCV {sym}", **pprov})
    bench, bprov = _vnindex_live(800)
    sources.append({"item": "VN-Index", **bprov})
    fin = financials_std(sym, years + 1)
    if not fin.empty:
        sources.append({"item": f"BCTC năm {sym}", **prov(fin.source, f"FY{fin.last_year()}", note="; ".join(fin.notes) or None)})
    else:
        sources.append({"item": f"BCTC năm {sym}", **prov("—", note="; ".join(fin.notes)), "ok": False})

    price_now = float(ohlcv["close"].iloc[-1]) if not ohlcv.empty else row.get("price")
    shares = row.get("shares")
    shares = float(shares) if shares is not None and pd.notna(shares) else None
    rt = compute_ratios(fin, ctype) if not fin.empty else pd.DataFrame()
    growth = growth_summary(fin, ctype) if not fin.empty else {}

    peers, lvl, node_name = sector_mod.peers_from_universe(uni, sym)
    quant = sector_mod.universe_quantiles(peers)
    bench_ret = _bench_returns()
    peer_stats = sector_mod.node_stats(peers, float(uni["market_cap"].sum()), bench_ret)
    md = macro_data(False)
    mres = analyze_macro(md, ctype)
    macro_commentary = analyze_macro_narrative({"macro": mres})
    sc = sector_mod.sector_score_universe(peer_stats, mres.sector_score)
    perf = {"sector_ret_3m": peer_stats.get("ret_3m"), "bench_ret_3m": bench_ret.get("ret_3m"),
            "sector_ret_1y": peer_stats.get("ret_1y"), "bench_ret_1y": bench_ret.get("ret_1y")}
    sector_view = _SectorView({k: v[1] for k, v in quant.items()}, quant, perf, sc["score"])
    rf = md.latest.get("gov_bond_10y", {}).get("value")
    rf = rf / 100 if rf else None
    beta = _beta(ohlcv, bench) if not bench.empty and not ohlcv.empty else None
    quant_val, comparison = sector_mod.valuation_comparison(peers, sym, row.get("market_cap"))
    special_cases = get_settings().get("valuation.special_cases", {}) or {}
    if sym.upper() in special_cases:
        pb_regression = None
    else:
        regression_peers = peers[peers["symbol"].astype(str).str.upper() != sym.upper()]
        quant_val, pb_regression = _pb_roe_adjust(regression_peers, row.get("roe"), quant_val)
    historical = _historical_multiples(fin, ohlcv, shares)
    ni_ttm = row.get("ni_ttm")
    ni_ttm = float(ni_ttm) if ni_ttm is not None and pd.notna(ni_ttm) else None
    val = value_company(fin, ctype, price_now, shares, rt, quant_val, beta, rf,
                        net_income_ttm=ni_ttm, historical_multiples=historical, symbol=sym)

    tech = None
    if len(ohlcv) >= 120:
        try:
            from ..analysis.technical import recommend

            tech = recommend(ohlcv.reset_index(drop=True), sym)
        except Exception:  # noqa: BLE001
            tech = None
    news_res = news(sym) if with_news else None
    sent_score = news_res["sentiment"]["score_100"] if news_res and news_res["items"] else None

    vchecks = (checks.check_financials(fin, ctype) if not fin.empty else []) \
        + checks.check_prices(ohlcv, row["exchange"]) \
        + (checks.cross_check(fin, rt, row.get("pe")) if not fin.empty else [])
    vchecks += _extra_checks(fin, row)

    scores = {
        "macro": mres.sector_score, "sector": sc["score"],
        "quality": comp.quality_score(rt, ctype) if not rt.empty else None,
        "growth": comp.growth_score(growth) if growth else None,
        "valuation": None if val.confidence == "THẤP" else comp.valuation_score(val.upside),
        "technical": comp.technical_score(tech.total_score if tech else None),
        "sentiment": sent_score,
    }
    result = comp.combine(scores, val.upside, valuation_confidence=val.confidence,
                          valuation_confidence_reason=val.confidence_reason)

    class _Sent:
        score = (news_res or {}).get("sentiment", {}).get("score")
        n_pos = (news_res or {}).get("sentiment", {}).get("n_pos", 0)
        n_neg = (news_res or {}).get("sentiment", {}).get("n_neg", 0)

    ctx = {"ratios": rt, "growth": growth, "valuation": val, "sector": sector_view, "macro": mres,
           "technical": tech, "sentiment": _Sent if news_res and news_res["items"] else None,
           "company_type": ctype}
    comp.build_thesis_and_risks(ctx, result)

    pos = sector_mod.position_in(peers, sym)
    cols = ["symbol", "name", "exchange", "icb4", "market_cap", "price", "pe", "pb", "ev_ebitda", "roe",
            "net_margin", "ni_growth", "ret_1y", "liquidity_flag", "avg_value_20d"]
    peer_table = peers.sort_values("market_cap", ascending=False)[[c for c in cols if c in peers.columns]]
    ratios_last = rt.iloc[-1].to_dict() if not rt.empty else {}

    out = {
        "symbol": sym, "name": row.get("name"), "exchange": row["exchange"],
        "company_type": ctype, "company_type_label": COMPANY_TYPE_LABELS[ctype],
        "icb": {f"icb{industry_level}": row[f"icb{industry_level}"] for industry_level in range(1, 5)},
        "icb_slugs": {f"icb{industry_level}": node_key(industry_level, row[f"icb{industry_level}"])
                      for industry_level in range(1, 5)},
        "price": price_now, "as_of_price": _iso(ohlcv["time"].iloc[-1]) if not ohlcv.empty else row.get("as_of_price"),
        "shares": shares, "shares_source": row.get("shares_source"),
        "market_cap": price_now * shares if price_now and shares else None,
        "metrics": {k: row.get(k) for k in ("pe", "pe_ttm", "eps_ttm", "ni_ttm", "ttm_label", "pb", "ev_ebitda", "roe", "net_margin", "ni_growth",
                                            "debt_to_equity", "eps", "avg_value_20d", "ret_1m", "ret_3m",
                                            "ret_ytd", "ret_1y", "fin_year")},
        "eps_basis": (f"P/E FY{int(row['fin_year'])} (BCTC năm arminer)"
                      + (f"; {row['ttm_label']} = {row['pe_ttm']:.1f}x (vnstock quý {row['ttm_periods']})"
                         if pd.notna(row.get("pe_ttm")) else "; chưa có số quý (TTM) cho mã này"))
                     if pd.notna(row.get("fin_year")) else None,
        "recommendation": {"rating": result.rating, "base_rating": result.base_rating,
                           "reason": result.rating_reason, "total_score": result.total,
                           "scores": result.scores, "weights": result.weights_used,
                           "target_price": val.target_price, "targets": val.target, "upside": val.upside},
        "thesis": result.thesis, "risks": result.risks,
        "valuation": {
            "methods": [dataclasses.asdict(m) for m in val.methods], "targets": val.target,
            "upside": val.upside, "assumptions": val.assumptions, "skipped": val.skipped,
            "per_share": val.per_share,
            "confidence": val.confidence, "confidence_reason": val.confidence_reason,
            "shares": shares, "shares_source": row.get("shares_source"),
            "shares_as_of": meta.get("built_at"),
            "history_years": fin.years[-5:],
            "historical_multiples": historical,
            "multiples_source": (f"{comparison['source']} tại ICB cấp {lvl} '{node_name}' "
                                 f"({comparison['peer_count']} mã so sánh; đủ thanh khoản)"),
            "comparison": comparison,
            "pb_roe_regression": pb_regression,
        },
        "sector": {
            "level": lvl, "name": node_name, "slug": node_key(lvl, node_name) if lvl else None,
            "n_peers": int(len(peers)), "n_liquid": int(peers["liquidity_flag"].sum()),
            "stats": peer_stats, "quantiles": quant, "position": pos, "score": sc,
            "note": f"So sánh ở ICB cấp {lvl} ({node_name}): {len(peers)} mã, "
                    f"{int(peers['liquidity_flag'].sum())} mã đủ thanh khoản; dữ liệu lúc {meta.get('built_at')}",
            "peers": peer_table,
        },
        "macro": {"score": mres.score, "sector_score": mres.sector_score, "label": mres.sector_label,
                  "commentary": macro_commentary, "table": mres.table},
        "ratios_last": ratios_last, "growth": growth,
        "technical": None if tech is None else {
            "action": tech.action, "total_score": tech.total_score, "components": tech.component_scores,
            "confidence": tech.confidence, "close": tech.close, "entry": [tech.entry_low, tech.entry_high],
            "stop_loss": tech.stop_loss, "target": tech.target, "risk_reward": tech.risk_reward,
            "reasons": tech.reasons, "vetoed_by_kumo": tech.vetoed_by_kumo,
            "rsi": tech.rsi_state, "macd": tech.macd_state},
        "news": news_res,
        "checks": [c.to_dict() for c in vchecks], "checks_summary": checks.summarize(vchecks),
        "financial_mapping": fin.mapping, "financial_notes": fin.notes,
        "bctc_available": not fin.empty,
        "bctc_note": None if not fin.empty else f"Chưa có BCTC từ nguồn {arminer_bctc.SOURCE_NAME}; kỳ gần nhất: chưa có.",
        "sources": sources,
        "generated_at": now_str(),
        "provenance": prov("Tổng hợp – xem 'sources'", _iso(ohlcv["time"].iloc[-1]) if not ohlcv.empty else None),
    }
    return jsonable(out)


def _extra_checks(fin: StandardFinancials, row: pd.Series) -> list:
    out = []
    if fin.empty:
        return out
    y = fin.last_year()
    ta, tl, eq = fin.get("total_assets", y), fin.get("total_liabilities", y), fin.get("equity", y)
    if ta and tl is not None and eq is not None:
        d = abs(tl + eq - ta) / ta
        out.append(checks.Check("Tổng TS = Nợ + VCSH (arminer)", "PASS" if d < 0.005 else "WARN",
                                f"FY{y}: lệch {d:.3%}"))
    eps_rep = fin.get("eps_reported", y)
    nip = fin.get("net_income_parent", y)
    shares = row.get("shares")
    if eps_rep and nip and shares and pd.notna(shares):
        eps_calc = nip / shares
        d = abs(eps_calc - eps_rep) / abs(eps_rep)
        out.append(checks.Check("EPS tự tính vs EPS báo cáo", "PASS" if d < 0.15 else "WARN",
                                f"FY{y}: tự tính {eps_calc:,.0f} đ (LNST CĐ mẹ / {shares:,.0f} CP hiện tại) vs báo cáo "
                                f"{eps_rep:,.0f} đ, lệch {d:.1%}"
                                + (" – thường do phát hành thêm/thưởng CP sau kỳ báo cáo hoặc trích quỹ" if d >= 0.15 else "")))
    return out


def sources_live() -> dict:
    """Test live tung nguon ngay tren may chu dang chay."""
    tests = {}

    def t(name, fn, *, cached=False):
        t0 = time.time()
        try:
            detail = fn()
            elapsed = int((time.time() - t0) * 1000)
            status = "ĐÓNG GÓI–CACHE" if cached else "TRỄ" if elapsed > 3000 else "LIVE"
            tests[name] = {"ok": True, "status": status, "ms": None if cached else elapsed, "detail": detail}
        except Exception as exc:  # noqa: BLE001
            status = "L\u1ed6I"
            if name == "DNSE OHLC VNINDEX":
                detail = str(exc).lower()
                if "dnse_api_key" in detail or "dnse_api_secret" in detail:
                    status = "CH\u01afA C\u1ea4U H\u00ccNH"
                elif any(token in detail for token in ("http 401", "http 403", "oa-400", "authorization")):
                    status = "L\u1ed6I X\u00c1C TH\u1ef0C"
                elif any(token in detail for token in ("connection", "timeout", "dns", "k???t n???i",
                                                       "khong ket noi", "không kết nối", "could not connect")):
                    status = "KH\u00d4NG K\u1ebeT N\u1ed0I \u0110\u01af\u1ee2C T\u1eea M\u00c1Y CH\u1ee6"
            tests[name] = {"ok": False, "status": status, "ms": int((time.time() - t0) * 1000),
                           "detail": f"{type(exc).__name__}: {exc}"}

    def vietcap():
        f = _gap_chart("FPT", 5)
        if f is None or f.empty:
            raise RuntimeError("gap-chart không trả dữ liệu (có thể bị chặn IP máy chủ)")
        return f"FPT close {f['close'].iloc[-1]:,.0f} ngày {_iso(f['time'].iloc[-1])}"

    def board():
        from ..data.vietcap import probe_endpoint

        st, data, err = probe_endpoint("POST", "/price/symbols/getList", {"symbols": ["FPT"]}, timeout=6)
        if st != 200 or not data:
            raise RuntimeError(f"HTTP {st} {err or ''}")
        return f"HTTP {st}, listedShare={(data[0] if isinstance(data, list) else {}).get('listingInfo', {}).get('listedShare')}"

    def arminer():
        cov = arminer_bctc.coverage()
        return f"{len(cov)} mã, FY{int(cov['last_year'].max())}"

    def uni():
        u, m = _uni()
        return f"{len(u)} mã, giá đến {m.get('as_of_price')}, nguồn {m.get('origin')}"

    def wb():
        import requests

        r = requests.get("https://api.worldbank.org/v2/country/VNM/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=3", timeout=6)
        r.raise_for_status()
        return f"HTTP {r.status_code}"

    def cafef():
        count = len(_cafef_topic('FPT', 6))
        if count == 0:
            raise RuntimeError("không nhận được tin từ trang mã FPT; có thể nguồn chặn/yêu cầu API trả rỗng")
        return f"{count} tin FPT"

    def rss():
        from ..data.macro_news import fetch_feed_items

        return f"{len(fetch_feed_items('https://vnexpress.net/rss/kinh-doanh.rss', 'VnExpress', timeout=6))} tin"

    def dnse():
        from ..data.dnse import DnseProvider

        status, count, error = DnseProvider().probe_ohlc("VNINDEX", days=14)
        if status != 200 or count < 5:
            raise RuntimeError(f"OHLC VNINDEX 5 phiên không hợp lệ: HTTP {status}, {count} phiên; {error or ''}")
        return f"OHLC VNINDEX thật: HTTP {status}, {count} phiên"

    def rss_count(url, source):
        import requests
        import xml.etree.ElementTree as ET

        response = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0 invest-system-source-check"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        count = len(root.findall(".//item"))
        if count == 0:
            raise RuntimeError("HTTP thành công nhưng RSS không có item")
        return count

    feeds = [
        ("CafeF Vĩ mô & đầu tư RSS", "https://cafef.vn/vi-mo-dau-tu.rss", "chung"),
        ("CafeF thị trường chứng khoán RSS", "https://cafef.vn/thi-truong-chung-khoan.rss", "chung"),
        ("CafeF tài chính ngân hàng RSS", "https://cafef.vn/tai-chinh-ngan-hang.rss", "chung"),
        ("VnExpress Kinh doanh RSS", "https://vnexpress.net/rss/kinh-doanh.rss", "chung"),
    ]
    feed_jobs = {name: (lambda url=url, name=name: f"{rss_count(url, name)} tin") for name, url, _ in feeds}

    jobs = {"Vietcap gap-chart (giá)": vietcap, "Vietcap getList (bảng giá, số CP)": board,
            "World Bank API": wb,
            "CafeF trang chủ đề mã": cafef, "DNSE OHLC VNINDEX": dnse, **feed_jobs}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(t, n, f) for n, f in jobs.items()]
        wait(futs, timeout=15)
    tests["BCTC arminer (đóng gói)"] = {"ok": True, "status": "ĐÓNG GÓI–CACHE", "ms": None,
                                      "detail": "Dữ liệu BCTC đã đóng gói; không gọi mạng khi kiểm tra."}
    tests["Bảng toàn thị trường"] = {"ok": True, "status": "ĐÓNG GÓI–CACHE", "ms": None,
                                   "detail": "Universe dựng sẵn trong gói triển khai; không gọi mạng khi kiểm tra."}
    feed_counts = {name: int(re.search(r"\d+", tests[name]["detail"]).group()) if name in tests and tests[name]["ok"] else None
                   for name, _, _ in feeds}
    news_sources = [
        {"name": "CafeF trang chủ đề mã", "url": "https://cafef.vn/fpt.html", "type": "theo mã FPT",
         "count": int(re.search(r"\d+", tests["CafeF trang chủ đề mã"]["detail"]).group())
         if tests.get("CafeF trang chủ đề mã", {}).get("ok") else None},
        *[{"name": name, "url": url, "type": feed_type, "count": feed_counts[name]}
          for name, url, feed_type in feeds],
        {"name": "Công bố thông tin Vietcap/VCI", "url": "https://trading.vietcap.com.vn/",
         "type": "theo mã", "count": None,
         "note": "Nguồn company.news() chỉ hoạt động nếu vnstock/VCI được cài trong runtime."},
    ]
    return jsonable({"tested_at": now_str(), "results": tests, "news_sources": news_sources,
                     "news_quality": {"sample_symbols": 20, "manual_precision": 0.977273,
                                      "reviewed_titles": 132, "precision_target": 0.90,
                                      "audit_as_of": "2026-10-09",
                                      "coverage_note": "Đọc thủ công tối đa 10 tiêu đề mỗi mã; nguồn không truy cập được đánh dấu lỗi, không hiểu số 0 là không có tin."}})


def bctc_coverage() -> dict:
    path = Path(__file__).resolve().parents[3] / "webdata" / "bctc_coverage.json"
    if not path.exists():
        return {"error": "Chưa tạo báo cáo độ phủ. Chạy scripts/check_bctc_coverage.py."}
    return json.loads(path.read_text(encoding="utf-8"))


def label_fields() -> dict:
    return FIELD_LABELS_VI
