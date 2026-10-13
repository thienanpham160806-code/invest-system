"""Vi mo quoc te tu FRED (Federal Reserve Bank of St. Louis).

API chinh thuc: https://api.stlouisfed.org/fred/series/observations, can key
mien phi trong bien moi truong FRED_API_KEY (dang ky tai
https://fredaccount.stlouisfed.org/apikeys). Khong co key thi doc file CSV
cong khai fredgraph.csv cua cung trang (cung so lieu, ghi ro nguon khac).

Cache 1 ngay qua data/cache.py (parquet + cache_meta). Loi mang ma con cache
cu thi tra cache cu va danh dau `stale` - khong bao gio bia so.

Ma chuoi da kiem tra tren fred.stlouisfed.org ngay 09/10/2026:

  FEDFUNDS      Federal Funds Effective Rate, %, thang
  DFF           Federal Funds Effective Rate, %, ngay
  DGS10         Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, %, ngay
  DTWEXBGS      Nominal Broad U.S. Dollar Index, Jan 2006 = 100, ngay
  DCOILBRENTEU  Crude Oil Prices: Brent - Europe, USD/thung, ngay
  VIXCLS        CBOE Volatility Index: VIX, diem, ngay

FRED KHONG co DXY (chi so cua ICE, 6 dong tien, ~58% EUR). DTWEXBGS la chi so
USD rong theo trong so thuong mai cua Fed (26 dong tien, co CNY, MXN, VND...)
nen dung thay; hai chi so cung chieu nhung KHAC muc va bien do. Chuoi cu
DTWEXM (major currencies) da ngung tu 01/2020.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass

import pandas as pd
import requests

from ..logging_conf import get_logger
from . import cache

log = get_logger(__name__)

API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES_URL = "https://fred.stlouisfed.org/series/{id}"
DEFAULT_START = "2000-01-01"
CACHE_MAX_AGE = 86_400  # 1 ngay
_KEY_PARAM = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    label: str
    unit: str
    frequency: str        # "D" ngay, "M" thang
    note: str = ""

    @property
    def url(self) -> str:
        return SERIES_URL.format(id=self.series_id)


SERIES: dict[str, FredSeries] = {
    "fed_funds": FredSeries("FEDFUNDS", "Lãi suất Fed Funds hiệu dụng (bình quân tháng)", "%", "M"),
    "fed_funds_daily": FredSeries("DFF", "Lãi suất Fed Funds hiệu dụng (ngày)", "%", "D"),
    "ust_10y": FredSeries("DGS10", "Lợi suất trái phiếu Chính phủ Mỹ 10 năm", "%", "D"),
    "usd_broad": FredSeries(
        "DTWEXBGS", "Chỉ số USD rộng (Fed, thay DXY)", "điểm (01/2006 = 100)", "D",
        note="FRED không có DXY; DTWEXBGS là chỉ số USD theo trọng số thương mại của Fed, "
             "cùng chiều nhưng khác mức với DXY."),
    "brent": FredSeries("DCOILBRENTEU", "Giá dầu Brent", "USD/thùng", "D"),
    "vix": FredSeries("VIXCLS", "Chỉ số biến động VIX", "điểm", "D"),
}


class FredError(RuntimeError):
    pass


@dataclass
class FredResult:
    key: str
    series: FredSeries
    values: pd.Series        # DatetimeIndex -> float, tang dan, da bo ngay thieu so
    source: str              # "FRED API" | "FRED CSV" | "... (cache)"
    stale: bool = False      # True: goi mang loi, dang dung cache qua han

    @property
    def last_date(self) -> pd.Timestamp | None:
        return None if self.values.empty else self.values.index[-1]


def _to_series(frame: pd.DataFrame) -> pd.Series:
    values = pd.to_numeric(frame["value"], errors="coerce")  # FRED ghi "." cho ngay thieu
    series = pd.Series(values.to_numpy(), index=pd.to_datetime(frame["date"]), dtype=float)
    return series.dropna().sort_index()


class FredClient:
    def __init__(self, api_key: str | None = None, session: requests.Session | None = None,
                 max_age: float = CACHE_MAX_AGE, timeout: float = 20):
        self.api_key = os.getenv("FRED_API_KEY", "") if api_key is None else api_key
        self.session = session or requests.Session()
        self.max_age = max_age
        self.timeout = timeout
        self._cache_ready = False

    # ------------------------------------------------------------ cache
    def _cache_key(self, series_id: str) -> str:
        return f"macro/fred/{series_id}"

    def _read_cache(self, series_id: str, max_age: float | None) -> pd.DataFrame | None:
        try:
            if not self._cache_ready:
                cache.init_db()
                self._cache_ready = True
            frame = cache.read_frame(self._cache_key(series_id), max_age=max_age)
        except Exception as exc:  # noqa: BLE001 - cache hong/khong ghi duoc khong lam hong vi mo
            log.info("FRED cache %s không đọc được: %s", series_id, exc)
            return None
        return frame if frame is not None and not frame.empty else None

    def _write_cache(self, series_id: str, frame: pd.DataFrame) -> None:
        try:
            cache.write_frame(self._cache_key(series_id), frame)
        except Exception as exc:  # noqa: BLE001
            log.info("FRED cache %s không ghi được: %s", series_id, exc)

    # ------------------------------------------------------------ mang
    def _fetch_api(self, series_id: str) -> pd.DataFrame:
        resp = self.session.get(API_URL, timeout=self.timeout, params={
            "series_id": series_id, "api_key": self.api_key, "file_type": "json",
            "observation_start": DEFAULT_START,
        })
        resp.raise_for_status()
        payload = resp.json()
        if "observations" not in payload:
            raise FredError(f"FRED {series_id}: phản hồi không có observations "
                            f"({payload.get('error_message', '')})")
        return pd.DataFrame([{"date": o["date"], "value": o["value"]}
                             for o in payload["observations"]], columns=["date", "value"])

    def _fetch_csv(self, series_id: str) -> pd.DataFrame:
        resp = self.session.get(CSV_URL, timeout=self.timeout,
                                params={"id": series_id, "cosd": DEFAULT_START})
        resp.raise_for_status()
        text = resp.text
        if not text.lstrip().lower().startswith(("observation_date", "date")):
            raise FredError(f"FRED {series_id}: CSV không hợp lệ (mã chuỗi sai?)")
        raw = pd.read_csv(io.StringIO(text), dtype=str)
        return raw.set_axis(["date", "value"], axis=1)

    # ------------------------------------------------------------ cong khai
    def get(self, key: str) -> FredResult:
        """Chuoi `key` trong SERIES (vd "ust_10y")."""
        if key not in SERIES:
            raise KeyError(f"chuỗi FRED không có trong danh mục: {key}")
        spec = SERIES[key]
        sid = spec.series_id
        fresh = self._read_cache(sid, self.max_age)
        if fresh is not None:
            return FredResult(key, spec, _to_series(fresh), "FRED (cache)")
        source = "FRED API" if self.api_key else "FRED CSV"
        try:
            frame = self._fetch_api(sid) if self.api_key else self._fetch_csv(sid)
        except Exception as exc:  # noqa: BLE001
            reason = self._safe_error(exc)
            stale = self._read_cache(sid, None)
            if stale is not None:
                log.warning("FRED %s lỗi (%s) - dùng cache cũ", sid, reason)
                return FredResult(key, spec, _to_series(stale), f"{source} (cache cũ)", stale=True)
            # `from None`: exception goc (requests) chua URL co api_key - khong de no
            # di theo traceback vao log may chu.
            raise FredError(f"FRED {sid}: {reason}") from None
        frame = frame.astype({"date": str, "value": str})
        if _to_series(frame).empty:
            raise FredError(f"FRED {sid}: không có quan sát nào")
        self._write_cache(sid, frame)
        return FredResult(key, spec, _to_series(frame), source)

    def get_all(self, keys: list[str] | None = None) -> tuple[dict[str, FredResult], dict[str, str]]:
        """(ket qua, loi) cho nhieu chuoi; mot chuoi loi khong lam hong cac chuoi khac."""
        results, errors = {}, {}
        for key in keys or list(SERIES):
            try:
                results[key] = self.get(key)
            except Exception as exc:  # noqa: BLE001
                errors[key] = self._redact(str(exc))
        return results, errors

    # ------------------------------------------------------------ an toan key
    def _redact(self, text: str) -> str:
        text = _KEY_PARAM.sub(r"\1***", text)
        if len(self.api_key) >= 8:  # key ngan bat thuong: khong thay chuoi con vo nghia
            text = text.replace(self.api_key, "***")
        return text

    def _safe_error(self, exc: Exception) -> str:
        """Mo ta loi KHONG chua key. HTTPError cua requests (va ConnectionError)
        in ca URL gom query `api_key=...` -> chi giu ma HTTP / ten loai loi."""
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return f"HTTP {exc.response.status_code}"
        if isinstance(exc, FredError):
            return self._redact(str(exc))
        return self._redact(f"{type(exc).__name__}: {exc}")
