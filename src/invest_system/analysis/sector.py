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
