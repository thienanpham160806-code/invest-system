"""Doc bang toan thi truong (tinh san boi scripts/build_market_universe.py).

Thu tu: Vercel Blob (`universe/latest.parquet`, neu co BLOB_BASE_URL) -> ban dong
goi trong repo (webdata/snapshot). Cache trong bo nho tien trinh 10 phut.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

from ..config import PROJECT_ROOT
from ..logging_conf import get_logger

log = get_logger(__name__)

WEBDATA = Path(os.getenv("WEBDATA_DIR", str(PROJECT_ROOT / "webdata")))
SNAPSHOT_DIR = WEBDATA / "snapshot"
UNCLASSIFIED = "Chưa phân loại"
_TTL = 600

COMPANY_TYPE_LABELS = {
    "BANK": "Ngân hàng", "SECURITIES": "Chứng khoán", "INSURANCE": "Bảo hiểm",
    "REAL_ESTATE": "Bất động sản", "NON_FINANCIAL": "Phi tài chính",
}


def _strip(text) -> str:
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _strip(text)).strip("-") or "na"


def node_key(level: int, name: str) -> str:
    return f"{level}-{slugify(name)}"


def classify_company_type(com_type_code, icb1, icb2, icb3, icb4) -> str:
    """Loai DN (quyet dinh phuong phap dinh gia). Uu tien ma loai DN cua vnstock
    (NH/CK/BH), sau do ICB cap 2-4."""
    code = str(com_type_code or "").upper()
    if code == "NH":
        return "BANK"
    if code == "CK":
        return "SECURITIES"
    if code == "BH":
        return "INSURANCE"
    l2, l3, l4 = _strip(icb2), _strip(icb3), _strip(icb4)
    if "ngan hang" in l2 or "ngan hang" in l4:
        return "BANK"
    if "bao hiem" in l2 or "bao hiem" in l3:
        return "INSURANCE"
    if "moi gioi chung khoan" in l4 or "chung khoan" in l4:
        return "SECURITIES"
    if "bat dong san" in l2 and "dich vu" not in l4 and "quy" not in l3:
        return "REAL_ESTATE"
    return "NON_FINANCIAL"


# ------------------------------------------------------------------ nap du lieu
_cache: dict[str, tuple[float, object]] = {}


def _blob_get(name: str) -> bytes | None:
    base = os.getenv("BLOB_BASE_URL", "").rstrip("/")
    if not base:
        return None
    try:
        import requests

        resp = requests.get(f"{base}/universe/{name}", timeout=8)
        if resp.ok:
            return resp.content
    except Exception as exc:  # noqa: BLE001
        log.warning("Blob %s loi: %s", name, exc)
    return None


def _cached(key: str, loader):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    value = loader()
    _cache[key] = (time.time(), value)
    return value


def load_universe() -> tuple[pd.DataFrame, dict]:
    """(bang universe, meta). meta gom origin = 'blob' | 'bundled'."""
    def loader():
        raw = _blob_get("latest.parquet")
        meta_raw = _blob_get("meta.json") if raw else None
        if raw is not None:
            frame = pd.read_parquet(io.BytesIO(raw))
            meta = json.loads(meta_raw) if meta_raw else {}
            meta["origin"] = "Vercel Blob (universe/latest.parquet)"
        else:
            frame = pd.read_parquet(SNAPSHOT_DIR / "market_universe.parquet")
            path = SNAPSHOT_DIR / "meta.json"
            meta = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            meta["origin"] = "Bản đóng gói trong repo (webdata/snapshot)"
        return frame, meta
    return _cached("universe", loader)


def load_sector_index() -> pd.DataFrame:
    def loader():
        path = SNAPSHOT_DIR / "sector_index.parquet"
        return pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["node", "time", "value"])
    return _cached("sector_index", loader)


def load_ohlcv_snapshot(symbol: str) -> pd.DataFrame:
    path = SNAPSHOT_DIR / "ohlcv.parquet"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_parquet(path, filters=[("symbol", "==", symbol.upper())])
    return frame.sort_values("time").reset_index(drop=True)


def load_vnindex_snapshot() -> pd.DataFrame:
    path = SNAPSHOT_DIR / "vnindex.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def zenodo_index() -> pd.DataFrame:
    path = WEBDATA / "zenodo_master_index.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path, columns=["ticker_file", "year_full", "document_type", "file_name",
                                          "relative_path", "file_size_mb", "status"])
