"""Nguon du lieu Vietcap (VCI), truy cap qua thu vien vnstock.

Ly do di qua vnstock thay vi goi thang endpoint cua Vietcap:
  1. Vietcap khong cong bo tai lieu API chinh thuc cho nha dau tu ca nhan,
     endpoint noi bo co the doi bat ky luc nao.
  2. vnstock da chuan hoa ten cot bao cao tai chinh giua cac nguon, do chinh la
     phan ton cong nhat neu tu lam.

Doi lai, vnstock co gioi han tan suat goi. Vi vay moi ket qua deu di qua cache.

LUU Y: lan dau dung phai chay register_user() cua vnstock mot lan, sau do
dat VNSTOCK_ACCEPT_TOS=1 trong .env.

vnstock la phu thuoc TUY CHON (`pip install ".[vnstock]"`): tu 25/09/2026 goi
nay bi PyPI cach ly nen `pip install -r requirements.txt` khong con keo no ve.
Moi cho import vnstock deu nam trong ham va bat loi -> thieu vnstock thi cac
phuong thuc can no nem ProviderError, router chuyen sang nguon khac / cache /
kho local (gia toan san qua endpoint cong khai ben duoi KHONG can vnstock).

DA XAC NHAN (kiem tra truc tiep tren vnstock 4.0.8, khong con la gia dinh):
  - `Market().equity` va `Fundamental().equity` la HAM, phai GOI voi symbol
    truoc (vd `market.equity(symbol="FPT")`) de lay ve doi tuong co cac
    phuong thuc thuc su (ohlcv/income_statement/...) - KHONG PHAI thuoc tinh
    long nhau nhu `market.equity.ohlcv(...)`.
  - `Reference().equity` la DOI TUONG (khong phai ham) - `list()`/
    `list_by_industry()` goi truc tiep duoc.
  - `income_statement`/`balance_sheet`/`cash_flow`/`ratios` tra ve dang
    "moi CHI TIEU la mot hang, moi KY la mot cot" (cot `item`, `item_id`,
    roi cac cot nam/quy). Phai xoay lai (_reshape_periods) thanh "moi KY la
    mot hang" de khop voi cach analysis/fintext.py va analysis/lookup.py
    doc du lieu (mot dong cho moi nam, tra cuu theo ten cot = item_id).
  - `ref.equity.list()` CHI co 2 cot (symbol, organ_name) - Vietcap khong
    tra ve san niem yet qua duong nay. `list_by_industry()` co `icb_name`
    voi 4 muc do chi tiet (icb_level 1-4); chon muc 4 (chi tiet nhat, vd
    "Moi gioi chung khoan" thay vi "Tai chinh") va doi ten cot thanh
    "industry" cho khop quy uoc chung cua he thong.
  - `ref.company(symbol=...).info()` co ho so day du: business_model (mo ta
    hoat dong), charter_capital, listing_date, outstanding_shares... - nguon
    that cho company_overview() (truoc day luon tra rong).
  - `ref.company(symbol=...).news()` (facade mac dinh source="kbs") CHI tra
    ve 1 tin moi nhat, khong loc duoc theo ngay. Nguon phong phu hon la
    module noi bo `vnstock.explorer.vci.company.Company(symbol=...).news()`
    (nguon VCI - CHINH Vietcap dang dung o day) - tra ve toi da 50 tin/cong
    bo thong tin gan nhat (da kiem chung thuc te: 44 tin cho FPT trong 180
    ngay), co cot `public_date` de tu loc theo khoang thoi gian. Day la cac
    cong bo thong tin CHINH THUC (nghi quyet HDQT, phat hanh co phieu, ket
    qua kinh doanh...), khong phai bao chi - phu hop de hien "cap nhat gan
    day" hon la "tin tuc" thong thuong.
"""
from __future__ import annotations

import importlib.util
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

from ..logging_conf import get_logger
from .base import OHLCV_COLUMNS, FundamentalProvider, PriceProvider, ProviderError

log = get_logger(__name__)

_VNSTOCK_MISSING = (
    "Chua cai vnstock (phu thuoc tuy chon - goi bi PyPI cach ly). "
    'Cai khi co the: pip install ".[vnstock]"'
)


def vnstock_available() -> bool:
    """Co cai vnstock khong (khong import - tranh tac dung phu cua vnai)."""
    return importlib.util.find_spec("vnstock") is not None

_INDUSTRY_LEVEL = 4  # 1=rong nhat (vd "Tai chinh") .. 4=chi tiet nhat


def _reshape_periods(frame: pd.DataFrame) -> pd.DataFrame:
    """Xoay bao cao tai chinh cua vnstock (chi tieu=hang, ky=cot) thanh
    (ky=hang, item_id=cot) - dang ma analysis/fintext.py va analysis/lookup.py
    gia dinh (mot dong moi nam, tra cuu chi so theo ten cot).
    """
    if frame is None or frame.empty or "item_id" not in frame.columns:
        return pd.DataFrame()

    period_cols = [c for c in frame.columns if c not in ("item", "item_id")]
    # Bo hang toan NaN (thuong la dong tieu de/section header khong co so
    # lieu, vd "TAI SAN"), roi giu 1 dong cho moi item_id neu bi trung
    # (uu tien dong xuat hien SAU - thuong la dong tong hop co gia tri that).
    body = frame.dropna(subset=period_cols, how="all")
    body = body.drop_duplicates(subset="item_id", keep="last")

    reshaped = body.set_index("item_id")[period_cols].T
    reshaped.index.name = "period"
    return reshaped.sort_index().reset_index()


_STATEMENT_PARTS = ("income", "balance", "cashflow")
# Ty le tang truong LN cong ty me (%/nam) trong bao cao "ratios" - nhan nam
# cua bao cao nay DUNG (da doi chieu P/E x EPS voi gia cuoi nam, va ROE/tang
# truong HPG 2023-2024 voi thuc te), nen dung lam "chuan" de kiem tra thu tu.
_RATIO_PROFIT_GROWTH = "profit_after_tax_for_shareholders_of_the_parent_company"


def _parent_profit_column(income: pd.DataFrame) -> str | None:
    for col in income.columns:
        if "attributable" in col or "parent" in col:
            return col
    return "net_profit" if "net_profit" in income.columns else None


def _growth_error(profit: pd.Series, expected: pd.Series) -> float | None:
    """Sai lech trung binh giua tang truong nam tinh tu `profit` va `expected`
    (ca hai danh chi muc theo nam, expected tinh bang %)."""
    growth = profit.astype(float).pct_change()
    both = pd.concat({"calc": growth, "exp": expected.astype(float) / 100}, axis=1).dropna()
    both = both[both["calc"].abs() < 10]  # bo nam loi nhuan doi dau/gan 0
    return None if both.empty else float((both["calc"] - both["exp"]).abs().mean())


def _reverse_years(frame: pd.DataFrame) -> pd.DataFrame:
    """Giu nguyen cot period (tang dan), dao thu tu cac hang so lieu."""
    values = frame.drop(columns="period").iloc[::-1].reset_index(drop=True)
    values.insert(0, "period", frame["period"].to_numpy())
    return values


def align_statement_years(bundle: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Sua loi cua vnstock 4.0.8 (nguon VCI): bao cao NAM income/balance/
    cashflow co nhan cot "2025, 2024, 2023, 2022" nhung so lieu lai xep theo
    thu tu 2022 -> 2025 (da kiem chung: LNST HPG thuc te 2022 = 8.444 ty nam
    duoi cot "2025"; tong 2 quy cuoi 2025 cua FPT khop cot "2022"). Khong sua
    thi /fin bao tang truong thanh suy giam va nguoc lai.

    KHONG dao cung: so tang truong LN cong ty me tinh tu bao cao ket qua kinh
    doanh voi tang truong trong bao cao "ratios" (nhan dung), chi dao khi thu
    tu dao khop ro rang hon. Vi vay ham nay idempotent (goi lai tren du lieu
    da sua khong dao nua) va tu het tac dung neu vnstock sua loi."""
    income, ratios = bundle.get("income"), bundle.get("ratios")
    if income is None or ratios is None or income.empty or ratios.empty:
        return bundle
    if "period" not in income.columns or _RATIO_PROFIT_GROWTH not in ratios.columns:
        return bundle
    profit_col = _parent_profit_column(income)
    if profit_col is None:
        return bundle
    expected = ratios.set_index("period")[_RATIO_PROFIT_GROWTH]
    as_is = _growth_error(income.set_index("period")[profit_col], expected)
    flipped = _growth_error(_reverse_years(income).set_index("period")[profit_col], expected)
    if as_is is None or flipped is None or not flipped < as_is * 0.5:
        return bundle
    log.info("Bao cao nam bi dao thu tu nam (loi vnstock) - da sap xep lai")
    fixed = dict(bundle)
    for part in _STATEMENT_PARTS:
        frame = bundle.get(part)
        if frame is not None and not frame.empty and "period" in frame.columns:
            fixed[part] = _reverse_years(frame)
    return fixed


class VietcapProvider(PriceProvider, FundamentalProvider):
    """Bao cao tai chinh, danh sach ma, nganh va gia du phong tu Vietcap/VCI."""

    name = "vietcap"

    def __init__(self) -> None:
        self._market = None
        self._reference = None
        self._fundamental = None

    # ------------------------------------------------------------------ lazy init
    def _modules(self):
        if self._market is None:
            try:
                from vnstock import Fundamental, Market, Reference  # type: ignore
            except ImportError as exc:
                raise ProviderError(_VNSTOCK_MISSING) from exc
            except (Exception, SystemExit) as exc:  # vnai co the sys.exit() ngay khi import
                raise ProviderError(f"Khong khoi tao duoc vnstock: {exc}") from exc
            self._market = Market()
            self._reference = Reference()
            self._fundamental = Fundamental()
            log.info("Da khoi tao vnstock (nguon Vietcap/VCI)")
        return self._market, self._reference, self._fundamental

    @staticmethod
    def _guard(fn, what: str):
        try:
            return fn()
        except SystemExit as exc:
            # QUAN TRONG: vnstock (qua vnai) goi thang sys.exit() khi cham
            # gioi han rate limit, thay vi nem mot exception binh thuong.
            # SystemExit ke thua tu BaseException nen "except Exception" o
            # duoi KHONG bat duoc - neu khong chan rieng o day, no se giet
            # chet toan bo tien trinh bot (xuyen qua ca middleware ErrorGuard
            # trong bot/main.py, vi ErrorGuard cung chi bat Exception).
            raise ProviderError(f"Vietcap/{what} bi chan (vnstock tu thoat): {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Vietcap/{what} that bai: {exc}") from exc

    # --------------------------------------------------------------- PriceProvider
    def ohlcv(
        self, symbol: str, start: date, end: date, resolution: str = "1D"
    ) -> pd.DataFrame:
        market, _, _ = self._modules()
        raw = self._guard(
            lambda: market.equity(symbol=symbol.upper()).ohlcv(
                start=start.isoformat(), end=end.isoformat(), interval=resolution
            ),
            f"ohlcv({symbol})",
        )
        frame = pd.DataFrame(raw)
        alias = {"time": "time", "date": "time", "tradingDate": "time"}
        frame = frame.rename(columns={k: v for k, v in alias.items() if k in frame.columns})
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
        for col in OHLCV_COLUMNS:
            if col not in frame.columns:
                frame[col] = pd.NA
        frame = frame[OHLCV_COLUMNS].dropna(subset=["time"]).sort_values("time")
        frame["symbol"] = symbol.upper()
        return frame.reset_index(drop=True)

    def listing(self, exchanges: list[str] | None = None) -> pd.DataFrame:
        _, reference, _ = self._modules()
        frame = pd.DataFrame(self._guard(lambda: reference.equity.list(), "listing"))
        if frame.empty:
            raise ProviderError("Vietcap tra ve danh sach ma rong")
        # LUU Y: nguon nay KHONG co cot san niem yet (chi symbol, organ_name).
        # Loc theo `exchanges` chi co tac dung khi nguon khac (DNSE) da dien
        # duoc cot "exchange" truoc do trong cung mot lan goi router.
        if exchanges and "exchange" in frame.columns:
            wanted = {e.upper() for e in exchanges}
            frame = frame[frame["exchange"].astype(str).str.upper().isin(wanted)]
        return frame.reset_index(drop=True)

    # ----------------------------------------------------------- FundamentalProvider
    def income_statement(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).income_statement(period=period),
            f"income_statement({symbol})",
        )
        return _reshape_periods(frame)

    def balance_sheet(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).balance_sheet(period=period),
            f"balance_sheet({symbol})",
        )
        return _reshape_periods(frame)

    def cash_flow(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).cash_flow(period=period),
            f"cash_flow({symbol})",
        )
        return _reshape_periods(frame)

    def ratios(self, symbol: str, period: str = "quarter") -> pd.DataFrame:
        _, _, fa = self._modules()
        frame = self._guard(
            lambda: fa.equity(symbol=symbol.upper()).ratios(period=period),
            f"ratios({symbol})",
        )
        return _reshape_periods(frame)

    def industry_map(self) -> pd.DataFrame:
        _, reference, _ = self._modules()
        frame = pd.DataFrame(
            self._guard(lambda: reference.equity.list_by_industry(), "industry_map")
        )
        if frame.empty or "icb_name" not in frame.columns:
            return frame
        frame = frame[frame.get("icb_level") == _INDUSTRY_LEVEL]
        frame = frame.rename(columns={"icb_name": "industry"})
        return frame[["symbol", "industry"]].reset_index(drop=True)

    def company_overview(self, symbol: str) -> dict:
        _, reference, _ = self._modules()
        frame = self._guard(
            lambda: reference.company(symbol=symbol.upper()).info(),
            f"company_overview({symbol})",
        )
        if frame is None or frame.empty:
            return {}
        row = frame.iloc[0]
        # LUU Y: "charter_capital" tu vnstock tinh bang TY DONG (vd FPT ra
        # 17413.0 nghia la 17,413 ty dong) - nhan 1e9 de quy ve VND, cho
        # cung don vi voi shares_outstanding*gia (xem analysis/lookup.py).
        charter_capital = _clean_float(row.get("charter_capital"))
        overview = {
            "listed_date": _clean_str(row.get("listing_date")),
            "charter_capital": charter_capital * 1e9 if charter_capital is not None else None,
            "shares_outstanding": _clean_float(row.get("outstanding_shares")),
            "description": _clean_str(row.get("business_model")),
        }
        return {k: v for k, v in overview.items() if v is not None}

    def company_news(self, symbol: str, days: int = 180) -> list[dict]:
        """Cong bo thong tin chinh thuc gan day, qua module VCI noi bo cua
        vnstock (xem ghi chu dau file). `Reference().company().news()` mac
        dinh (source="kbs") chi tra 1 tin nen KHONG dung o day.
        """
        try:
            from vnstock.explorer.vci.company import Company as VciCompany  # type: ignore
        except ImportError as exc:
            raise ProviderError(_VNSTOCK_MISSING) from exc
        except (Exception, SystemExit) as exc:
            raise ProviderError(f"Khong khoi tao duoc vnstock: {exc}") from exc

        frame = self._guard(
            lambda: VciCompany(symbol=symbol.upper()).news(), f"company_news({symbol})"
        )
        if frame is None or frame.empty or "public_date" not in frame.columns:
            return []

        cutoff = datetime.now() - timedelta(days=days)
        frame = frame.copy()
        frame["public_date"] = pd.to_datetime(frame["public_date"], errors="coerce")
        frame = frame[frame["public_date"] >= cutoff].sort_values("public_date", ascending=False)

        title_col = "news_title" if "news_title" in frame.columns else None
        if title_col is None:
            return []
        return [
            {"title": str(row[title_col]), "published_at": row["public_date"]}
            for _, row in frame.iterrows()
            if pd.notna(row[title_col])
        ]


def _clean_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _clean_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ===================================================================
# Tai TOAN SAN tu endpoint cong khai cua bang gia Vietcap (trading.vietcap.com.vn).
#
# Dung cho scripts/backfill_data.py de nap MOT KHO (data/market_store.py)
# thay vi goi vnstock tung ma mot qua VietcapProvider o tren (cham, de cham
# rate limit cua vnstock - xem docstring dau file). Day la endpoint CONG
# KHAI ma chinh trang bang gia tu goi khi mo trinh duyet, KHONG can dang
# nhap va KHONG dung token tai khoan chung khoan o day.
#
# DA KIEM CHUNG TRUC TIEP (22/09/2026, khong con la gia dinh tu script cu):
#   - Header toi thieu (chi User-Agent/Referer/Origin) bi endpoint tra ve
#     RONG ([]) du HTTP 200 - phai dung dung bo header ma chinh vnstock
#     dung cho nguon VCI (vnstock.core.utils.user_agent.get_headers), gom ca
#     cac header Sec-Fetch-*/Accept-Language/DNT... ma trinh duyet that gui.
#   - `POST .../chart/OHLCChart/gap-chart` CHI TRA DU LIEU KHI `symbols` co
#     DUNG 1 MA - gui nhieu ma trong cung 1 request tra ve RONG (khong bao
#     loi, HTTP van 200), KHAC voi gia dinh ban dau la gui duoc theo lo 20
#     ma. Vi vay fetch_ohlcv_bulk() duoi day chay SONG SONG CO GIOI HAN
#     (ThreadPoolExecutor) tren tung ma rieng, thay vi gop lo.
#   - `POST .../price/symbols/getList` (bang gia trong phien) THUC SU nhan
#     duoc nhieu ma/request (da thu 5 ma, ra du 5 ket qua) - endpoint nay
#     dung duoc theo lo nhu thiet ke ban dau.
#
# Endpoint KHONG co tai lieu chinh thuc va co the doi bat cu luc nao - bao
# boc trong try/except, khong dua vao duong ra quyet dinh chinh (chi dung
# de NAP KHO, phan quyet dinh khuyen nghi van di qua indicators/analysis
# nhu thuong voi du lieu da nap).
# ===================================================================

_PUBLIC_BASE = "https://trading.vietcap.com.vn/api"
_EXCHANGE_ALIAS = {"HSX": "HOSE", "HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM"}
_DEFAULT_CONCURRENCY = 8  # so request OHLCV chay dong thoi (moi ma 1 request rieng)


def _public_headers() -> dict[str, str]:
    """Bo header GIONG HET trinh duyet that ma vnstock dung cho nguon VCI.

    Header toi thieu (chi User-Agent/Referer/Origin) bi endpoint tra ve RONG
    - da kiem chung truc tiep (xem ghi chu dau khoi nay). Dung lai ham cua
    vnstock thay vi tu doan lai bo header, vi day la ban DA XAC NHAN chay dung.
    """
    try:
        from vnstock.core.utils.user_agent import get_headers  # type: ignore

        return get_headers(data_source="VCI")
    except (Exception, SystemExit):  # vnstock la tuy chon (hoac loi khi import vnai)
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
            "Referer": "https://trading.vietcap.com.vn/",
            "Origin": "https://trading.vietcap.com.vn",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }


_public_session = requests.Session()
_public_session.headers.update(_public_headers())


def _polite_sleep(base: float = 1.0) -> None:
    """Gian nhip 1-2 giay co nhieu ngau nhien, tranh goi dong loat."""
    time.sleep(base + random.uniform(0, base))


def _request_json_public(
    method: str, url: str, payload: dict | None = None, attempts: int = 5, delay: float = 1.0
):
    """Goi endpoint cong khai, lui theo cap so nhan khi gap 429/5xx hoac loi mang."""
    for attempt in range(1, attempts + 1):
        try:
            resp = _public_session.request(method, url, json=payload, timeout=30)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == attempts:
                raise ProviderError(
                    f"Endpoint cong khai Vietcap loi sau {attempts} lan thu: {exc}"
                ) from exc
            wait = delay * 2 ** (attempt - 1)
            log.warning(
                "goi %s loi (%s), thu lai sau %.0fs [%d/%d]", url, exc, wait, attempt, attempts
            )
            time.sleep(wait)


def probe_endpoint(
    method: str, path: str, payload: dict | None = None, timeout: float = 15
) -> tuple[int | None, Any, str | None]:
    """Goi thu endpoint cong khai DUNG MOT LAN (khong thu lai) - cho
    scripts/diagnose.py: can thay dung ma HTTP (vd 403 khi bi chan IP) thay
    vi bi che boi vong thu lai. Tra (ma HTTP, JSON hoac None, loi hoac None)."""
    url = f"{_PUBLIC_BASE}{path}"
    try:
        resp = _public_session.request(method, url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return None, None, f"{type(exc).__name__}: {exc}"
    try:
        return resp.status_code, resp.json(), None
    except ValueError:
        return resp.status_code, None, f"phan hoi khong phai JSON: {resp.text[:120]!r}"


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _fetch_in_batches(
    symbols: list[str],
    batch_size: int,
    fetch_one_batch: Callable[[list[str]], list],
    label: str,
    delay: float,
) -> list:
    """Chay theo lo; lo nao bi tu choi thi chia doi va thu lai, toi thieu 1 ma."""
    results: list = []
    queue = list(_chunks(symbols, batch_size))
    done = 0
    while queue:
        batch = queue.pop(0)
        try:
            results.extend(fetch_one_batch(batch))
            done += len(batch)
            log.info("[%s] %d/%d ma", label, done, len(symbols))
        except Exception as exc:
            if len(batch) == 1:
                log.warning("[%s] bo qua %s: %s", label, batch[0], exc)
                done += 1
            else:
                half = len(batch) // 2
                log.info("[%s] lo %d ma bi tu choi -> chia doi", label, len(batch))
                queue[:0] = [batch[:half], batch[half:]]
        _polite_sleep(delay)
    return results


def fetch_all_symbols(exchanges: list[str]) -> pd.DataFrame:
    """Danh sach TOAN BO ma co phieu (3 ky tu) tren cac san yeu cau, mot request duy nhat.

    `GET /price/symbols/getAll`. Cot tra ve: symbol, exchange.
    """
    raw = _request_json_public("GET", f"{_PUBLIC_BASE}/price/symbols/getAll")
    frame = pd.DataFrame(raw if isinstance(raw, list) else raw.get("data", []))
    if frame.empty:
        raise ProviderError("Endpoint getAll tra ve danh sach ma rong - co the da doi cau truc")

    exch_col = next((c for c in ("board", "exchange", "floor") if c in frame.columns), None)
    if exch_col:
        frame["exchange"] = frame[exch_col].astype(str).str.upper().map(_EXCHANGE_ALIAS)
        frame = frame[frame["exchange"].isin(exchanges)]

    type_col = next((c for c in ("type", "securityType", "stockType") if c in frame.columns), None)
    if type_col:
        frame = frame[frame[type_col].astype(str).str.upper().str.contains("STOCK")]

    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame = frame[frame["symbol"].str.fullmatch(r"[A-Z0-9]{3}")]  # chi ma co phieu 3 ky tu
    frame = frame.drop_duplicates("symbol").reset_index(drop=True)
    return frame[["symbol", "exchange"]] if "exchange" in frame.columns else frame


def fetch_price_board(
    symbols: list[str], batch_size: int = 100, delay: float = 1.0
) -> pd.DataFrame:
    """Anh chup gia trong phien cho danh sach ma, theo lo 100 ma/request.

    `POST /price/symbols/getList`, body {"symbols": [...]}. Dung cho gia
    hien tai/khoi luong trong phien (khac voi lich su OHLCV).
    """
    def one_batch(batch: list[str]) -> list[dict]:
        url = f"{_PUBLIC_BASE}/price/symbols/getList"
        raw = _request_json_public("POST", url, {"symbols": batch})
        return raw if isinstance(raw, list) else raw.get("data", [])

    rows = _fetch_in_batches(symbols, batch_size, one_batch, "price_board", delay)
    return pd.json_normalize(rows, sep=".")


def _fetch_ohlcv_one(symbol: str, count_back: int, to_ts: int) -> pd.DataFrame | None:
    payload = {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": to_ts, "countBack": count_back}
    raw = _request_json_public("POST", f"{_PUBLIC_BASE}/chart/OHLCChart/gap-chart", payload)
    items = raw if isinstance(raw, list) else raw.get("data", [])
    if not items or not items[0] or "t" not in items[0]:
        return None
    item = items[0]
    return pd.DataFrame(
        {
            "symbol": symbol,
            "time": pd.to_datetime(pd.Series(item["t"], dtype="int64"), unit="s"),
            "open": item.get("o"), "high": item.get("h"),
            "low": item.get("l"), "close": item.get("c"),
            "volume": item.get("v"),
        }
    )


def fetch_daily_bars(symbol: str, count_back: int = 30) -> pd.DataFrame:
    """Nen ngay GAN NHAT cua mot ma/chi so (vd VNINDEX), KE CA nen dang chay
    cua phien hom nay khi dang giao dich - gap-chart cap nhat trong phien, khac
    kho gia (chi cap nhat 11:35/15:05) va cache cua router (12 gio). Rong neu
    nguon khong tra ve."""
    frame = _fetch_ohlcv_one(symbol.upper(), count_back, int(time.time()))
    return frame if frame is not None else pd.DataFrame(columns=["symbol", *OHLCV_COLUMNS])


def fetch_ohlcv_bulk(
    symbols: list[str], count_back: int, to_ts: int | None = None,
    max_workers: int = _DEFAULT_CONCURRENCY, delay: float = 0.3,
    progress: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """Lich su OHLCV cho danh sach ma.

    `POST /chart/OHLCChart/gap-chart` CHI tra du lieu khi `symbols` co dung
    MOT ma (da kiem chung truc tiep - xem ghi chu dau khoi ham nay o file
    nay). Vi vay ham nay goi MOI MA MOT REQUEST RIENG, chay SONG SONG CO
    GIOI HAN bang ThreadPoolExecutor (`max_workers`, mac dinh xem
    _DEFAULT_CONCURRENCY) de bu lai toc do - khong con "gui theo lo" nhu
    gia dinh ban dau, nhung van "lich su" voi server (moi thread tu gian
    nhip `delay` giay + nhieu ngau nhien sau moi request).

    Tra ve DataFrame dung dinh dang data/market_store.py can:
    symbol, time, open, high, low, close, volume. Ma nao loi/rong thi bo
    qua (ghi log), khong lam hong ca lot.

    `progress(done, total)` duoc goi sau moi ma (ke ca ma loi) - dung de hien
    tien do trong /trangthai va thong bao cua /loc.
    """
    to_ts = to_ts if to_ts is not None else int(time.time())
    frames: list[pd.DataFrame] = []
    done = 0

    def worker(symbol: str) -> pd.DataFrame | None:
        try:
            result = _fetch_ohlcv_one(symbol, count_back, to_ts)
        finally:
            _polite_sleep(delay)
        return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {executor.submit(worker, s): s for s in symbols}
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            done += 1
            if progress is not None:
                progress(done, len(symbols))
            try:
                frame = future.result()
            except Exception as exc:
                log.warning("[ohlcv_bulk] bo qua %s: %s", symbol, exc)
                continue
            if frame is not None:
                frames.append(frame)
            if done % 100 == 0 or done == len(symbols):
                log.info("[ohlcv_bulk] %d/%d ma", done, len(symbols))

    if not frames:
        return pd.DataFrame(columns=OHLCV_COLUMNS + ["symbol"])
    frame = pd.concat(frames, ignore_index=True)
    frame = frame.drop_duplicates(["symbol", "time"]).sort_values(["symbol", "time"])
    return frame.reset_index(drop=True)
