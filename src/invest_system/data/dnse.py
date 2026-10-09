"""Nguon du lieu DNSE qua SDK chinh thuc.

`pip install openapi-sdk` (theo README cua DNSE) KHONG cai duoc - ten goi do
chi la vi du trong docs, KHONG phai ten that tren PyPI. Ten goi PyPI THAT su
la `dnse-sdk-openapi` (da xac nhan tren PyPI 22/09/2026 - xem requirements.txt),
cai binh thuong bang `pip install -r requirements.txt`, khong can vendor nua.
Import trong code van la `from dnse import DNSEClient` (khong doi ten module).

Cac chi tiet duoi day DA XAC NHAN truc tiep tu tai lieu API chinh thuc cua DNSE
(https://developers.dnse.com.vn) va tu doc source cua SDK (dnse/api/client.py):

  - Moi phuong thuc cua DNSEClient tra ve tuple (status_code, body_text),
    body_text la CHUOI JSON THO - phai tu json.loads(), SDK khong tu parse.
  - GET /price/ohlc: bat buoc symbol, resolution (1,3,5,15,30,1h,1D,1W), from,
    to (epoch giay). SDK: client.get_ohlc(bar_type, query={...}) - bar_type
    la LOAI THI TRUONG (STOCK/DERIVATIVE/INDEX), KHONG PHAI khung thoi gian;
    symbol/resolution/from/to nam trong `query`. Tra ve {t,o,h,l,c,v,nextTime}.
  - GET /market/instruments: tra ve {data: [...], total, page, pageSize}.
    Moi ban ghi co symbol, marketId (STO=HOSE, STX=HNX, UPX=UPCOM), name
    (ten day du), shortName, listedDate. KHONG co von dieu le / so CP luu
    hanh / mo ta hoat dong - de None, khong bia (xem company_overview()).

Repo con lai: https://github.com/dnse-tech/openapi-sdk . Tai lieu API:
https://developers.dnse.com.vn

KHONG KET NOI DUOC (vd Render dat o Singapore: connect timeout toi
openapi.dnse.com.vn, trong khi tu may ca nhan o VN goi binh thuong): SDK mac
dinh cho ket noi 30s va urllib3 tu thu lai 3 lan -> ~2 phut/lan goi, nhan
them 5 lan thu cua _call_ohlc thanh >10 phut treo cho MOI ma truoc khi router
chuyen sang Vietcap. Vi vay: cho ket noi toi da _CONNECT_TIMEOUT giay, loi
ket noi KHONG thu lai, va "ngat mach" _DOWN_COOLDOWN giay - trong thoi gian
do moi lan goi bao loi ngay de router dung nguon ke tiep.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timezone

import pandas as pd
import urllib3
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
_DOWN_COOLDOWN = 15 * 60  # giay bo qua DNSE sau mot lan khong ket noi duoc

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
    reason = exc.reason if isinstance(exc, urllib3.exceptions.MaxRetryError) else exc
    # NewConnectionError (tu choi ket noi, loi DNS) la lop con cua ConnectTimeoutError.
    return isinstance(reason, urllib3.exceptions.ConnectTimeoutError)


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
            try:
                from dnse import DNSEClient  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise ProviderError(
                    "Chua cai SDK cua DNSE. Chay: pip install -r requirements.txt "
                    "(goi PyPI: dnse-sdk-openapi)"
                ) from exc

            client = DNSEClient(
                api_key=secrets.dnse_api_key,
                api_secret=secrets.dnse_api_secret,
                base_url=secrets.dnse_base_url,
                api_version=secrets.dnse_api_version,
            )
            # SDK khong cho truyen timeout/retry: thay PoolManager noi bo (cung
            # tham so nhu SDK, chi doi timeout va bo thu lai khi loi ket noi).
            # Neu ban SDK sau doi ten thuoc tinh thi giu nguyen mac dinh cua SDK.
            if hasattr(client, "_http"):
                client._http = urllib3.PoolManager(
                    num_pools=10, maxsize=10, block=False,
                    timeout=urllib3.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT),
                    retries=urllib3.Retry(total=2, connect=0, read=0),
                    assert_hostname=False,
                )
            self._client = client
            log.info("Da khoi tao DNSE client (%s)", secrets.dnse_base_url)
        return self._client

    def _get(self, what: str, call):
        """Goi SDK qua ngat mach: dang ngat thi bao loi ngay; loi ket noi thi
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
        """Kiem tra status va json.loads() body_text - DNSEClient khong tu parse."""
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
