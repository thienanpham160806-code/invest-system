"""Bieu do cho bao cao PDF (matplotlib, font Be Vietnam Pro, tra ve PNG base64)."""
from __future__ import annotations

import base64
import io
from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import PROJECT_ROOT

NAVY = "#12355b"
TEAL = "#1f8a70"
GOLD = "#c8901a"
RED = "#b3261e"
GRAY = "#8a94a3"
LIGHT = "#e6ebf1"
SERIES = [NAVY, TEAL, GOLD, "#6c4ab6", "#d4652f", "#2a9dc4", GRAY]


@lru_cache(maxsize=1)
def _setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    family = "DejaVu Sans"
    for p in (PROJECT_ROOT / "assets" / "fonts").glob("BeVietnamPro-*.ttf"):
        font_manager.fontManager.addfont(str(p))
        family = "Be Vietnam Pro"
    plt.rcParams.update({
        "font.family": family, "font.size": 8.5, "axes.titlesize": 9.5, "axes.titleweight": "bold",
        "axes.edgecolor": "#c5ccd6", "axes.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": LIGHT, "grid.linewidth": 0.6,
        "xtick.color": "#4a5563", "ytick.color": "#4a5563", "legend.frameon": False,
        "figure.dpi": 100, "savefig.dpi": 200, "axes.titlelocation": "left",
    })
    return plt


def _encode(fig) -> str:
    plt = _setup()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _vn_tick(v, _pos=None):
    return f"{v:,.0f}".replace(",", ".")


def price_vs_benchmark(stock: pd.DataFrame, bench: pd.DataFrame, symbol: str, bench_name: str,
                       days: int = 365) -> str | None:
    if stock is None or stock.empty:
        return None
    plt = _setup()
    end = stock["time"].iloc[-1]
    s = stock[stock["time"] >= end - pd.Timedelta(days=days)]
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(5.6, 3.0), sharex=True,
                                  gridspec_kw={"height_ratios": [3.2, 1]})
    ax.plot(s["time"], s["close"] / s["close"].iloc[0] * 100, color=NAVY, lw=1.4, label=symbol)
    if bench is not None and not bench.empty:
        b = bench[bench["time"] >= s["time"].iloc[0]]
        if len(b):
            ax.plot(b["time"], b["close"] / b["close"].iloc[0] * 100, color=GOLD, lw=1.1,
                    label=bench_name)
    ax.axhline(100, color=GRAY, lw=0.6, ls="--")
    ax.set_title("Diễn biến giá 12 tháng (cơ sở 100)")
    ax.legend(loc="upper left", fontsize=7.5, ncol=2)
    axv.bar(s["time"], s["volume"] / 1e6, color=TEAL, width=1.0, alpha=0.7)
    axv.set_ylabel("KL (tr cp)", fontsize=7)
    fig.autofmt_xdate(rotation=0, ha="center")
    return _encode(fig)


def financial_bars(fin, company_type: str) -> str | None:
    if fin.empty:
        return None
    plt = _setup()
    top = fin.series("total_operating_income" if company_type == "BANK" else "revenue") / 1e9
    nip = fin.series("net_income_parent") / 1e9
    if top.empty and nip.empty:
        return None
    years = [str(y) for y in fin.years]
    x = np.arange(len(years))
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    w = 0.38
    if not top.empty:
        ax.bar(x - w / 2, top.reindex(fin.years).values, w, color=NAVY,
               label="Tổng TN hoạt động" if company_type == "BANK" else "Doanh thu thuần")
    if not nip.empty:
        ax.bar(x + w / 2, nip.reindex(fin.years).values, w, color=TEAL, label="LNST CĐ mẹ")
    ax.set_xticks(x, years)
    ax.yaxis.set_major_formatter(_vn_tick)
    ax.set_title("Kết quả kinh doanh (tỷ đồng)")
    if not top.empty and not nip.empty:
        ax2 = ax.twinx()
        margin = (nip / top.replace(0, np.nan)).reindex(fin.years) * 100
        ax2.plot(x, margin.values, color=GOLD, marker="o", lw=1.3, ms=3.5,
                 label="Biên ròng (%)")
        ax2.set_ylim(0, max(5, np.nanmax(margin.values) * 1.6) if np.isfinite(np.nanmax(margin.values)) else 10)
        ax2.grid(False)
        ax2.spines["right"].set_visible(True)
        lines = ax.get_legend_handles_labels()
        l2 = ax2.get_legend_handles_labels()
        ax.legend(lines[0] + l2[0], lines[1] + l2[1], loc="upper center", fontsize=7, ncol=3,
                  bbox_to_anchor=(0.5, -0.1))
    else:
        ax.legend(fontsize=7)
    return _encode(fig)


def ratio_trends(ratios: pd.DataFrame, keys: list[tuple[str, str]], title: str) -> str | None:
    if ratios is None or ratios.empty:
        return None
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 2.4))
    drawn = 0
    for (key, label), color in zip(keys, SERIES[: len(keys)], strict=False):
        if key in ratios.columns and ratios[key].notna().any():
            ax.plot([str(y) for y in ratios.index], ratios[key].values * 100, marker="o", ms=3.5,
                    lw=1.4, color=color, label=label)
            drawn += 1
    if not drawn:
        return None
    ax.set_title(title)
    ax.set_ylabel("%")
    ax.legend(fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return _encode(fig)


def peers_scatter(table: pd.DataFrame, x: str, y: str, xlabel: str, ylabel: str,
                  title: str) -> str | None:
    if table is None or table.empty or x not in table or y not in table:
        return None
    t = table.dropna(subset=[x, y])
    if len(t) < 2:
        return None
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 2.8))
    for _, r in t.iterrows():
        tgt = bool(r.get("is_target"))
        ax.scatter(r[x] * (100 if x in ("roe", "ni_cagr") else 1),
                   r[y] * (100 if y in ("roe", "ni_cagr") else 1),
                   s=70 if tgt else 36, color=GOLD if tgt else NAVY, zorder=3,
                   edgecolor="white", lw=0.8)
        ax.annotate(r["symbol"], (r[x] * (100 if x in ("roe", "ni_cagr") else 1),
                                  r[y] * (100 if y in ("roe", "ni_cagr") else 1)),
                    xytext=(4, 3), textcoords="offset points", fontsize=7,
                    fontweight="bold" if tgt else "normal")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return _encode(fig)


def sector_vs_bench(index_series: pd.DataFrame, sector_label: str, bench_name: str) -> str | None:
    if index_series is None or index_series.empty:
        return None
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 2.3))
    ax.plot(index_series["time"], index_series["sector"], color=TEAL, lw=1.4,
            label="Chỉ số nhóm ngành (tự tính)")
    ax.plot(index_series["time"], index_series["bench"], color=GOLD, lw=1.1, label=bench_name)
    ax.axhline(100, color=GRAY, lw=0.6, ls="--")
    ax.set_title(f"Ngành {sector_label} so với thị trường (cơ sở 100)")
    ax.legend(fontsize=7, loc="upper left")
    fig.autofmt_xdate(rotation=0, ha="center")
    return _encode(fig)


def radar(scores: dict[str, float], labels: dict[str, str]) -> str | None:
    if len(scores) < 3:
        return None
    plt = _setup()
    keys = list(scores)
    vals = [scores[k] for k in keys]
    ang = np.linspace(0, 2 * np.pi, len(keys), endpoint=False).tolist()
    vals += vals[:1]
    ang += ang[:1]
    fig = plt.figure(figsize=(3.0, 3.0))
    ax = fig.add_subplot(111, polar=True)
    ax.plot(ang, vals, color=NAVY, lw=1.5)
    ax.fill(ang, vals, color=NAVY, alpha=0.18)
    ax.set_xticks(ang[:-1], [labels.get(k, k) for k in keys], fontsize=7)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75], ["25", "50", "75"], fontsize=6, color=GRAY)
    ax.grid(color=LIGHT)
    ax.spines["polar"].set_color("#c5ccd6")
    return _encode(fig)


def football_field(val) -> str | None:
    methods = [m for m in val.methods if all(np.isfinite(v) for v in m.values.values())]
    if not methods or not val.price:
        return None
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 0.5 + 0.48 * len(methods)))
    for i, m in enumerate(methods):
        lo, hi = min(m.values.values()), max(m.values.values())
        ax.barh(i, hi - lo, left=lo, color=TEAL if m.weight else GRAY, height=0.5, alpha=0.85)
        ax.plot(m.values["base"], i, "|", color="white", ms=14, mew=2)
        ax.text(hi, i, f"  {_vn_tick(m.values['base'])}", va="center", fontsize=7)
    ax.set_yticks(range(len(methods)), [f"{m.label} ({m.weight*100:.0f}%)" for m in methods], fontsize=7)
    ax.axvline(val.price, color=RED, lw=1.1, ls="--", label=f"Giá hiện tại {_vn_tick(val.price)}")
    if val.target_price:
        ax.axvline(val.target_price, color=NAVY, lw=1.4, label=f"Giá mục tiêu {_vn_tick(val.target_price)}")
    ax.xaxis.set_major_formatter(_vn_tick)
    ax.set_title("Biên độ giá trị theo phương pháp (đ/cp, bi quan – lạc quan)")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(axis="y", visible=False)
    return _encode(fig)


def macro_history(history: dict[str, pd.Series]) -> str | None:
    g, c = history.get("gdp_growth"), history.get("cpi")
    if (g is None or g.empty) and (c is None or c.empty):
        return None
    plt = _setup()
    fig, ax = plt.subplots(figsize=(5.6, 2.3))
    if g is not None and not g.empty:
        g = g[g.index >= g.index.max() - 10]
        ax.bar([str(i) for i in g.index], g.values, color=NAVY, label="Tăng trưởng GDP (%)", width=0.6)
    if c is not None and not c.empty:
        c = c[c.index >= c.index.max() - 10]
        ax.plot([str(i) for i in c.index], c.values, color=GOLD, marker="o", ms=3.5, lw=1.4,
                label="Lạm phát CPI (%)")
    ax.set_title("Việt Nam: tăng trưởng GDP và lạm phát")
    ax.legend(fontsize=7, loc="upper left", ncol=2)
    return _encode(fig)


def technical_chart(ohlcv: pd.DataFrame, symbol: str, stop=None, target=None) -> str | None:
    if ohlcv is None or len(ohlcv) < 80:
        return None
    _setup()
    from .technical import candlestick_png

    png = candlestick_png(ohlcv, symbol, stop_loss=stop, target=target, bars=160)
    return "data:image/png;base64," + base64.b64encode(png).decode()
