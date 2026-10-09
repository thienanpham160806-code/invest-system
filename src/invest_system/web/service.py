"""Dich vu cho web API: doc universe + BCTC arminer + gia, chay lai cac module phan tich san co.

Nguyen tac: moi khoi du lieu tra ve kem `provenance` = {source, as_of, fetched_at};
thieu so -> None + ly do (khong bia, khong dung du lieu demo cho ma that).
"""
from __future__ import annotations

import dataclasses
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..analysis import composite as comp
from ..analysis import sector as sector_mod
from ..analysis.macro import analyze_macro
from ..analysis.ratios import BANK_KEYS, NONFIN_KEYS, RATIO_LABELS, compute_ratios, growth_summary
from ..analysis.sentiment import analyze_news
from ..analysis.valuation import value_company
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
    "pe_ttm", "ttm_label",
]


def universe_prov(meta: dict) -> dict:
    src = meta.get("sources", {})
    return prov("Bảng toàn thị trường: " + "; ".join(f"{k}: {v}" for k, v in src.items()),
                meta.get("as_of_price"), origin=meta.get("origin"), built_at=meta.get("built_at"),
                as_of_fin=meta.get("as_of_fin_max"))


def _uni() -> tuple[pd.DataFrame, dict]:
    uni, meta = load_universe()
    return uni, meta


def search(q: str, limit: int = 12) -> dict:
    uni, meta = _uni()
    q = (q or "").strip()
    if not q:
        return {"items": [], "provenance": universe_prov(meta)}
    from .universe import _strip

    qs = _strip(q)
    sym = uni["symbol"].str.upper()
    exact = uni[sym == q.upper()]
    starts = uni[sym.str.startswith(q.upper()) & (sym != q.upper())]
    names = (uni["name"].fillna("") + " " + (uni["brand"].fillna("") if "brand" in uni.columns else "")).map(_strip)
    by_name = uni[names.str.contains(re.escape(qs), regex=True) & ~sym.str.startswith(q.upper())]
    hits = pd.concat([exact, starts, by_name]).drop_duplicates("symbol").head(limit)
    cols = [c for c in ["symbol", "name", "brand", "exchange", "icb2", "icb4", "price", "market_cap"] if c in hits.columns]
    return {"items": jsonable(hits[cols]), "provenance": universe_prov(meta)}


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


# ------------------------------------------------------------------ thi truong
_VNI_CACHE: dict = {}


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
        frame = pd.DataFrame({
            "time": pd.to_datetime(pd.Series(item["t"], dtype="int64"), unit="s"),
            "open": item.get("o"), "high": item.get("h"), "low": item.get("l"),
            "close": item.get("c"), "volume": item.get("v"),
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


_SECTOR_CACHE: dict = {}


def sectors(level: int = 1) -> dict:
    level = int(min(max(level, 1), 4))
    uni, meta = _uni()
    ck = (level, meta.get("built_at"))
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
        "level": level, "items": items, "benchmark": {"name": "VN-Index", **bench},
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
    hit = _PRICE_CACHE.get(sym)
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
    _PRICE_CACHE[sym] = (time.time(), frame, p)
    return frame, p


def price(symbol: str, days: int = 365) -> dict:
    _row(symbol)
    frame, p = price_frame(symbol)
    f = frame.tail(days)
    vni, vp = _vnindex_live(max(days, 300))
    return jsonable({"symbol": symbol.upper(), "bars": f, "vnindex": vni.tail(days)[["time", "close"]] if not vni.empty else [],
                     "provenance": p, "vnindex_provenance": vp})


def financials_std(symbol: str, years: int = 10) -> StandardFinancials:
    std = arminer_bctc.from_arminer(symbol)
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
    _row(symbol)
    statement = statement if statement in ("bs", "is", "cf") else "is"
    raw = arminer_bctc.raw_statement(symbol, statement, years)
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
        "provenance": prov(arminer_bctc.SOURCE_NAME, f"FY{max(year_cols)}",
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
            items.extend(got)
            status["cafef_topic"] = f"{len(got)} tin" if ft.done() else "quá thời gian"
        except Exception as exc:  # noqa: BLE001
            status["cafef_topic"] = f"lỗi: {exc}"
        macro_items = []
        try:
            heads = fr.result(timeout=0) if fr.done() else []
            from .universe import _strip

            short = _strip(str(row.get("name") or "").replace("Công ty Cổ phần", "").replace("Công ty CP", "")).strip()
            for it in heads:
                text = f" {it.title} {it.summary} "
                d = {"title": it.title, "link": it.link, "published_at": it.published_at, "source": it.source}
                if f" {sym} " in text or f"({sym})" in text or (len(short) > 6 and short in _strip(text)):
                    items.append(d)
                macro_items.append(d)
            status["rss"] = f"{len(heads)} tin vĩ mô/thị trường" if fr.done() else "quá thời gian"
        except Exception as exc:  # noqa: BLE001
            status["rss"] = f"lỗi: {exc}"
    dated = [i for i in items if i.get("published_at") is not None]
    for i in dated:
        ts = pd.Timestamp(i["published_at"])
        i["published_at"] = ts.tz_convert(None) if ts.tzinfo else ts
    sent = analyze_news(dated, pd.Timestamp.now())
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
    """P/B muc tieu theo hoi quy P/B = a + b*ROE tren toan nhom peers du thanh khoan
    (DN sinh loi cao xung dang P/B cao hon trung vi). Chi ap dung khi >= 8 diem, he so
    goc duong; ket qua cat trong [P10, P90] P/B cua nganh. Dich ca bo ba kich ban."""
    if roe_own is None or pd.isna(roe_own) or "pb" not in quant:
        return quant, None
    liq = sector_mod._clean_multiples(peers)[["pb", "roe"]].dropna()
    liq = liq[(liq["roe"] > -0.2) & (liq["roe"] < 0.6)]
    if len(liq) < 8:
        return quant, None
    b, a = np.polyfit(liq["roe"], liq["pb"], 1)
    r2 = float(np.corrcoef(liq["roe"], liq["pb"])[0, 1] ** 2)
    if b <= 0 or r2 < 0.05:
        return quant, None
    pred = float(np.clip(a + b * roe_own, liq["pb"].quantile(0.1), liq["pb"].quantile(0.9)))
    delta = pred - quant["pb"][1]
    adj = dict(quant)
    adj["pb"] = tuple(max(x + delta, 0.1) for x in quant["pb"])
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
    ohlcv, pprov = price_frame(sym)
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
    quant_val, pb_reg = _pb_roe_adjust(peers, row.get("roe"), quant)
    val = value_company(fin, ctype, price_now, shares, rt, quant_val, beta, rf)
    for m in val.methods:
        if m.key == "pb_relative" and pb_reg:
            m.inputs["Nguồn bội số"] = (f"hồi quy P/B–ROE ngành (n={pb_reg['n']}, R²={pb_reg['r2']:.2f}): "
                                        f"ROE {pb_reg['roe']:.1%} → P/B {pb_reg['pb_target']:.2f}x "
                                        f"(trung vị {pb_reg['pb_median']:.2f}x)")

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
        "valuation": comp.valuation_score(val.upside),
        "technical": comp.technical_score(tech.total_score if tech else None),
        "sentiment": sent_score,
    }
    result = comp.combine(scores, val.upside)

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
            "multiples_source": f"Phân vị P25/P50/P75 của toàn bộ {len(peers)} mã ICB cấp {lvl} '{node_name}' "
                                f"(chỉ mã đủ thanh khoản, đã loại ngoại lai)"
                                + ("; P/B mục tiêu điều chỉnh theo hồi quy P/B–ROE của ngành" if pb_reg else ""),
            "pb_roe_regression": pb_reg,
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

    def t(name, fn):
        t0 = time.time()
        try:
            detail = fn()
            tests[name] = {"ok": True, "ms": int((time.time() - t0) * 1000), "detail": detail}
        except Exception as exc:  # noqa: BLE001
            tests[name] = {"ok": False, "ms": int((time.time() - t0) * 1000), "detail": f"{type(exc).__name__}: {exc}"}

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
        return f"{len(_cafef_topic('FPT', 6))} tin FPT"

    def rss():
        from ..data.macro_news import fetch_feed_items

        return f"{len(fetch_feed_items('https://vnexpress.net/rss/kinh-doanh.rss', 'VnExpress', timeout=6))} tin"

    def dnse():
        import os

        if not os.getenv("DNSE_API_KEY"):
            return "bỏ qua – không có DNSE_API_KEY trong env"
        return "có key"

    jobs = {"Vietcap gap-chart (giá)": vietcap, "Vietcap getList (bảng giá, số CP)": board,
            "BCTC arminer (đóng gói)": arminer, "Bảng toàn thị trường": uni, "World Bank API": wb,
            "CafeF trang chủ đề mã": cafef, "RSS VnExpress": rss, "DNSE": dnse}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(t, n, f) for n, f in jobs.items()]
        wait(futs, timeout=15)
    return jsonable({"tested_at": now_str(), "results": tests})


def label_fields() -> dict:
    return FIELD_LABELS_VI
