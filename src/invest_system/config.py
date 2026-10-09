"""Nap cau hinh tu settings.yaml va bien moi truong."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Secrets:
    """Thong tin nhay cam, chi doc tu bien moi truong."""

    telegram_token: str = ""
    telegram_admin_ids: tuple[int, ...] = ()
    dnse_api_key: str = ""
    dnse_api_secret: str = ""
    dnse_base_url: str = "https://openapi.dnse.com.vn"
    dnse_api_version: str = "2026-05-07"

    @classmethod
    def from_env(cls) -> Secrets:
        raw_admins = os.getenv("TELEGRAM_ADMIN_IDS", "")
        admins = tuple(
            int(x) for x in (p.strip() for p in raw_admins.split(",")) if x.isdigit()
        )
        return cls(
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_admin_ids=admins,
            dnse_api_key=os.getenv("DNSE_API_KEY", ""),
            dnse_api_secret=os.getenv("DNSE_API_SECRET", ""),
            dnse_base_url=os.getenv("DNSE_BASE_URL", "https://openapi.dnse.com.vn"),
            dnse_api_version=os.getenv("DNSE_API_VERSION", "2026-05-07"),
        )


@dataclass(frozen=True)
class Paths:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    cache_db: Path = field(
        default_factory=lambda: Path(os.getenv("CACHE_DB", "./data/cache.sqlite3"))
    )
    model_dir: Path = field(default_factory=lambda: Path(os.getenv("MODEL_DIR", "./artifacts")))

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)


# Khoa cau hinh cho phep ghi de bang bien moi truong - de dat rieng tren may
# chu (vd Render) ma khong phai sua file settings.yaml trong repo.
_ENV_OVERRIDES: dict[str, tuple[str, type]] = {
    "universe.max_symbols": ("UNIVERSE_MAX_SYMBOLS", int),
    "market_store.count_back_bootstrap": ("MARKET_COUNT_BACK", int),
    "snapshot.max_workers": ("SNAPSHOT_MAX_WORKERS", int),
}


class Settings:
    """Bao mong quanh settings.yaml, truy cap bang duong dan dau cham. Mot so
    khoa co the bi ghi de bang bien moi truong (xem _ENV_OVERRIDES)."""

    def __init__(self, raw: dict[str, Any]):
        self._raw = raw

    def get(self, dotted: str, default: Any = None) -> Any:
        override = _ENV_OVERRIDES.get(dotted)
        if override is not None:
            env_name, cast = override
            raw_value = os.getenv(env_name, "").strip()
            if raw_value:
                try:
                    return cast(raw_value)
                except ValueError as exc:
                    raise ValueError(
                        f"Bien moi truong {env_name}={raw_value!r} khong hop le "
                        f"(can kieu {cast.__name__})"
                    ) from exc

        node: Any = self._raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, dotted: str) -> Any:
        value = self.get(dotted, _MISSING)
        if value is _MISSING:
            raise KeyError(f"Thieu khoa cau hinh: {dotted}")
        return value

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw


_MISSING = object()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as fh:
        return Settings(yaml.safe_load(fh))


def bot_timezone() -> ZoneInfo:
    """Mui gio giao dich cua bot (config bot.timezone, mac dinh Asia/Ho_Chi_Minh)."""
    return ZoneInfo(get_settings().get("bot.timezone", "Asia/Ho_Chi_Minh"))


def now_local() -> datetime:
    """Gio hien tai theo bot.timezone, CO gan mui gio. Dung thay cho
    datetime.now() tran: may chu (vd Render) chay UTC, lech 7 gio so voi gio
    giao dich Viet Nam - moi phep so voi gio dong cua 15h phai theo gio VN."""
    return datetime.now(bot_timezone())


def auto_subscribe_chat_ids() -> list[int]:
    """Chat duoc tu dang ky ban tin tin tuc moi lan bot khoi dong (bien
    AUTO_SUBSCRIBE_CHAT_IDS, cach nhau dau phay; chap nhan id am cua nhom)."""
    ids: list[int] = []
    for part in os.getenv("AUTO_SUBSCRIBE_CHAT_IDS", "").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


@lru_cache(maxsize=1)
def get_universe_config() -> dict[str, Any]:
    with open(CONFIG_DIR / "universe.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def get_secrets() -> Secrets:
    return Secrets.from_env()


@lru_cache(maxsize=1)
def get_paths() -> Paths:
    paths = Paths()
    paths.ensure()
    return paths
