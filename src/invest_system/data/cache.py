"""Cache hai tang: SQLite cho sieu du lieu, Parquet cho chuoi gia dai."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from ..config import get_paths
from ..logging_conf import get_logger

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_meta (
    key         TEXT PRIMARY KEY,
    updated_at  REAL NOT NULL,
    rows        INTEGER
);

CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id     INTEGER NOT NULL,
    symbol      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    PRIMARY KEY (chat_id, symbol)
);

CREATE TABLE IF NOT EXISTS signals (
    trade_date  TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    probability REAL,
    entry       REAL,
    stop_loss   REAL,
    target      REAL,
    payload     TEXT,
    PRIMARY KEY (trade_date, symbol, side)
);

CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(trade_date);

-- alerts/eod.py dung cot payload (JSON) de luu trang thai khuyen nghi gan
-- nhat cua moi ma (side = 'eod'), lam co so so sanh cho lan quet ke tiep.

CREATE TABLE IF NOT EXISTS alert_settings (
    chat_id     INTEGER PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS macro_news_items (
    guid            TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    link            TEXT NOT NULL,
    category        TEXT NOT NULL,
    summary         TEXT,
    published_at    TEXT NOT NULL,
    source          TEXT NOT NULL,
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_published ON macro_news_items(published_at);

CREATE TABLE IF NOT EXISTS news_subscribers (
    chat_id     INTEGER PRIMARY KEY,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL
);
"""


@contextmanager
def connect():
    path = get_paths().cache_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    log.info("Da khoi tao CSDL tai %s", get_paths().cache_db)


# ----------------------------------------------------------------- parquet cache
def _parquet_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return get_paths().data_dir / "parquet" / f"{safe}.parquet"


def write_frame(key: str, frame: pd.DataFrame) -> None:
    path = _parquet_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    with connect() as conn:
        conn.execute(
            "INSERT INTO cache_meta(key, updated_at, rows) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET updated_at=excluded.updated_at, rows=excluded.rows",
            (key, time.time(), len(frame)),
        )


def read_frame(key: str, max_age: float | None = None) -> pd.DataFrame | None:
    """Doc cache. Tra None neu chua co hoac da qua han max_age giay."""
    path = _parquet_path(key)
    if not path.exists():
        return None
    if max_age is not None:
        with connect() as conn:
            row = conn.execute(
                "SELECT updated_at FROM cache_meta WHERE key = ?", (key,)
            ).fetchone()
        if row and (time.time() - row["updated_at"]) > max_age:
            return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # pragma: no cover
        log.warning("Doc cache %s that bai: %s", key, exc)
        return None


def age_seconds(key: str) -> float | None:
    with connect() as conn:
        row = conn.execute("SELECT updated_at FROM cache_meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else time.time() - row["updated_at"]


# ----------------------------------------------------------------- tin tuc vi mo & phap luat
def save_macro_news_items(items: list[dict]) -> list[dict]:
    """Luu danh sach tin tuc vi mo vao cache. Tra ve danh sach cac tin MOI chua tung co."""
    if not items:
        return []
    new_items: list[dict] = []
    now = time.time()
    with connect() as conn:
        for it in items:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO macro_news_items "
                "(guid, title, link, category, summary, published_at, source, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    it["guid"],
                    it["title"],
                    it["link"],
                    it["category"],
                    it.get("summary", ""),
                    it["published_at"],
                    it["source"],
                    now,
                ),
            )
            if cursor.rowcount > 0:
                new_items.append(it)
    return new_items


def get_recent_macro_news(limit: int = 6, category: str | None = None) -> list[dict]:
    """Lay danh sach tin tuc vi mo moi nhat tu CSDL."""
    query = (
        "SELECT guid, title, link, category, summary, published_at, source "
        "FROM macro_news_items "
    )
    params: list[object] = []
    if category:
        query += "WHERE category = ? "
        params.append(category)
    query += "ORDER BY published_at DESC LIMIT ?"
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def set_news_subscriber(chat_id: int, enabled: bool = True) -> None:
    """Bat hoac tat nhan tin tuc dinh ky moi gio cho nguoi dung / group."""
    with connect() as conn:
        conn.execute(
            "INSERT INTO news_subscribers(chat_id, enabled, created_at) VALUES (?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled",
            (chat_id, 1 if enabled else 0, time.time()),
        )


def is_news_subscribed(chat_id: int) -> bool:
    """Kiem tra xem chat_id co dang bat nhan tin tuc tu dong khong."""
    with connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM news_subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return bool(row["enabled"]) if row else False


def get_news_subscribers() -> list[int]:
    """Lay danh sach chat_id dang bat nhan tin tuc moi gio."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM news_subscribers WHERE enabled = 1"
        ).fetchall()
        return [int(r["chat_id"]) for r in rows]


def seed_subscribers(chat_ids: list[int]) -> None:
    """Dang ky san ban tin tin tuc cho `chat_ids` neu chat do CHUA tung bat/tat
    - dung bien AUTO_SUBSCRIBE_CHAT_IDS de giu dang ky qua cac lan Render Free
    khoi dong lai (moi lan la mot CSDL trang)."""
    now = time.time()
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO news_subscribers(chat_id, enabled, created_at) "
            "VALUES (?, 1, ?)",
            [(chat_id, now) for chat_id in chat_ids],
        )
