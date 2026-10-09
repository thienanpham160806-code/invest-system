"""DNSE OpenAPI data source using a small signed httpx client.

The signature, request fields, and endpoint paths follow DNSE's published
OpenAPI and official SDK implementation. A 5-second connect timeout and a
5-minute connection-failure circuit breaker keep a blocked server region from
stalling analysis; normal provider routing may then use its configured source.
"""
from __future__ import annotations

import json
import base64
import hashlib
import hmac
import threading
import time
from datetime import date, datetime, timezone
from urllib.parse import quote, urlencode
from uuid import uuid4

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from ..config import get_secrets
from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, PriceProvider, ProviderError

log = get_logger(__name__)

# Anh xa do phan giai noi bo -> gia tri `resolution` DNSE chap nhan (xem
# spec /price/ohlc: "1,3,5,15,30,1h,1D,1W").
RESOLUTION_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1H": "1h", "1D": "1D", "1W": "1W",
}
# marketId (endpoint /market/instruments) -> ten san dung trong he thong.
MARKET_ID_TO_EXCHANGE = {"STO": "HOSE", "STX": "HNX", "UPX": "UPCOM"}
EXCHANGE_TO_MARKET_ID = {v: k for k, v in MARKET_ID_TO_EXCHANGE.items()}
_INDEX_SYMBOLS = {"VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30"}
_INSTRUMENTS_PAGE_SIZE = 100

_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 30.0
_DOWN_COOLDOWN = 5 * 60  # seconds to skip DNSE after a connection failure

_down_lock = threading.Lock()
_down_until = 0.0  # time.monotonic(); > hien tai = dang ngat mach


class DnseUnreachable(ProviderError):
    """Khong ket noi duoc may chu DNSE (timeout/tu choi ket noi/DNS) - thu lai
    ngay cung vo ich, nen khong retry va router chuyen nguon ke tiep."""


class DnseRequestError(ProviderError):
    """Yeu cau khong the thanh cong du thu lai: DNSE tu choi (HTTP 4xx, vd
    "invalid symbol") hoac chua cau hinh khoa API - khong retry (ban cu thu 5
    lan: /kn ma sai mat ~40s, may chua co khoa DNSE cham hang chuc giay/ma)."""


def _is_connection_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                            httpx.NetworkError, httpx.PoolTimeout))


class _DnseRestClient:
    """Small signed HTTP client for the two DNSE market-data endpoints used here."""

    def __init__(self, api_key: str, api_secret: str, base_url: str, api_version: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.http = httpx.Client(timeout=httpx.Timeout(
            connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=5, pool=5,
        ))

    def _request(self, method: str, path: str, query: dict | None = None):
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        date_value = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        nonce = uuid4().hex
        # Matches DNSE's official SDK signing input: path (not query), Date,
        # then a fresh nonce on every request.
        signing = f"(request-target): {method.lower()} {path}\ndate: {date_value}\nnonce: {nonce}"
        digest = hmac.new(self.api_secret.encode("utf-8"), signing.encode("utf-8"), hashlib.sha256).digest()
        signature = quote(base64.b64encode(digest).decode("ascii"), safe="")
        headers = {
            "X-Api-Key": self.api_key,
            "X-Signature": (f'Signature keyId="{self.api_key}",algorithm="hmac-sha256",'
                            f'headers="(request-target) date",signature="{signature}",nonce="{nonce}"'),
            "Date": date_value,
            "version": self.api_version,
        }
        response = self.http.request(method, url, headers=headers)
        return response.status_code, response.text

    def get_ohlc(self, bar_type: str, query: dict):
        return self._request("GET", "/price/ohlc", {**query, "type": bar_type})

    def get_instruments(self, *, market_id=None, limit=None, page=None, symbol=None):
        query = {"marketId": market_id, "limit": limit, "page": page, "symbol": symbol}
        return self._request("GET", "/market/instruments", {k: v for k, v in query.items() if v is not None})


def _mark_down(exc: BaseException) -> None:
    global _down_until
    with _down_lock:
        _down_until = time.monotonic() + _DOWN_COOLDOWN
    log.warning(
        "Khong ket noi duoc DNSE (%s) - bo qua DNSE, dung nguon ke tiep trong %d phut",
        exc, _DOWN_COOLDOWN // 60,
    )


def _raise_if_down() -> None:
    remaining = _down_until - time.monotonic()
    if remaining > 0:
        raise DnseUnreachable(
            f"DNSE khong ket noi duoc, tam bo qua (thu lai sau {remaining / 60:.0f} phut)"
        )


def _to_epoch(value: date, end_of_day: bool = False) -> int:
    if end_of_day:
        dt = datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=timezone.utc)
    else:
        dt = datetime(value.year, value.month, value.day, 0, 0, 0, tzinfo=timezone.utc)
    return int(dt.timestamp())


def _market_type_of(symbol: str) -> str:
    """"STOCK" cho ma co phieu thuong, "INDEX" cho VNINDEX/VN30... (best-effort)."""
    return "INDEX" if symbol.upper() in _INDEX_SYMBOLS else "STOCK"


class DnseProvider(PriceProvider):
    """Gia, khop lenh va danh sach ma tu DNSE OpenAPI."""

    name = "dnse"

    def __init__(self) -> None:
        self._client = None  # khoi tao tre: chi tao khi that su goi mang

    # ------------------------------------------------------------------ client
    @property
    def client(self):
        if self._client is None:
            secrets = get_secrets()
            if not secrets.dnse_api_key or not secrets.dnse_api_secret:
                raise DnseRequestError(
                    "Thieu DNSE_API_KEY / DNSE_API_SECRET trong .env. "
                    "Dang ky ung dung tai https://developers.dnse.com.vn"
                )
            client = _DnseRestClient(
                api_key=secrets.dnse_api_key,
                api_secret=secrets.dnse_api_secret,
                base_url=secrets.dnse_base_url,
                api_version=secrets.dnse_api_version,
            )
            self._client = client
            log.info("Da khoi tao DNSE client (%s)", secrets.dnse_base_url)
        return self._client

    def _get(self, what: str, call):
        """Goi REST qua ngat mach: dang ngat thi bao loi ngay; loi ket noi thi
        bat ngat mach va nem DnseUnreachable (khong retry)."""
        _raise_if_down()
        try:
            status, body = call()
        except ProviderError:
            raise  # vd thieu khoa API (DnseRequestError): giu nguyen loai loi
        except Exception as exc:  # SDK nem nhieu loai loi khac nhau
            if _is_connection_error(exc):
                _mark_down(exc)
                raise DnseUnreachable(f"DNSE {what}: khong ket noi duoc may chu: {exc}") from exc
            raise ProviderError(f"DNSE {what} that bai: {exc}") from exc
        return self._parse_response(status, body, what)

    @staticmethod
    def _parse_response(status: int | None, body: str | None, what: str) -> dict:
        """Validate HTTP status and parse the raw JSON response body."""
        if status is not None and 400 <= status < 500 and status != 429:
            raise DnseRequestError(f"DNSE {what} tra ve HTTP {status}: {body}")
        if status is None or status >= 300:
            raise ProviderError(f"DNSE {what} tra ve HTTP {status}: {body}")
        try:
            return json.loads(body) if body else {}
        except (TypeError, ValueError) as exc:
            raise ProviderError(f"DNSE {what} tra ve JSON khong hop le: {exc}") from exc

    # ------------------------------------------------------------------- goi API
    @retry(
        # Loi ket noi khong thu lai: da cho du _CONNECT_TIMEOUT, thu tiep chi
        # lam lenh cua nguoi dung treo them.
        retry=retry_if_exception(
            lambda e: isinstance(e, ProviderError)
            and not isinstance(e, (DnseUnreachable, DnseRequestError))
        ),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=30),
        reraise=True,
    )
    def _call_ohlc(self, symbol: str, start: date, end: date, resolution: str) -> dict:
        return self._get(
            f"get_ohlc({symbol})",
            lambda: self.client.get_ohlc(
                _market_type_of(symbol),
                query={
                    "symbol": symbol.upper(),
                    "resolution": RESOLUTION_MAP.get(resolution, "1D"),
                    "from": _to_epoch(start, end_of_day=False),
                    "to": _to_epoch(end, end_of_day=True),
                },
            ),
        )

    def _call_instruments_page(self, market_id: str, page: int) -> dict:
        return self._get(
            "get_instruments",
            lambda: self.client.get_instruments(
                market_id=market_id, limit=_INSTRUMENTS_PAGE_SIZE, page=page
            ),
        )

    def probe_ohlc(self, symbol: str, days: int = 30) -> tuple[int | None, int, str | None]:
        """Goi thu GET /price/ohlc DUNG MOT LAN (khong thu lai) - cho
        scripts/diagnose.py. Tra (ma HTTP, so phien nhan duoc, loi hoac None)."""
        end = date.today()
        start = date.fromordinal(end.toordinal() - days)
        try:
            status, body = self.client.get_ohlc(
                _market_type_of(symbol),
                query={
                    "symbol": symbol.upper(), "resolution": "1D",
                    "from": _to_epoch(start), "to": _to_epoch(end),
                },
            )
            payload = self._parse_response(status, body, f"get_ohlc({symbol})")
        except Exception as exc:  # noqa: BLE001 - chan doan: bao loi, khong nem
            if _is_connection_error(exc):
                _mark_down(exc)
                return None, 0, (
                    f"không kết nối được máy chủ DNSE sau {_CONNECT_TIMEOUT:.0f}s "
                    "(thường do DNSE chặn IP ngoài Việt Nam, vd Render ở Singapore)"
                )
            return None, 0, f"{type(exc).__name__}: {exc}"
        return status, len(_normalise_ohlc(payload)), None

    # --------------------------------------------------------------- PriceProvider
    def ohlcv(
        self, symbol: str, start: date, end: date, resolution: str = "1D"
    ) -> pd.DataFrame:
        payload = self._call_ohlc(symbol, start, end, resolution)
        frame = _normalise_ohlc(payload)
        if frame.empty:
            raise ProviderError(f"DNSE tra ve rong cho {symbol}")
        frame["symbol"] = symbol.upper()
        return frame

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        if exchanges:
            wanted = [e.upper() for e in exchanges]
            market_ids = [EXCHANGE_TO_MARKET_ID[e] for e in wanted if e in EXCHANGE_TO_MARKET_ID]
        else:
            market_ids = list(MARKET_ID_TO_EXCHANGE)

        rows: list[dict] = []
        for market_id in market_ids:
            page = 1
            while True:
                payload = self._call_instruments_page(market_id, page)
                data = payload.get("data") or []
                rows.extend(data)
                total = payload.get("total", len(rows))
                if not data or page * _INSTRUMENTS_PAGE_SIZE >= total:
                    break
                page += 1

        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ProviderError("DNSE tra ve danh sach ma rong")

        frame["exchange"] = frame["marketId"].map(MARKET_ID_TO_EXCHANGE)
        frame["organ_name"] = frame.get("name", frame.get("shortName"))
        frame["symbol"] = frame["symbol"].astype(str).str.upper()
        return frame[["symbol", "exchange", "organ_name"]].reset_index(drop=True)

    def company_overview(self, symbol: str) -> dict:
        """Ho so tu /market/instruments: chi co full_name + listed_date thuc
        su co du lieu. Von dieu le/so CP luu hanh/mo ta KHONG co trong
        endpoint nay - khong bia, de trong."""
        try:
            payload = self._get(
                f"get_instruments({symbol})",
                lambda: self.client.get_instruments(symbol=symbol.upper()),
            )
        except ProviderError as exc:
            log.warning("company_overview(%s) that bai: %s", symbol, exc)
            return {}
        rows = payload.get("data") or []
        if not rows:
            return {}
        row = rows[0]
        return {
            "full_name": row.get("name") or row.get("shortName"),
            "listed_date": row.get("listedDate"),
        }


def _normalise_ohlc(payload: dict) -> pd.DataFrame:
    """DNSE tra ve {t,o,h,l,c,v,nextTime} (mang song song) cho GET /price/ohlc."""
    if not isinstance(payload, dict) or "t" not in payload:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(payload["t"], unit="s"),
            "open": payload.get("o"),
            "high": payload.get("h"),
            "low": payload.get("l"),
            "close": payload.get("c"),
            "volume": payload.get("v"),
        }
    )
    for col in OHLCV_COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[OHLCV_COLUMNS].dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
