"""Do RAM cua tien trinh bot - de ghi log khi dung snapshot va hien trong
/trangthai. Goi Render Free chi co 512 MB, vuot la bi OOM kill va mat sach
data/ (dia tam), nen can thay duoc RAM thuc te thay vi doan.
"""
from __future__ import annotations

import sys

_MB = 1_048_576


def current_rss_mb() -> float | None:
    """RAM tien trinh dang giu (RSS). None neu khong do duoc."""
    try:
        import psutil
    except ImportError:
        return None
    return psutil.Process().memory_info().rss / _MB


def peak_rss_mb() -> float | None:
    """RAM DINH tu luc tien trinh khoi dong. None neu khong do duoc."""
    try:
        import resource
    except ImportError:  # Windows khong co module resource
        try:
            import psutil
        except ImportError:
            return None
        info = psutil.Process().memory_info()
        return getattr(info, "peak_wset", info.rss) / _MB
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss: Linux tinh bang KB, macOS tinh bang byte
    return peak / _MB if sys.platform == "darwin" else peak / 1024


def format_mb(value: float | None) -> str:
    return "không đo được" if value is None else f"{value:,.0f} MB"
