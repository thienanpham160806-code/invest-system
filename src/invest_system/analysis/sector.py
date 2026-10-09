"""Phan tich nganh: so sanh voi cac ma cung nganh (peers) va hieu suat nganh.

- Bang peers: P/E, P/B, ROE, tang truong LN, von hoa, bien dong gia.
- Trung vi nganh (median) -> dau vao cho dinh gia tuong doi (analysis/valuation.py).
- Chi so nganh tu tinh: trung binh can bang cac ma trong nhom (equal-weight),
  so voi VN-Index -> nganh dang manh hay yeu hon thi truong.
- Vi the DN: phan vi (percentile) cua ROE/tang truong/dinh gia trong nhom.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data import prices
from ..data.company import CompanyInfo
from ..data.fundamentals import load_financials
from ..logging_conf import get_logger
from ..provenance import SourceLog
from .ratios import cagr, compute_ratios

log = get_logger(__name__)


@dataclass
class SectorResult:
    peers_table: pd.DataFrame = field(default_factory=pd.DataFrame)  # moi dong mot ma
    medians: dict = field(default_factory=dict)
    quantiles: dict = field(default_factory=dict)   # {"pe": (p25, p50, p75), ...}
    performance: dict = field(default_factory=dict) # {"sector_ret_3m":..., "bench_ret_3m":...}
    index_series: pd.DataFrame = field(default_factory=pd.DataFrame)  # time, sector, bench (=100)
    position: dict = field(default_factory=dict)    # percentile cua ma trong nhom
    score: float | None = None
    notes: list[str] = field(default_factory=list)


def _shares_for(symbol: str, info_shares: float | None, fin) -> float | None:
    if info_shares:
        return float(info_shares)
    hist = fin.ratios_history
    if not hist.empty and "eps" in hist.columns:
        eps = hist["eps"].dropna()
        nip = fin.get("net_income_parent")
        if not eps.empty and nip and eps.iloc[-1]:
            return float(nip / eps.iloc[-1])
    return None


def metrics_for(symbol: str, fin, ohlcv: pd.DataFrame, company_type: str,
                shares: float | None) -> dict:
    """Chi so dinh gia/hieu qua cua mot ma tai gia hien tai."""
    row: dict = {"symbol": symbol}
    price = float(ohlcv["close"].iloc[-1]) if ohlcv is not None and not ohlcv.empty else None
    row["price"] = price
    nip = fin.get("net_income_parent") if not fin.empty else None
    equity = fin.get("equity") if not fin.empty else None
    shares = _shares_for(symbol, shares, fin) if not fin.empty else shares
    row["shares"] = shares
    if price and shares:
        row["market_cap"] = price * shares
        if nip and nip > 0:
            row["pe"] = price * shares / nip
        if equity and equity > 0:
            row["pb"] = price * shares / equity
    if (row.get("pe") is None or row.get("pb") is None) and not fin.ratios_history.empty:
        last = fin.ratios_history.dropna(how="all").iloc[-1]
        row.setdefault("pe", last.get("pe"))
        row.setdefault("pb", last.get("pb"))
        row["multiples_source"] = "ratios của nguồn (năm gần nhất)"
    if company_type == "NON_FINANCIAL" and row.get("market_cap") and not fin.empty:
        debt = (fin.get("short_debt") or 0) + (fin.get("long_debt") or 0)
        cash = (fin.get("cash") or 0) + (fin.get("short_investments") or 0)
        pbt, interest = fin.get("pbt"), fin.get("interest_expense")
        dep = fin.get("depreciation")
        if pbt is not None and dep is not None:
            ebitda = pbt + abs(interest or 0) + abs(dep)
            if ebitda > 0:
                row["ev_ebitda"] = (row["market_cap"] + debt - cash) / ebitda
    ratios = compute_ratios(fin, company_type) if not fin.empty else pd.DataFrame()
    if not ratios.empty:
        last = ratios.iloc[-1]
        row["roe"] = last.get("roe")
        row["roa"] = last.get("roa")
        row["net_margin"] = last.get("net_margin")
        row["nim"] = last.get("nim")
    nip_s = fin.series("net_income_parent") if not fin.empty else pd.Series(dtype=float)
    row["ni_cagr"] = cagr(nip_s) if not nip_s.empty else None
    if ohlcv is not None and not ohlcv.empty:
        rs = prices.returns_summary(ohlcv)
        row["ret_3m"], row["ret_1y"] = rs.get("ret_3m"), rs.get("ret_1y")
    for k in ("pe", "pb", "ev_ebitda"):
        v = row.get(k)
        if v is not None and (not np.isfinite(v) or v <= 0 or v > 200):
            row[k] = None  # loai so vo nghia (LN am, VCSH am...) khoi trung vi
    return row


def _equal_weight_index(frames: dict[str, pd.DataFrame], start: pd.Timestamp) -> pd.Series:
    closes = []
    for sym, f in frames.items():
        if f is None or f.empty:
            continue
        s = f.set_index("time")["close"].astype(float)
        s = s[s.index >= start]
        if len(s) > 20:
            closes.append((s / s.iloc[0]).rename(sym))
    if not closes:
        return pd.Series(dtype=float)
    return pd.concat(closes, axis=1).ffill().mean(axis=1) * 100


def analyze_sector(info: CompanyInfo, target_metrics: dict, target_ohlcv: pd.DataFrame,
                   bench: pd.DataFrame, max_peers: int = 6,
                   log_: SourceLog | None = None) -> SectorResult:
    res = SectorResult()
    rows = [dict(target_metrics, is_target=True)]
    frames = {info.symbol: target_ohlcv}
    for peer in info.peers[:max_peers]:
        try:
            fin = load_financials(peer, years=5)
            ohlcv = prices.get_ohlcv(peer, 400)
            shares = None
            if info.is_demo:
                from ..data import demo

                shares = demo.overview(peer)["shares_outstanding"]
            m = metrics_for(peer, fin, ohlcv, info.company_type, shares)
            m["is_target"] = False
            rows.append(m)
            frames[peer] = ohlcv
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            log.info("peer %s loi: %s", peer, exc)
    table = pd.DataFrame(rows)
    res.peers_table = table
    peers_only = table[~table["is_target"]] if "is_target" in table else table
    if len(peers_only) == 0:
        res.notes.append("Không lấy được dữ liệu doanh nghiệp cùng ngành — định giá tương đối "
                         "chuyển sang so với lịch sử của chính doanh nghiệp.")
    if log_:
        log_.add("Nhóm so sánh cùng ngành", "Cùng nguồn giá/BCTC với mã phân tích",
                 note=", ".join(peers_only["symbol"].tolist()) or "không có")

    # Trung vi & phan vi tren TOAN NHOM (gom ca ma muc tieu) - chuan CTCK hay dung
    for k in ("pe", "pb", "ev_ebitda", "roe", "ni_cagr", "net_margin", "nim"):
        if k in table.columns:
            vals = pd.to_numeric(table[k], errors="coerce").dropna()
            if len(vals) >= 2:
                res.medians[k] = float(vals.median())
                res.quantiles[k] = tuple(float(vals.quantile(q)) for q in (0.25, 0.5, 0.75))
    # Vi the cua ma muc tieu
    for k in ("roe", "ni_cagr", "pe", "pb", "ret_1y"):
        if k in table.columns:
            vals = pd.to_numeric(table[k], errors="coerce")
            tv = vals.iloc[0]
            if pd.notna(tv) and vals.notna().sum() >= 3:
                res.position[k] = float((vals.dropna() <= tv).mean())

    # Hieu suat nganh vs thi truong
    if bench is not None and not bench.empty:
        start = bench["time"].iloc[-1] - pd.Timedelta(days=365)
        sector_idx = _equal_weight_index(frames, start)
        b = bench.set_index("time")["close"].astype(float)
        b = b[b.index >= start]
        if not sector_idx.empty and len(b) > 20:
            bench_idx = b / b.iloc[0] * 100
            idx = pd.concat({"sector": sector_idx, "bench": bench_idx}, axis=1).ffill().dropna()
            res.index_series = idx.reset_index().rename(columns={"index": "time"})
            for label, d in (("1m", 30), ("3m", 91), ("6m", 182), ("1y", 365)):
                cut = idx[idx.index <= idx.index[-1] - pd.Timedelta(days=d)]
                base = cut.iloc[-1] if not cut.empty else idx.iloc[0]
                res.performance[f"sector_ret_{label}"] = float(idx["sector"].iloc[-1] / base["sector"] - 1)
                res.performance[f"bench_ret_{label}"] = float(idx["bench"].iloc[-1] / base["bench"] - 1)
    res.score = _sector_score(res)
    return res


def _sector_score(res: SectorResult) -> float | None:
    """0-100: dong luc nganh so voi thi truong (3T & 6T) + hieu qua trung vi nganh."""
    perf = res.performance
    parts = []
    for label, w in (("3m", 0.5), ("6m", 0.5)):
        s, b = perf.get(f"sector_ret_{label}"), perf.get(f"bench_ret_{label}")
        if s is not None and b is not None:
            parts.append((50 + (s - b) * 250, w))   # vuot 10% -> 75 diem
    roe = res.medians.get("roe")
    if roe is not None:
        parts.append((40 + (roe - 0.12) * 300, 0.4))  # ROE trung vi 12% -> 40d, 20% -> 64d
    if not parts:
        return None
    total_w = sum(w for _, w in parts)
    return float(np.clip(sum(v * w for v, w in parts) / total_w, 0, 100))


# =====================================================================
# PHAN TICH NGANH THEO BANG TOAN THI TRUONG (universe, web/build_market_universe)
# Moi nut ICB 1-4 tong hop tu TAT CA ma trong nut (khong chi vai peers).
# =====================================================================
UNIVERSE_STATS = ("pe", "pb", "roe", "net_margin", "ni_growth")
_RET_COLS = ("ret_1m", "ret_3m", "ret_ytd", "ret_1y")


def _clean_multiples(frame: pd.DataFrame) -> pd.DataFrame:
    """Chi ma du thanh khoan; loai P/E <= 0 hoac > 100, P/B <= 0 hoac > 20."""
    f = frame[frame["liquidity_flag"].fillna(False).astype(bool)].copy()
    f.loc[~f["pe"].between(0, 100, inclusive="right"), "pe"] = np.nan
    f.loc[~f["pb"].between(0, 20, inclusive="right"), "pb"] = np.nan
    if "ev_ebitda" in f.columns:
        f.loc[~f["ev_ebitda"].between(0, 50, inclusive="right"), "ev_ebitda"] = np.nan
    return f


def _q(series: pd.Series) -> dict | None:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return None
    return {"p25": float(s.quantile(0.25)), "median": float(s.median()),
            "p75": float(s.quantile(0.75)), "n": int(len(s))}


def _cap_weighted(frame: pd.DataFrame, col: str) -> float | None:
    f = frame[[col, "market_cap"]].dropna()
    f = f[f["market_cap"] > 0]
    if f.empty:
        return None
    return float((f[col] * f["market_cap"]).sum() / f["market_cap"].sum())


def node_stats(members: pd.DataFrame, total_cap: float, bench: dict | None = None) -> dict:
    """Chi so tong hop cho mot nut nganh (members = tat ca ma trong nut)."""
    caps = members["market_cap"].dropna()
    cap = float(caps.sum()) if not caps.empty else 0.0
    liquid = _clean_multiples(members)
    ni = members.loc[members["market_cap"].notna(), "net_income_parent"]
    ni_pos_cap = members.loc[members["net_income_parent"].notna() & members["market_cap"].notna()]
    agg_pe = None
    if not ni_pos_cap.empty and ni_pos_cap["net_income_parent"].sum() > 0:
        agg_pe = float(ni_pos_cap["market_cap"].sum() / ni_pos_cap["net_income_parent"].sum())
    out = {
        "n_symbols": int(len(members)),
        "n_liquid": int(members["liquidity_flag"].fillna(False).astype(bool).sum()),
        "n_with_bctc": int(members["has_bctc"].fillna(False).astype(bool).sum()),
        "market_cap": cap, "market_weight": cap / total_cap if total_cap else None,
        "avg_value_20d": float(members["avg_value_20d"].sum(skipna=True)),
        "pe_aggregate": agg_pe,
        "top_symbols": members.sort_values("market_cap", ascending=False)["symbol"].head(5).tolist(),
    }
    del ni
    for col in _RET_COLS:
        out[col] = _cap_weighted(members, col)
        if bench and bench.get(col) is not None and out[col] is not None:
            out[f"{col}_vs_index"] = out[col] - bench[col]
    for col in UNIVERSE_STATS:
        out[col] = _q(liquid[col])
    return out


def sector_score_universe(stats: dict, macro_impact: float | None) -> dict:
    """Diem nganh 0-100 = dong luc gia (3T, 1N so VN-Index) 40% + ROE trung vi 30%
    + tac dong vi mo theo loai DN 30%. Thanh phan nao thieu thi chuan hoa lai trong so."""
    parts = []
    m3, m12 = stats.get("ret_3m_vs_index"), stats.get("ret_1y_vs_index")
    mom = [v for v in (m3, m12) if v is not None]
    if mom:
        parts.append(("momentum", float(np.clip(50 + np.mean(mom) * 200, 0, 100)), 0.4))
    roe = (stats.get("roe") or {}).get("median")
    if roe is not None:
        parts.append(("roe", float(np.clip(50 + (roe - 0.12) * 400, 0, 100)), 0.3))
    if macro_impact is not None:
        parts.append(("macro", float(macro_impact), 0.3))
    if not parts:
        return {"score": None, "components": {}}
    tw = sum(w for *_, w in parts)
    return {"score": float(sum(v * w for _, v, w in parts) / tw),
            "components": {k: v for k, v, _ in parts}}


def peers_from_universe(universe: pd.DataFrame, symbol: str, min_liquid: int = 5) -> tuple[pd.DataFrame, int, str]:
    """Peers = TOAN BO ma cung ICB4; < min_liquid ma du thanh khoan thi lui ICB3, roi ICB2.
    Tra ve (bang peers gom ca ma muc tieu, cap ICB dang dung, ten nut)."""
    row = universe.loc[universe["symbol"] == symbol.upper()]
    if row.empty:
        return universe.iloc[0:0], 0, ""
    row = row.iloc[0]
    for lvl in (4, 3, 2, 1):
        name = row[f"icb{lvl}"]
        members = universe[universe[f"icb{lvl}"] == name]
        if members["liquidity_flag"].fillna(False).astype(bool).sum() >= min_liquid or lvl == 1:
            return members, lvl, str(name)
    return universe.iloc[0:0], 0, ""


def universe_quantiles(peers: pd.DataFrame) -> dict:
    """{"pe": (p25, p50, p75), ...} tren nhom peers (du thanh khoan, da loai ngoai lai)
    -> dau vao analysis/valuation.py (cung dinh dang SectorResult.quantiles)."""
    liquid = _clean_multiples(peers)
    out = {}
    for k in ("pe", "pb", "ev_ebitda", "roe", "net_margin", "ni_growth"):
        if k not in liquid.columns:
            continue
        s = pd.to_numeric(liquid[k], errors="coerce").dropna()
        if len(s) >= 3:
            out[k] = tuple(float(s.quantile(q)) for q in (0.25, 0.5, 0.75))
    return out


def valuation_comparison(peers: pd.DataFrame, symbol: str, target_market_cap: float | None) -> tuple[dict, dict]:
    """Return comparison multiples for liquid ICB peers and their selection audit.

    Prefer same-node peers with at least 10% of target capitalization. If too few
    exist, widen the cap threshold progressively, then use the ten largest peers.
    The target itself is excluded from peer aggregates.
    """
    all_liquid = peers[peers.get("liquidity_flag", False).fillna(False).astype(bool)].copy()
    all_liquid["market_cap"] = pd.to_numeric(all_liquid.get("market_cap"), errors="coerce")
    all_liquid = all_liquid[all_liquid["market_cap"] > 0].sort_values("market_cap", ascending=False)
    liquid = all_liquid[all_liquid["symbol"].astype(str).str.upper() != symbol.upper()]
    selected = pd.DataFrame()
    threshold_used = None
    if target_market_cap and target_market_cap > 0:
        for fraction in (0.10, 0.05, 0.01, 0.0):
            candidate = liquid[liquid["market_cap"] >= target_market_cap * fraction]
            if len(candidate) >= 2:
                selected, threshold_used = candidate.head(10), fraction
                break
    if selected.empty:
        selected = liquid.head(10)
        threshold_used = None

    out: dict[str, tuple[float, float, float]] = {}
    aggregates: dict[str, float | None] = {}
    for key, denominator in (("pe", "net_income_parent"), ("pb", "equity_parent")):
        if denominator not in selected:
            continue
        den = pd.to_numeric(selected[denominator], errors="coerce")
        if key == "pe" and "ni_ttm" in selected:
            ttm = pd.to_numeric(selected["ni_ttm"], errors="coerce")
            den = ttm.where(ttm > 0, den)
        cap = pd.to_numeric(selected["market_cap"], errors="coerce")
        valid = (den > 0) & (cap > 0)
        multiples = (cap[valid] / den[valid]).replace([np.inf, -np.inf], np.nan).dropna()
        if key == "pe":
            multiples = multiples[multiples < 60]
        else:
            multiples = multiples[multiples <= 20]
        if len(multiples) >= 2:
            out[key] = tuple(float(multiples.quantile(q)) for q in (0.25, 0.50, 0.75))
            if key == "pb":
                out["pb_p90"] = float(multiples.quantile(0.90))
        agg_valid = (den > 0) & (cap > 0)
        if key == "pe":
            # A gross P/E is not meaningful when loss-making peers dominate NI.
            agg_valid &= den.notna()
        if agg_valid.any() and den[agg_valid].sum() > 0:
            aggregates[key] = float(cap[agg_valid].sum() / den[agg_valid].sum())
        else:
            aggregates[key] = None

    cap_cut = float(all_liquid["market_cap"].quantile(0.90)) if len(all_liquid) else None
    is_top_decile = bool(target_market_cap and cap_cut and target_market_cap >= cap_cut)
    audit = {
        "peer_symbols": selected["symbol"].astype(str).tolist(),
        "peer_count": int(len(selected)),
        "liquid_peer_count": int(len(liquid)),
        "cap_threshold": threshold_used,
        "target_top_decile": is_top_decile,
        "gross_multiples": aggregates,
        "source": "trung vị nhóm so sánh thanh khoản; loại chính mã mục tiêu",
    }
    return out, audit


def position_in(peers: pd.DataFrame, symbol: str) -> dict:
    """Phan vi (0-1) cua ma trong TOAN nhom peers theo tung chi so."""
    out = {}
    me = peers.loc[peers["symbol"] == symbol.upper()]
    if me.empty:
        return out
    me = me.iloc[0]
    for k in ("pe", "pb", "roe", "net_margin", "ni_growth", "ret_1y", "market_cap"):
        vals = pd.to_numeric(peers[k], errors="coerce").dropna()
        v = me.get(k)
        if pd.notna(v) and len(vals) >= 3:
            out[k] = float((vals <= v).mean())
    return out
