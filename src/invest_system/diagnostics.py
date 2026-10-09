"""Chan doan moi truong chay bot - dung cho scripts/diagnose.py va lenh
/trangthai (xem bot/handlers/status.py).

Muc dich: tren Render goi Free khong co Shell, khong xem duoc may chu dang
thieu RAM hay bi chan IP. Cac kiem tra o day tra loi thang: container duoc cap
bao nhieu RAM/CPU THAT (han muc cgroup, khong phai so cua may chu vat ly), co
goi duoc cac nguon du lieu khong (ma HTTP that), kho gia/snapshot dang co gi.

Khong import aiogram - chay duoc doc lap bang `python scripts/diagnose.py`.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .analysis import snapshot
from .config import get_secrets, get_settings, now_local
from .data import fundamentals_store, market_store
from .sysinfo import current_rss_mb, format_mb, peak_rss_mb

OK = "OK"
FAIL = "LỖI"
WARN = "CẢNH BÁO"
INFO = "-"

_PROBE_SYMBOL = "FPT"
_UNLIMITED = 1 << 60


# ------------------------------------------------------------ trang thai du lieu
@dataclass
class SystemStatus:
    store_symbols: int
    store_rows: int
    store_updated: datetime | None
    store_size_mb: float | None
    snapshot_symbols: int
    snapshot_updated: datetime | None
    snapshot_stale: bool
    snapshot_partial: bool
    fundamentals_symbols: int
    fundamentals_updated: datetime | None
    build: snapshot.BuildStatus
    progress: str | None
    ram_mb: float | None
    ram_peak_mb: float | None


def collect_system_status() -> SystemStatus:
    """Chi doc metadata/cot nho, KHONG nap ca kho gia vao RAM chi de dem."""
    store_path = market_store.ohlcv_path()
    symbols = market_store.load_ohlcv(columns=["symbol"])
    snap = snapshot.load_snapshot()
    fundamentals = fundamentals_store.load_fundamentals()
    return SystemStatus(
        store_symbols=int(symbols["symbol"].nunique()) if not symbols.empty else 0,
        store_rows=len(symbols),
        store_updated=market_store.last_updated(),
        store_size_mb=store_path.stat().st_size / 1_048_576 if store_path.exists() else None,
        snapshot_symbols=len(snap),
        snapshot_updated=snapshot.snapshot_last_updated(),
        snapshot_stale=snapshot.is_stale(),
        snapshot_partial=snapshot.is_partial_snapshot(),
        fundamentals_symbols=len(fundamentals),
        fundamentals_updated=fundamentals_store.fundamentals_last_updated(),
        build=snapshot.get_build_status(),
        progress=snapshot.progress_text(),
        ram_mb=current_rss_mb(),
        ram_peak_mb=peak_rss_mb(),
    )


# ------------------------------------------------------------------- kiem tra
@dataclass
class Check:
    name: str
    status: str
    detail: str


def _read_first(*paths: str) -> str | None:
    for path in paths:
        try:
            return Path(path).read_text().strip()
        except OSError:
            continue
    return None


def _cgroup_memory_limit_mb() -> float | None:
    """Han muc RAM that cua container (cgroup v2 roi v1). None neu khong gioi han
    hoac khong phai Linux."""
    raw = _read_first(
        "/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    )
    if raw is None or raw == "max" or not raw.isdigit() or int(raw) >= _UNLIMITED:
        return None
    return int(raw) / 1_048_576


def _cgroup_cpu_quota() -> float | None:
    """So CPU that duoc cap (quota/period). None neu khong gioi han."""
    raw = _read_first("/sys/fs/cgroup/cpu.max")
    if raw:
        quota, _, period = raw.partition(" ")
        if quota != "max" and quota.isdigit() and period.isdigit():
            return int(quota) / int(period)
        return None
    quota = _read_first("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read_first("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota.lstrip("-").isdigit() and int(quota) > 0 and period.isdigit():
        return int(quota) / int(period)
    return None


def check_memory() -> Check:
    limit = _cgroup_memory_limit_mb()
    try:
        import psutil

        available = psutil.virtual_memory().available / 1_048_576
    except ImportError:
        available = None
    rss = current_rss_mb()
    parts = [
        f"hạn mức container {format_mb(limit) if limit else 'không giới hạn / không đọc được'}",
        f"còn trống {format_mb(available)}",
        f"bot đang dùng {format_mb(rss)} (đỉnh {format_mb(peak_rss_mb())})",
    ]
    status = INFO
    if limit and rss and rss > 0.8 * limit:
        status = WARN
        parts.append("gần chạm hạn mức — cân nhắc giảm UNIVERSE_MAX_SYMBOLS")
    return Check("RAM", status, "; ".join(parts))


def check_cpu() -> Check:
    parts = [f"os.cpu_count() = {os.cpu_count()}"]
    if hasattr(os, "sched_getaffinity"):
        parts.append(f"được gán {len(os.sched_getaffinity(0))} core")
    quota = _cgroup_cpu_quota()
    parts.append(f"hạn mức cgroup {quota:.2f} CPU" if quota else "không có hạn mức cgroup")
    return Check("CPU", INFO, "; ".join(parts))


def _items(body) -> list:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        return body.get("data") or []
    return []


def check_vietcap_listing() -> Check:
    from .data.vietcap import probe_endpoint

    started = time.time()
    status, body, error = probe_endpoint("GET", "/price/symbols/getAll")
    elapsed = time.time() - started
    if error and status is None:
        return Check("Vietcap getAll", FAIL, f"không kết nối được: {error}")
    items = _items(body)
    detail = f"HTTP {status}, {len(items)} mã, {elapsed:.1f}s"
    if error:
        detail += f" ({error})"
    ok = status == 200 and len(items) > 0
    if status == 200 and not items:
        detail += " — trả về RỖNG (có thể bị chặn IP hoặc sai header)"
    return Check("Vietcap getAll", OK if ok else FAIL, detail)


def check_vietcap_chart(symbol: str = _PROBE_SYMBOL) -> Check:
    from .data.vietcap import probe_endpoint

    payload = {
        "timeFrame": "ONE_DAY", "symbols": [symbol], "to": int(time.time()), "countBack": 30,
    }
    started = time.time()
    status, body, error = probe_endpoint("POST", "/chart/OHLCChart/gap-chart", payload)
    elapsed = time.time() - started
    if error and status is None:
        return Check(f"Vietcap gap-chart {symbol}", FAIL, f"không kết nối được: {error}")
    items = _items(body)
    bars = len(items[0].get("t", [])) if items and isinstance(items[0], dict) else 0
    detail = f"HTTP {status}, {bars} phiên, {elapsed:.1f}s"
    if error:
        detail += f" ({error})"
    return Check(f"Vietcap gap-chart {symbol}", OK if status == 200 and bars else FAIL, detail)


def check_dnse(symbol: str = _PROBE_SYMBOL) -> Check:
    secrets = get_secrets()
    if not secrets.dnse_api_key or not secrets.dnse_api_secret:
        return Check("DNSE", INFO, "chưa có DNSE_API_KEY/DNSE_API_SECRET — bot dùng Vietcap")
    from .data.dnse import DnseProvider

    status, bars, error = DnseProvider().probe_ohlc(symbol)
    if error:
        # Khong phai LOI: router tu chuyen sang Vietcap (nguon du phong).
        return Check("DNSE", WARN, f"gọi thử lỗi, bot tự dùng Vietcap thay thế — {error}")
    return Check("DNSE", OK if bars else WARN, f"HTTP {status}, {bars} phiên {symbol}")


def check_store(status: SystemStatus) -> Check:
    if not status.store_rows:
        return Check("Kho giá", WARN, "trống — bot sẽ tự nạp khi khởi động")
    size = f", {status.store_size_mb:,.1f} MB" if status.store_size_mb is not None else ""
    updated = f"{status.store_updated:%d/%m/%Y %H:%M}" if status.store_updated else "?"
    return Check(
        "Kho giá", OK,
        f"{status.store_symbols:,} mã, {status.store_rows:,} dòng{size}, cập nhật {updated}",
    )


def check_snapshot(status: SystemStatus) -> Check:
    if not status.snapshot_symbols:
        return Check("Snapshot", WARN, "chưa có — /loc, /tinhieu chưa có dữ liệu")
    updated = f"{status.snapshot_updated:%d/%m/%Y %H:%M}" if status.snapshot_updated else "?"
    if status.snapshot_partial:
        return Check("Snapshot", WARN, f"TẠM THỜI {status.snapshot_symbols} mã, dựng {updated}")
    state = "cũ hơn phiên gần nhất" if status.snapshot_stale else "mới"
    return Check(
        "Snapshot", WARN if status.snapshot_stale else OK,
        f"{status.snapshot_symbols:,} mã, dựng {updated}, {state}",
    )


def check_config() -> Check:
    settings = get_settings()
    return Check(
        "Cấu hình quy mô", INFO,
        f"universe.max_symbols={settings.get('universe.max_symbols', 0)}, "
        f"count_back_bootstrap={settings.get('market_store.count_back_bootstrap', 500)}, "
        f"snapshot.max_workers={settings.get('snapshot.max_workers', 1)}",
    )


def run_diagnostics(network: bool = True) -> list[Check]:
    """Chay moi kiem tra. `network=False` bo qua cac kiem tra goi mang."""
    checks = [check_memory(), check_cpu(), check_config()]
    if network:
        checks += [check_vietcap_listing(), check_vietcap_chart(), check_dnse()]
    status = collect_system_status()
    checks += [check_store(status), check_snapshot(status)]
    return checks


def format_table(checks: list[Check]) -> str:
    """Bang van ban tho, can cot - in ra console hoac boc trong <pre> tren Telegram."""
    name_w = max(len(c.name) for c in checks)
    status_w = max(len(c.status) for c in checks)
    lines = [f"Chẩn đoán lúc {now_local():%d/%m/%Y %H:%M:%S} (giờ Việt Nam)"]
    for c in checks:
        lines.append(f"{c.name:<{name_w}}  {c.status:<{status_w}}  {c.detail}")
    return "\n".join(lines)
