"""Gia & giao dich: OHLCV cua mot ma, VN-Index, san niem yet.

Chuoi nguon cho OHLCV ngay:
  1. data/router.py (kho toan san local -> DNSE -> vnstock/Vietcap -> cache) -
     tai su dung nguyen ven tu du an bot-phan-tich.
  2. Endpoint CONG KHAI cua bang gia Vietcap (gap-chart) - KHONG can vnstock,
     KHONG can API key (data/vietcap.py:_fetch_ohlcv_one).
  3. Du lieu gia lap cho ma demo (data/demo.py).
"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd

from ..logging_conf import get_logger
from ..provenance import SourceLog
from . import demo

log = get_logger(__name__)

BENCHMARK = "VNINDEX"


def _public_ohlcv(symbol: str, days: int) -> pd.DataFrame:
    from .vietcap import _fetch_ohlcv_one

    count_back = int(days * 5 / 7) + 10
    frame = _fetch_ohlcv_one(symbol.upper(), count_back, int(time.time()))
    if frame is None or frame.empty:
        return pd.DataFrame()
    from .cleaner import clean_ohlcv

    return clean_ohlcv(frame, symbol)


def get_ohlcv(symbol: str, days: int = 730, log_: SourceLog | None = None) -> pd.DataFrame:
    """OHLCV ngay ~`days` ngay gan nhat, cot time/open/high/low/close/volume (gia: dong)."""
    symbol = symbol.upper()
    if demo.is_demo(symbol) or symbol in demo.DEMO_BENCHMARKS:
        frame = demo.ohlcv(symbol, days)
        if log_:
            log_.add(f"Giá OHLCV {symbol}", "DỮ LIỆU MẪU (giả lập)", frame["time"].iloc[-1])
        return frame

    end = date.today()
    start = end - timedelta(days=days)
    errors = []
    if symbol != BENCHMARK:
        try:
            from .router import get_router

            frame = get_router().ohlcv(symbol, start=start, end=end)
            if frame is not None and not frame.empty:
                if log_:
                    log_.add(f"Giá OHLCV {symbol}", "Data router (kho local/DNSE/Vietcap)",
                             frame["time"].iloc[-1], note=f"{len(frame)} phiên")
                return frame.reset_index(drop=True)
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            errors.append(f"router: {exc}")
    try:
        frame = _public_ohlcv(symbol, days)
        if not frame.empty:
            frame = frame[frame["time"] >= pd.Timestamp(start)].reset_index(drop=True)
            if log_:
                log_.add(f"Giá OHLCV {symbol}", "Vietcap public API (gap-chart)",
                         frame["time"].iloc[-1], note=f"{len(frame)} phiên")
            return frame
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        errors.append(f"vietcap public: {exc}")
    if log_:
        log_.fail(f"Giá OHLCV {symbol}", "; ".join(errors) or "không có dữ liệu")
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])


def get_benchmark(symbol: str, days: int = 730, log_: SourceLog | None = None) -> pd.DataFrame:
    """Chi so tham chieu: VN-Index (hoac chi so gia lap khi chay ma demo)."""
    bench = demo.benchmark_for(symbol) if demo.is_demo(symbol) else BENCHMARK
    return get_ohlcv(bench, days, log_)


def get_exchange(symbol: str) -> str | None:
    """San niem yet (HOSE/HNX/UPCOM)."""
    if demo.is_demo(symbol):
        return "HOSE"
    try:
        from . import market_store

        syms = market_store.load_symbols()
        if not syms.empty and "exchange" in syms.columns:
            hit = syms[syms["symbol"] == symbol.upper()]
            if not hit.empty:
                return str(hit["exchange"].iloc[0])
    except Exception:  # noqa: BLE001
        pass
    try:
        from .vietcap import fetch_all_symbols

        frame = fetch_all_symbols(["HOSE", "HNX", "UPCOM"])
        hit = frame[frame["symbol"] == symbol.upper()]
        if not hit.empty:
            return str(hit["exchange"].iloc[0])
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        log.debug("fetch_all_symbols loi: %s", exc)
    return None


def returns_summary(frame: pd.DataFrame) -> dict:
    """Bien dong gia 1T/3T/6T/1N, cao/thap 52 tuan, KLGD TB 20 phien."""
    if frame is None or frame.empty:
        return {}
    close = frame.set_index("time")["close"].astype(float)
    last_t = close.index[-1]
    out = {"close": float(close.iloc[-1]), "last_date": last_t}

    def ret(days: int):
        past = close[close.index <= last_t - pd.Timedelta(days=days)]
        return None if past.empty else float(close.iloc[-1] / past.iloc[-1] - 1)

    for label, d in (("1m", 30), ("3m", 91), ("6m", 182), ("1y", 365)):
        out[f"ret_{label}"] = ret(d)
    year = close[close.index > last_t - pd.Timedelta(days=365)]
    out["high_52w"] = float(year.max())
    out["low_52w"] = float(year.min())
    vol = frame["volume"].astype(float).tail(20)
    out["avg_volume_20d"] = float(vol.mean())
    out["avg_value_20d"] = float((frame["close"].astype(float).tail(20) * vol).mean())
    return out


def beta(stock: pd.DataFrame, bench: pd.DataFrame, weeks: int = 104) -> float | None:
    """Beta theo loi suat TUAN (giam nhieu so voi loi suat ngay) trong ~2 nam."""
    if stock is None or bench is None or stock.empty or bench.empty:
        return None
    s = stock.set_index("time")["close"].astype(float).resample("W-FRI").last().pct_change()
    b = bench.set_index("time")["close"].astype(float).resample("W-FRI").last().pct_change()
    both = pd.concat({"s": s, "b": b}, axis=1).dropna().tail(weeks)
    if len(both) < 26 or both["b"].var() == 0:
        return None
    return float(both["s"].cov(both["b"]) / both["b"].var())
