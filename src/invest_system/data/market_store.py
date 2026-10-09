"""Kho du lieu gia TOAN SAN: mot file parquet duy nhat tren dia, doc mot lan.

Giai quyet van de: truoc day moi lan /loc hay /tinhieu phai goi mang tung ma
mot cho ca san (hang tram request, lam bot treo). Gio toan bo lich su gia
cua ca san nam trong MOT file (`data/market/ohlcv.parquet`), duoc cap nhat
dinh ky boi `scripts/backfill_data.py` (tai lan dau ~3 nam, cac lan sau chi
tai them vai phien moi va gop vao). Luc bot chay, moi noi can OHLCV toan san
(liquid_universe, screener, snapshot) CHI DOC file nay - khong goi mang.

`data/router.py::ohlcv()` van la duong lay gia CHO TUNG MA rieng le (vd
/khuyennghi mot ma) - no doc kho nay TRUOC, chi goi mang khi ma khong co
trong kho (xem router.py).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..config import bot_timezone, get_paths, get_settings
from ..logging_conf import get_logger

log = get_logger(__name__)

OHLCV_COLUMNS = ["symbol", "time", "open", "high", "low", "close", "volume"]
_NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume"]
OHLCV_FILENAME = "ohlcv.parquet"
SYMBOLS_FILENAME = "symbols.parquet"

# Cache trong bo nho tien trinh: {duong_dan: (mtime_luc_doc, DataFrame)}. Tu
# lam moi khi file tren dia doi mtime (backfill_data.py ghi de file), khong
# can khoi dong lai tien trinh. Kho OHLCV chi cache BAN DAY DU (moi cot) -
# ban doc mot phan cot khong cache, tranh giu hai ban sao cung luc.
_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _market_dir() -> Path:
    d = get_paths().data_dir / "market"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ohlcv_path() -> Path:
    return _market_dir() / OHLCV_FILENAME


def symbols_path() -> Path:
    return _market_dir() / SYMBOLS_FILENAME


def _read_cached(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    mtime = path.stat().st_mtime
    key = str(path)
    hit = _cache.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    frame = pd.read_parquet(path)
    _cache[key] = (mtime, frame)
    return frame


def _read_parquet_compact(path: Path, columns: list[str] | None) -> pd.DataFrame:
    """Doc parquet o dang tiet kiem RAM - can thiet de chay vua may chu 512 MB
    (Render goi Free): symbol -> category, gia/khoi luong -> float32.

    Ep kieu NGAY O TANG ARROW (truoc to_pandas), khong phai doc xong roi moi
    astype: tranh tao ~1,1 trieu object chuoi Python cho cot symbol. Do thuc
    te tren kho toan san (1,1 trieu dong): DataFrame 110,8 MB -> 33,4 MB, RAM
    tien trinh sau khi doc 261 MB -> 156 MB (nho release_unused() tra vung
    nho thua cua Arrow ve he dieu hanh). float32 du chinh xac cho gia (~7 chu
    so co nghia) va chi bao ky thuat; khoi luong lam tron ~1e-7, khong dang ke.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    read_dictionary = ["symbol"] if columns is None or "symbol" in columns else None
    table = pq.read_table(path, columns=columns, read_dictionary=read_dictionary)
    schema = pa.schema(
        [pa.field(f.name, pa.float32()) if f.name in _NUMERIC_COLUMNS else f for f in table.schema]
    )
    frame = table.cast(schema, safe=False).to_pandas()
    del table
    pa.default_memory_pool().release_unused()
    return frame


def _read_ohlcv(path: Path, columns: list[str] | None) -> pd.DataFrame:
    mtime = path.stat().st_mtime
    hit = _cache.get(str(path))
    if hit is not None and hit[0] == mtime:
        return hit[1] if columns is None else hit[1][columns]
    if columns is not None:
        return _read_parquet_compact(path, columns)
    frame = _read_parquet_compact(path, None)
    _cache[str(path)] = (mtime, frame)
    return frame


def load_ohlcv(
    symbols: list[str] | None = None,
    since: date | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    """Doc OHLCV tu kho (toan san neu `symbols` la None). DataFrame RONG neu
    chua backfill lan nao - goi noi khong duoc tu dong goi mang bu vao.

    `columns`: chi doc cac cot nay tu parquet (`pd.read_parquet(columns=...)`)
    - giam RAM tren may chu 512 MB khi chi can vai cot (vd data/universe.py
    chi can symbol/time/close/volume). Du lieu tra ve LUON o dang tiet kiem
    RAM (xem _read_parquet_compact()): symbol la category, gia/khoi luong la
    float32.
    """
    path = ohlcv_path()
    if not path.exists():
        return pd.DataFrame(columns=columns or OHLCV_COLUMNS)

    read_columns = None
    if columns is not None:
        extra = (["symbol"] if symbols else []) + (["time"] if since is not None else [])
        read_columns = list(dict.fromkeys([*columns, *extra]))

    frame = _read_ohlcv(path, read_columns)
    if frame.empty:
        return frame
    if symbols:
        wanted = {s.upper() for s in symbols}
        frame = frame[frame["symbol"].isin(wanted)]
    if since is not None:
        frame = frame[frame["time"] >= pd.Timestamp(since)]
    if columns is not None:
        frame = frame[columns]
    return frame.reset_index(drop=True)


def load_symbols() -> pd.DataFrame:
    """Danh sach ma + san niem yet (va cac cot khac neu co) tu kho."""
    return _read_cached(symbols_path(), ["symbol", "exchange"])


def frames_by_symbol(
    symbols: list[str] | None = None, since: date | None = None
) -> dict[str, pd.DataFrame]:
    """Tach OHLCV theo tung ma bang mot lan groupby - KHONG doc file nhieu lan."""
    frame = load_ohlcv(symbols, since)
    if frame.empty:
        return {}
    result: dict[str, pd.DataFrame] = {}
    # observed=True: symbol la category (xem _read_parquet_compact) - khong co thi groupby
    # sinh ra MOI category cua ca san, ke ca ma da bi loc bo (nhom rong).
    for symbol, group in frame.groupby("symbol", observed=True, sort=False):
        result[str(symbol)] = group.sort_values("time").reset_index(drop=True)
    return result


def last_updated() -> datetime | None:
    """Thoi diem file OHLCV duoc ghi lan gan nhat (gan mui gio bot.timezone),
    None neu chua co kho."""
    path = ohlcv_path()
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=bot_timezone())


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Chuan hoa du lieu moi truoc khi ghi: dung cot, ma viet hoa, time la
    datetime, gia/khoi luong float32."""
    frame = frame[OHLCV_COLUMNS].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["time"] = pd.to_datetime(frame["time"])
    frame[_NUMERIC_COLUMNS] = frame[_NUMERIC_COLUMNS].astype("float32")
    return frame


def save_ohlcv(frame: pd.DataFrame, merge: bool = True) -> int:
    """Ghi OHLCV vao kho, gop voi du lieu cu (neu `merge`) va khu trung theo
    (symbol, time), giu ban ghi MOI hon khi trung. Tra ve tong so dong sau khi ghi.

    Gop o dang TIET KIEM RAM (symbol category, gia float32): ban cu doc lai
    ca kho bang pd.read_parquet (symbol object, float64) roi concat - do
    thuc te ton them ~270 MB moi lan tren kho toan san, du lam may chu 512 MB
    (Render goi Free) bi OOM o cac lo cuoi cua bootstrap() va o refresh()
    hang ngay. Hai ben phai CUNG danh sach category thi concat moi giu duoc
    kieu category (khac nhau -> pandas bung ra object).
    """
    path = ohlcv_path()
    frame = _normalize(frame)

    if merge and path.exists():
        existing = _read_ohlcv(path, None)
        categories = existing["symbol"].cat.categories.union(pd.Index(frame["symbol"].unique()))
        frame = pd.concat(
            [
                existing.assign(symbol=existing["symbol"].cat.set_categories(categories)),
                frame.assign(symbol=pd.Categorical(frame["symbol"], categories=categories)),
            ],
            ignore_index=True,
        )
    else:
        frame["symbol"] = frame["symbol"].astype("category")

    frame = frame.drop_duplicates(subset=["symbol", "time"], keep="last")
    frame = frame.sort_values(["symbol", "time"]).reset_index(drop=True)
    frame.to_parquet(path, index=False)
    _cache.pop(str(path), None)
    log.info("market_store: da ghi %d dong vao %s", len(frame), path)
    return len(frame)


def save_symbols(frame: pd.DataFrame) -> None:
    path = symbols_path()
    frame.to_parquet(path, index=False)
    _cache.pop(str(path), None)


def _count_back(key: str, default: int) -> int:
    return int(get_settings().get(f"market_store.{key}", default))


ProgressFn = Callable[[int, int], None]


def refresh(count_back: int | None = None, progress: ProgressFn | None = None) -> int:
    """Cap nhat TANG DAN: tai `count_back` phien gan nhat (mac dinh: config
    market_store.count_back_refresh) cho CAC MA DA CO trong kho, gop vao
    (khu trung theo (symbol, time), giu ban ghi moi hon).

    Dung cho lich chay hang ngay (xem bot/scheduler.py, bot/main.py:
    daily_scan_job) - NGAN va nhanh hon nhieu so voi backfill lan dau. Neu
    kho chua co gi (chua chay scripts/backfill_data.py lan nao, hoac dia bi
    xoa trang - vd Render goi Free KHONG co dia luu ben vung, moi lan
    container khoi dong lai la kho lai rong), khong lam gi ca va tra ve 0 -
    goi noi (vd ensure_fresh_in_background()) tu quyet dinh co goi
    bootstrap() thay the hay khong.
    """
    existing = load_ohlcv(columns=["symbol"])
    if existing.empty:
        log.warning(
            "market_store.refresh(): kho rong, chay scripts/backfill_data.py lan dau truoc"
        )
        return 0

    from .vietcap import fetch_ohlcv_bulk  # tranh import vong o muc module

    count_back = count_back or _count_back("count_back_refresh", 10)
    symbols = sorted(str(s) for s in existing["symbol"].unique())
    frame = fetch_ohlcv_bulk(symbols, count_back=count_back, progress=progress)
    return save_ohlcv(frame, merge=True)


_BOOTSTRAP_CHUNK_SIZE = 150  # xem docstring bootstrap(): giam dinh RAM


def _parquet_schema():
    import pyarrow as pa

    return pa.schema(
        [("symbol", pa.string()), ("time", pa.timestamp("ns"))]
        + [(col, pa.float32()) for col in _NUMERIC_COLUMNS]
    )


def bootstrap(
    exchanges: list[str] | None = None,
    count_back: int | None = None,
    chunk_size: int = _BOOTSTRAP_CHUNK_SIZE,
    progress: ProgressFn | None = None,
) -> int:
    """Nap TOAN BO lich su gia cho CA SAN (giong scripts/backfill_data.py
    lan dau), dung khi kho HOAN TOAN RONG - vd container vua khoi dong tren
    moi truong khong co dia luu ben vung (Render goi Free: /data bi xoa
    trang moi lan container restart/spin-down-wake, khac voi may ca nhan).

    KHAC voi refresh(): refresh() chi tai bu vai phien cho ma DA CO san -
    tren kho rong no khong lam gi ca (dung y, tranh tu bia danh sach ma).
    bootstrap() moi thuc su tai danh sach ma + lich su day du tu dau.

    Tai theo TUNG LO (`chunk_size` ma/lo) va ghi NOI TIEP vao mot file tam
    bang pyarrow.ParquetWriter, xong het moi DOI TEN thanh kho that:
      1. RAM: trong bo nho chi co mot lo tai mot thoi diem, khong phai doc
         lai ca kho sau moi lo de gop (ban truoc lam vay, ton RAM tang dan
         theo kich thuoc kho - nguy hiem tren may chu 512 MB).
      2. Kho luon NGUYEN VEN: hoac chua co, hoac du ca san. Neu bi ngat giua
         chung (loi mang, bi restart...) thi kho khong xuat hien, lan sau
         bootstrap lai tu dau. Ban truoc luu tung lo thang vao kho - bi ngat
         o 450/1500 ma thi kho "khong rong" nen lan sau chi goi refresh(),
         ma refresh() chi cap nhat ma DA CO -> kho ket o 450 ma mai mai.

    `count_back` mac dinh lay tu config market_store.count_back_bootstrap
    (500 phien ~ 2 nam; ghi de bang bien MARKET_COUNT_BACK): van du cho moi
    chi bao - Ichimoku can 52+26 phien, RSI thich ung can 252 - nhung kho
    nho hon ~1/3 so voi 750 phien truoc day.

    Cham hon refresh() nhieu (~2-3 phut cho toan san, do thuc te 1.523 ma/
    123s) - chi nen goi khi phat hien kho rong, khong goi lap lai moi vong
    quet dinh ky (xem analysis/snapshot.py:ensure_fresh_in_background()).
    """
    from .vietcap import fetch_all_symbols, fetch_ohlcv_bulk  # tranh import vong

    count_back = count_back or _count_back("count_back_bootstrap", 500)
    exchanges = exchanges or get_settings().get(
        "universe.exchanges", ["HOSE", "HNX", "UPCOM"]
    )
    symbols_frame = fetch_all_symbols(exchanges)
    if symbols_frame.empty:
        log.warning("market_store.bootstrap(): khong lay duoc danh sach ma, bo qua")
        return 0
    save_symbols(symbols_frame)

    import pyarrow as pa
    import pyarrow.parquet as pq

    symbols = symbols_frame["symbol"].tolist()
    path = ohlcv_path()
    tmp_path = path.with_name(path.name + ".tmp")
    schema = _parquet_schema()
    total = 0
    try:
        with pq.ParquetWriter(tmp_path, schema) as writer:
            for i in range(0, len(symbols), chunk_size):
                chunk = symbols[i : i + chunk_size]
                chunk_progress = None
                if progress is not None:
                    def chunk_progress(done: int, _total: int, offset: int = i) -> None:
                        progress(offset + done, len(symbols))
                frame = fetch_ohlcv_bulk(chunk, count_back=count_back, progress=chunk_progress)
                if frame.empty:
                    continue
                frame = _normalize(frame).drop_duplicates(subset=["symbol", "time"], keep="last")
                frame = frame.sort_values(["symbol", "time"])
                writer.write_table(pa.Table.from_pandas(frame, schema=schema, preserve_index=False))
                total += len(frame)
                log.info(
                    "market_store.bootstrap(): da tai %d/%d ma (%d dong)",
                    min(i + chunk_size, len(symbols)), len(symbols), total,
                )
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    if total == 0:
        tmp_path.unlink(missing_ok=True)
        log.warning("market_store.bootstrap(): khong tai duoc dong gia nao, kho giu nguyen")
        return 0
    tmp_path.replace(path)
    _cache.pop(str(path), None)
    log.info("market_store.bootstrap(): xong %d ma, %d dong", len(symbols), total)
    return total
