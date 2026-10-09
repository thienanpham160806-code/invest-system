"""Ve bieu do ky thuat (nen + may Ichimoku, MACD, RSI) gui qua Telegram.

Ve thang vao bo nho dem roi gui, KHONG ghi tep tam ra o dia - tranh rac va
tranh loi khi nhieu nguoi dung goi cung luc.

matplotlib (~10 MB + Pillow) chi nap o lan ve dau tien, khong nap luc khoi
dong bot - de RAM nen thap hon tren may/goi Render it bo nho.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

from ..indicators.ichimoku import ichimoku
from ..indicators.macd import macd
from ..indicators.rsi import adaptive_bands, rsi

_UP_COLOR = "#2e7d52"
_DOWN_COLOR = "#c0392b"


def candlestick_png(
    frame: pd.DataFrame,
    symbol: str,
    stop_loss: float | None = None,
    target: float | None = None,
    bars: int = 180,
) -> bytes:
    """Tra ve anh PNG dang bytes: nen + may Ichimoku o tren, khoi luong,
    MACD va RSI (kem hai duong nguong thich ung) o cac khung phu duoi.
    """
    if frame.empty:
        raise ValueError("Khong co du lieu de ve")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ichi = ichimoku(frame)
    macd_lines = macd(frame)
    rsi_series = rsi(frame["close"])
    bands = adaptive_bands(rsi_series)

    data = frame.tail(bars)
    ichi = ichi.loc[data.index]
    macd_lines = macd_lines.loc[data.index]
    rsi_tail = rsi_series.loc[data.index]
    bands_tail = bands.loc[data.index]

    fig, (ax_price, ax_vol, ax_macd, ax_rsi) = plt.subplots(
        4, 1, figsize=(10, 10), dpi=140, sharex=True,
        gridspec_kw={"height_ratios": [3, 0.8, 1, 1]},
    )
    x = np.arange(len(data))

    _draw_price_panel(ax_price, x, data, ichi, symbol, stop_loss, target)
    _draw_volume_panel(ax_vol, x, data)
    _draw_macd_panel(ax_macd, x, macd_lines)
    _draw_rsi_panel(ax_rsi, x, rsi_tail, bands_tail)

    step = max(len(data) // 8, 1)
    ax_rsi.set_xticks(x[::step])
    ax_rsi.set_xticklabels([t.strftime("%d/%m") for t in data["time"]][::step], fontsize=8)

    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", facecolor="white")
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()


def _draw_price_panel(ax, x, data, ichi, symbol, stop_loss, target) -> None:
    senkou_a, senkou_b = ichi["senkou_a"].to_numpy(), ichi["senkou_b"].to_numpy()
    # May xanh khi Dan A tren Dan B (xu huong tang), do khi nguoc lai.
    ax.fill_between(
        x, senkou_a, senkou_b, where=senkou_a >= senkou_b,
        color=_UP_COLOR, alpha=0.18, interpolate=True,
    )
    ax.fill_between(
        x, senkou_a, senkou_b, where=senkou_a < senkou_b,
        color=_DOWN_COLOR, alpha=0.18, interpolate=True,
    )
    ax.plot(x, ichi["tenkan"], color="#e8a33d", linewidth=1.0, label="Tenkan")
    ax.plot(x, ichi["kijun"], color="#2f6f8f", linewidth=1.0, label="Kijun")

    for i, (_, row) in enumerate(data.iterrows()):
        up = row["close"] >= row["open"]
        color = _UP_COLOR if up else _DOWN_COLOR
        ax.plot([i, i], [row["low"], row["high"]], color=color, linewidth=0.8)
        ax.plot(
            [i, i], [row["open"], row["close"]], color=color, linewidth=3.0, solid_capstyle="butt"
        )

    if stop_loss:
        ax.axhline(stop_loss, color=_DOWN_COLOR, linestyle=":", linewidth=1.0, label="Cắt lỗ")
    if target:
        ax.axhline(target, color=_UP_COLOR, linestyle="--", linewidth=1.0, label="Mục tiêu")

    ax.set_title(f"{symbol} — {len(data)} phiên gần nhất", fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=7, frameon=False, ncol=2)
    ax.grid(alpha=0.25)


def _draw_volume_panel(ax, x, data) -> None:
    pairs = zip(data["open"], data["close"], strict=False)
    colors = [_UP_COLOR if c >= o else _DOWN_COLOR for o, c in pairs]
    ax.bar(x, data["volume"], color=colors, alpha=0.75)
    ax.set_ylabel("KL", fontsize=8)
    ax.grid(alpha=0.2)


def _draw_macd_panel(ax, x, macd_lines) -> None:
    ax.plot(x, macd_lines["macd"], color="#2f6f8f", linewidth=1.0, label="MACD")
    ax.plot(x, macd_lines["signal"], color="#e8a33d", linewidth=1.0, label="Signal")
    hist = macd_lines["hist"].fillna(0.0)
    hist_colors = [_UP_COLOR if v >= 0 else _DOWN_COLOR for v in hist]
    ax.bar(x, hist, color=hist_colors, alpha=0.6)
    ax.axhline(0, color="#888888", linewidth=0.6)
    ax.set_ylabel("MACD", fontsize=8)
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    ax.grid(alpha=0.2)


def _draw_rsi_panel(ax, x, rsi_tail, bands_tail) -> None:
    ax.plot(x, rsi_tail, color="#2f6f8f", linewidth=1.0, label="RSI")
    ax.plot(
        x, bands_tail["upper"], color=_DOWN_COLOR, linewidth=0.8,
        linestyle="--", label="Ngưỡng trên",
    )
    ax.plot(
        x, bands_tail["lower"], color=_UP_COLOR, linewidth=0.8,
        linestyle="--", label="Ngưỡng dưới",
    )
    ax.set_ylim(0, 100)
    ax.set_ylabel("RSI", fontsize=8)
    ax.legend(loc="upper left", fontsize=7, frameon=False)
    ax.grid(alpha=0.2)
