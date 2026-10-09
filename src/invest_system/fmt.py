"""Dinh dang so kieu Viet Nam: 1.234.567,8 - dung chung cho PDF, UI, nhan xet."""
from __future__ import annotations

import math


def _ok(v) -> bool:
    try:
        return v is not None and not (isinstance(v, float) and math.isnan(v)) and math.isfinite(float(v))
    except Exception:  # noqa: BLE001 - ca jinja2 Undefined
        return False


def num(v, decimals: int = 0, na: str = "N/A") -> str:
    if not _ok(v):
        return na
    text = f"{float(v):,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(v, decimals: int = 1, na: str = "N/A", sign: bool = False) -> str:
    """v la TY LE (0.125 -> 12,5%)."""
    if not _ok(v):
        return na
    s = num(float(v) * 100, decimals)
    if sign and float(v) > 0:
        s = "+" + s
    return s + "%"


def times(v, decimals: int = 2, na: str = "N/A") -> str:
    return na if not _ok(v) else num(v, decimals) + "x"


def bn(v, decimals: int = 0, na: str = "N/A") -> str:
    """VND -> ty dong."""
    return na if not _ok(v) else num(float(v) / 1e9, decimals)


def price(v, na: str = "N/A") -> str:
    return na if not _ok(v) else num(v, 0)


def fmt_ratio(v, kind: str) -> str:
    return {"pct": pct, "x": times, "vnd": bn, "d": lambda x: num(x, 0)}.get(kind, num)(v)
