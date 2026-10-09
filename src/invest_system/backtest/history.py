"""Diem co hoi TAI THOI DIEM t - chay LAI dung web/service.analysis() voi du lieu point-in-time.

Khong viet lai logic cham diem: moi dau vao cua service.analysis() duoc thay bang
ban "nhu tai ngay t" (cung cach scripts/build_opportunities.py thay nguon gia
live bang ban chup):

  price_frame      -> gia <= t (ban chup Vietcap, da dieu chinh)
  _vnindex_live    -> VN-Index <= t
  _uni / _row      -> universe tai t: gia, GTGD TB20, hieu suat tinh den t;
                      chi so BCTC tu ky NAM da cong bo tai t (backtest/pit.py)
  financials_std   -> BCTC nam chi gom cac nam da cong bo tai t
  analyze_macro    -> giu tinh toan nhung sector_score = None: vi mo khong co
                      lich su theo ngay cong bo (docs/phase2/backtest-design.md muc 5)
  with_news=False  -> khong co kho tin lich su

Gioi han (ghi trong bao cao): so CP dung so HIEN TAI (von hoa qua khu = gia dieu
chinh x so CP nay); nganh ICB, san niem yet la hien tai; lai suat phi rui ro lay
so hien tai trong config/macro_vn.csv.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import numpy as np
import pandas as pd

from ..analysis.ttm import compute_ttm
from ..data import arminer_bctc
from ..data.fundamentals import StandardFinancials, _fill_derived
from ..logging_conf import get_logger
from . import pit

log = get_logger(__name__)

MIN_LIQUID_VALUE = 1e9          # = scripts/build_market_universe.py: "du thanh khoan" cho peers
MIN_OPPORTUNITY_VALUE = 5e9     # = scripts/build_opportunities.py: dieu kien /co-hoi
MIN_SESSIONS = 120
STATIC_COLS = ["symbol", "exchange", "icb1", "icb2", "icb3", "icb4", "icb4_code", "com_type_code",
               "company_type", "name", "brand", "website", "industry_source", "shares", "shares_source"]


# ------------------------------------------------------------------ gia theo ngay
def price_panel(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Chi so gia cho MOI (ma, phien), chi dung du lieu <= phien do (rolling/shift ve qua khu)."""
    frame = ohlcv.sort_values(["symbol", "time"]).reset_index(drop=True)
    g = frame.groupby("symbol", sort=False)
    close = frame["close"].astype(float)
    out = frame[["symbol", "time"]].copy()
    out["price"] = close
    out["n_sessions"] = g.cumcount() + 1
    for name, n in (("change_1d", 1), ("ret_1m", 21), ("ret_3m", 63), ("ret_1y", 250)):
        prev = g["close"].shift(n).astype(float)
        out[name] = np.where(prev > 0, close / prev - 1, np.nan)
    value = close * frame["volume"].astype(float)
    out["avg_value_20d"] = value.groupby(frame["symbol"]).transform(lambda s: s.rolling(20, min_periods=1).mean())
    return out


def prices_as_of(panel: pd.DataFrame, as_of, stale_days: int = 30) -> pd.DataFrame:
    """Dong gia gan nhat <= as_of cua moi ma con giao dich trong `stale_days` ngay
    (nhu universe live: ma it giao dich van la peer). `traded_today`: co phien dung as_of."""
    cutoff = pd.Timestamp(as_of)
    last = panel[(panel["time"] <= cutoff) & (panel["time"] > cutoff - pd.Timedelta(days=stale_days))]
    last = last.groupby("symbol", sort=False).tail(1)
    return last.assign(traded_today=last["time"] == cutoff).rename(columns={"time": "as_of_price"})


# ------------------------------------------------------------------ BCTC nam theo ky
@lru_cache(maxsize=4096)
def _annual(symbol: str) -> StandardFinancials | None:
    return arminer_bctc.from_arminer(symbol)


def annual_metrics(std: StandardFinancials) -> pd.DataFrame:
    """Chi so universe cho MOI nam - cung cong thuc scripts/build_market_universe.fin_metrics
    (ham do chi tinh nam moi nhat)."""
    f = std.frame
    ni = f["net_income_parent"] if "net_income_parent" in f else f.get("net_income")
    if ni is None or ni.dropna().empty:
        return pd.DataFrame()
    rows = []
    for year in ni.dropna().index:
        row = f.loc[year]
        eq_total, minority = row.get("equity"), row.get("minority_interest")
        eq_parent = eq_total - (minority if pd.notna(minority) else 0) if pd.notna(eq_total) else None
        prev_eq = None
        if year - 1 in f.index and pd.notna(f.loc[year - 1].get("equity")):
            pm = f.loc[year - 1].get("minority_interest")
            prev_eq = f.loc[year - 1, "equity"] - (pm if pd.notna(pm) else 0)
        avg_eq = (eq_parent + prev_eq) / 2 if eq_parent and prev_eq else eq_parent
        ni_y = float(ni.loc[year])
        ni_prev = float(ni.loc[year - 1]) if year - 1 in ni.index and pd.notna(ni.loc[year - 1]) else None
        debt = sum(v for v in (row.get("short_debt"), row.get("long_debt")) if pd.notna(v)) \
            if any(pd.notna(row.get(k)) for k in ("short_debt", "long_debt")) else None
        rev = row.get("revenue")
        rows.append({
            "fin_year": int(year), "as_of_fin": f"FY{int(year)}",
            "available_from": pit.rule_available_from(int(year)),
            "net_income_parent": ni_y, "equity_parent": eq_parent,
            "total_assets": row.get("total_assets"), "revenue": rev,
            "charter_capital": row.get("charter_capital"), "eps_reported": row.get("eps_reported"),
            "roe": ni_y / avg_eq if avg_eq and avg_eq > 0 else None,
            "net_margin": ni_y / rev if pd.notna(rev) and rev and rev > 0 else None,
            "ni_growth": (ni_y / ni_prev - 1) if ni_prev and ni_prev > 0 else None,
            "ebitda": row.get("ebitda") if pd.notna(row.get("ebitda")) and row.get("ebitda") else None,
            "net_debt": (debt or 0) - sum(v for v in (row.get("cash"), row.get("short_investments")) if pd.notna(v)),
            "debt_to_equity": debt / eq_parent if debt is not None and eq_parent and eq_parent > 0 else None,
        })
    return pd.DataFrame(rows)


def ttm_history(quarterly: pd.DataFrame) -> pd.DataFrame:
    """LNST cong ty me TTM tai MOI quy co du 4 quy lien tiep (analysis/ttm.compute_ttm),
    dung duoc tu ngay sau khi quy MUON nhat trong 4 quy cong bo (published_at + 1;
    thieu ngay that -> quy tac tre chuan cua backtest/pit.py)."""
    if quarterly is None or quarterly.empty:
        return pd.DataFrame(columns=["symbol", "available_from", "ni_ttm", "ttm_label", "ttm_periods"])
    rows = []
    for sym, g in quarterly.groupby("symbol", sort=False):
        g = g.sort_values(["year", "quarter"])
        if "net_income_parent" not in g.columns or g["net_income_parent"].isna().all():
            continue
        for k in range(3, len(g)):
            end = g.iloc[k]
            res = compute_ttm(g.iloc[: k + 1], end=(int(end["year"]), int(end["quarter"])))
            ni = res.get("net_income_parent")
            if not res.ok or ni is None:
                continue
            window = g[(g["year"] * 4 + g["quarter"]).between(
                (end["year"] * 4 + end["quarter"]) - 3, end["year"] * 4 + end["quarter"])]
            dates = [pit.available_from(int(r.year), int(r.quarter), r.published_at)[0]
                     for r in window.itertuples()]
            rows.append({"symbol": sym, "available_from": max(dates), "ni_ttm": ni, "ttm_label": res.label,
                         "ttm_periods": ",".join(res.periods)})
    return pd.DataFrame(rows)


def financials_as_of(symbol: str, as_of, years: int = 10) -> StandardFinancials:
    std = _annual(symbol)
    if std is None or std.empty:
        return StandardFinancials(symbol.upper(), pd.DataFrame(), "—", notes=["Chưa có BCTC năm"])
    cutoff = pd.Timestamp(as_of)
    keep = [y for y in std.frame.index if pit.rule_available_from(int(y)) <= cutoff]
    if not keep:
        return StandardFinancials(symbol.upper(), pd.DataFrame(), std.source,
                                  notes=[f"Chưa có BCTC năm nào công bố tại {cutoff:%d/%m/%Y}"])
    frame = std.frame.loc[keep].tail(years).copy()
    out = dataclasses.replace(std, frame=frame, mapping=dict(std.mapping), notes=list(std.notes),
                              ratios_history=pd.DataFrame())   # ratios cua nguon: khong biet ngay cong bo
    _fill_derived(out)
    return out


# ------------------------------------------------------------------ boi canh lich su
class History:
    """Du lieu da chuan bi de dung universe va cham diem tai nhieu ngay."""

    def __init__(self, base_universe: pd.DataFrame, ohlcv: pd.DataFrame, vnindex: pd.DataFrame,
                 symbols_with_annual: list[str] | None = None, quarterly: pd.DataFrame | None = None):
        self.base = base_universe[[c for c in STATIC_COLS if c in base_universe.columns]].copy()
        self.ohlcv = ohlcv.sort_values(["symbol", "time"]).reset_index(drop=True)
        self._by_symbol = {s: g.reset_index(drop=True) for s, g in self.ohlcv.groupby("symbol", sort=False)}
        self.vnindex = vnindex.sort_values("time").reset_index(drop=True)
        self.panel = price_panel(self.ohlcv)
        self.calendar = pd.DatetimeIndex(sorted(self.vnindex["time"].unique()))
        covered = set(arminer_bctc.coverage()["ticker"].astype(str))
        wanted = symbols_with_annual if symbols_with_annual is not None else self.base["symbol"].tolist()
        parts = []
        for sym in wanted:
            if sym not in covered:
                continue
            std = _annual(sym)
            metrics = annual_metrics(std) if std is not None and not std.empty else pd.DataFrame()
            if not metrics.empty:
                parts.append(metrics.assign(symbol=sym))
        self.fin = (pd.concat(parts, ignore_index=True).sort_values("available_from")
                    if parts else pd.DataFrame(columns=["symbol", "available_from"]))
        self.ttm = ttm_history(quarterly).sort_values("available_from") if quarterly is not None             else ttm_history(None)

    def universe_as_of(self, as_of) -> pd.DataFrame:
        cutoff = pd.Timestamp(as_of)
        prices = prices_as_of(self.panel, cutoff)
        fin = self.fin[self.fin["available_from"] <= cutoff].groupby("symbol").tail(1)
        ttm = self.ttm[self.ttm["available_from"] <= cutoff].groupby("symbol").tail(1)
        uni = (self.base.merge(prices, on="symbol", how="inner")
                        .merge(fin.drop(columns=["available_from"]), on="symbol", how="left")
                        .merge(ttm.drop(columns=["available_from"]), on="symbol", how="left"))
        uni["market_cap"] = uni["price"] * uni["shares"]
        ni = uni["net_income_parent"]
        uni["pe"] = np.where(ni > 0, uni["market_cap"] / ni, np.nan)
        uni["pb"] = np.where(uni["equity_parent"] > 0, uni["market_cap"] / uni["equity_parent"], np.nan)
        ev = uni["market_cap"] + uni["net_debt"].fillna(0)
        uni["ev_ebitda"] = np.where((uni["ebitda"] > 0) & (uni["company_type"] == "NON_FINANCIAL"),
                                    ev / uni["ebitda"], np.nan)
        uni["eps"] = np.where(uni["shares"] > 0, ni / uni["shares"], np.nan)
        uni["pe_ttm"] = np.where(uni["ni_ttm"] > 0, uni["market_cap"] / uni["ni_ttm"], np.nan)
        uni["eps_ttm"] = np.where(uni["shares"] > 0, uni["ni_ttm"] / uni["shares"], np.nan)
        uni["liquidity_flag"] = uni["avg_value_20d"] >= MIN_LIQUID_VALUE
        uni["has_bctc"] = uni["fin_year"].notna()
        uni["ret_ytd"] = np.nan
        uni["as_of_price"] = pd.to_datetime(uni["as_of_price"]).dt.strftime("%Y-%m-%d")
        return uni.sort_values("market_cap", ascending=False, na_position="last").reset_index(drop=True)

    def eligible_universe(self, uni: pd.DataFrame) -> pd.DataFrame:
        """Muc 4 thiet ke: >= 120 phien, GTGD TB20 >= 5 ty, co BCTC tai t, co giao dich phien t."""
        return uni[(uni["n_sessions"] >= MIN_SESSIONS) & (uni["avg_value_20d"] >= MIN_OPPORTUNITY_VALUE)
                   & uni["has_bctc"] & uni["traded_today"]].reset_index(drop=True)

    def prices_until(self, symbol: str, as_of, days: int) -> pd.DataFrame:
        frame = self._by_symbol.get(symbol.upper())
        if frame is None:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        return frame[frame["time"] <= pd.Timestamp(as_of)].tail(days)[["time", "open", "high", "low", "close", "volume"]]

    @contextmanager
    def patched_service(self, as_of, uni: pd.DataFrame) -> Iterator[object]:
        from ..web import service

        cutoff = pd.Timestamp(as_of)
        vni = self.vnindex[self.vnindex["time"] <= cutoff]
        real_macro = service.analyze_macro
        saved = {name: getattr(service, name) for name in
                 ("price_frame", "_vnindex_live", "_uni", "financials_std", "analyze_macro")}
        meta = {"built_at": f"{cutoff:%Y-%m-%d} (backtest point-in-time)"}
        service.price_frame = lambda s, days=750: (self.prices_until(s, cutoff, days),
                                                   service.prov("backtest: giá ≤ t", cutoff))
        service._vnindex_live = lambda days=400: (vni.tail(days), service.prov("backtest: VN-Index ≤ t", cutoff))
        service._uni = lambda: (uni, meta)
        service.financials_std = lambda s, years=10: financials_as_of(s, cutoff, years)
        service.analyze_macro = lambda md, ct: dataclasses.replace(real_macro(md, ct), sector_score=None)
        try:
            yield service
        finally:
            for name, value in saved.items():
                setattr(service, name, value)

    def score(self, as_of, symbols: list[str] | None = None) -> pd.DataFrame:
        """Diem va dieu kien /co-hoi cua cac ma (mac dinh: universe du dieu kien muc 4) tai `as_of`."""
        uni = self.universe_as_of(as_of)
        targets = symbols if symbols is not None else self.eligible_universe(uni)["symbol"].tolist()
        rows = []
        with self.patched_service(as_of, uni) as service:
            for sym in targets:
                try:
                    rows.append(record(service.analysis(sym, with_news=False)))
                except Exception as exc:  # noqa: BLE001 - mot ma loi khong lam hong ca ngay
                    rows.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"[:200]})
        out = pd.DataFrame(rows)
        if out.empty:
            return out
        out.insert(0, "as_of", pd.Timestamp(as_of))
        statics = uni.set_index("symbol")[["icb1", "market_cap", "avg_value_20d", "company_type"]]
        return out.drop(columns=[c for c in statics.columns if c in out.columns]).join(statics, on="symbol")


def record(result: dict) -> dict:
    """Ban ghi /co-hoi tu ket qua service.analysis() - cung truong voi scripts/build_opportunities._record."""
    val, rec = result["valuation"], result["recommendation"]
    row = {
        "symbol": result["symbol"], "price": result.get("price"),
        "upside": val.get("upside"), "confidence": val.get("confidence"),
        "rating": rec.get("rating"), "score": rec.get("total_score"),
        "quality_failures": [c.get("name") for c in result.get("checks", []) if c.get("status") == "FAIL"],
        "has_bctc": result.get("bctc_available"),
    }
    for group, value in (rec.get("scores") or {}).items():
        row[f"score_{group}"] = value
    row["eligible"] = is_eligible(row, result.get("metrics", {}).get("avg_value_20d"))
    return row


def is_eligible(row: dict, avg_value_20d) -> bool:
    """Dieu kien bang co hoi - giong het scripts/build_opportunities.build()."""
    upside, score = row.get("upside"), row.get("score")
    return bool(
        row.get("has_bctc") and not row.get("quality_failures")
        and row.get("confidence") in {"CAO", "TRUNG BÌNH"}
        and isinstance(avg_value_20d, (int, float)) and avg_value_20d >= MIN_OPPORTUNITY_VALUE
        and row.get("rating") == "MUA" and isinstance(upside, (int, float))
        and 0 < upside <= 1.5 and isinstance(score, (int, float))
    )
