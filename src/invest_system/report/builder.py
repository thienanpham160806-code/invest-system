"""Gom ket qua phan tich -> context Jinja2 -> HTML bao cao kieu CTCK."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import fmt
from ..analysis.composite import GROUP_LABELS, RATING_COLORS
from ..analysis.ratios import BANK_KEYS, NONFIN_KEYS, RATIO_LABELS
from ..charts import report_charts as ch
from ..config import PROJECT_ROOT, get_settings
from ..data.fundamentals import FIELD_LABELS_VI
from ..narrative import llm
from ..narrative import templates as nt
from ..pipeline import SECTION_LABELS

TEMPLATE_DIR = Path(__file__).parent / "templates"
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"

NONFIN_TABLE = ["revenue", "gross_profit", "operating_profit", "pbt", "net_income",
                "net_income_parent", "total_assets", "total_liabilities", "equity", "cash",
                "short_debt", "long_debt", "cfo", "capex"]
BANK_TABLE = ["net_interest_income", "fee_income", "total_operating_income", "operating_expense",
              "provision", "pbt", "net_income_parent", "loans", "deposits", "total_assets", "equity"]


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR),
                      autoescape=select_autoescape(["html"]))
    env.filters.update({"num": fmt.num, "pct": fmt.pct, "price": fmt.price, "bn": fmt.bn,
                        "times": fmt.times, "ratio": fmt.fmt_ratio})
    return env


def _fin_table(fin, company_type: str) -> dict:
    if fin.empty:
        return {"years": [], "rows": []}
    keys = BANK_TABLE if company_type == "BANK" else NONFIN_TABLE
    rows = []
    for k in keys:
        s = fin.series(k)
        if s.empty or s.isna().all():
            continue
        rows.append({"label": FIELD_LABELS_VI.get(k, k),
                     "cells": [fmt.bn(s.get(y)) for y in fin.years],
                     "source": fin.mapping.get(k, "")})
    return {"years": fin.years, "rows": rows}


def _ratio_table(ratios: pd.DataFrame, company_type: str) -> dict:
    if ratios is None or ratios.empty:
        return {"years": [], "rows": []}
    keys = BANK_KEYS if company_type == "BANK" else NONFIN_KEYS
    rows = []
    for k in keys:
        if k not in ratios.columns:
            continue
        label, kind = RATIO_LABELS[k]
        rows.append({"label": label, "cells": [fmt.fmt_ratio(ratios.loc[y, k], kind)
                                                for y in ratios.index]})
    return {"years": list(ratios.index), "rows": rows}


def build_context(ctx: dict, template: str = "full") -> dict:
    s = get_settings()
    info, val, res = ctx["info"], ctx["valuation"], ctx["composite"]
    ctype = ctx["company_type"]
    sections = [x for x in ctx["sections"] if x in SECTION_LABELS]
    if template == "summary":
        sections = [x for x in sections if x in ("valuation", "appendix")]
    m = ctx["metrics"]
    ps = ctx["price_summary"]
    side_stats = [
        ("Giá hiện tại (đ)", fmt.price(m.get("price"))),
        ("Ngày giá", ps["last_date"].strftime("%d/%m/%Y") if ps.get("last_date") is not None else "N/A"),
        ("Vốn hóa (tỷ đ)", fmt.bn(m.get("market_cap"))),
        ("SL CP lưu hành (tr)", fmt.num((m.get("shares") or 0) / 1e6) if m.get("shares") else "N/A"),
        ("KLGD TB 20 phiên", fmt.num(ps.get("avg_volume_20d"))),
        ("Cao/thấp 52 tuần", f"{fmt.price(ps.get('high_52w'))} / {fmt.price(ps.get('low_52w'))}"),
        ("P/E (FY gần nhất)", fmt.times(m.get("pe"), 1)),
        ("P/B", fmt.times(m.get("pb"), 2)),
        ("ROE", fmt.pct(m.get("roe"))),
        ("Beta (2 năm, tuần)", fmt.num(ctx.get("beta"), 2)),
        ("Biến động 1T / 3T / 1N", f"{fmt.pct(ps.get('ret_1m'), sign=True)} / "
                                   f"{fmt.pct(ps.get('ret_3m'), sign=True)} / "
                                   f"{fmt.pct(ps.get('ret_1y'), sign=True)}"),
    ]
    ratio_keys = ([("nim", "NIM"), ("roe", "ROE"), ("credit_cost", "Chi phí tín dụng"), ("cir", "CIR")]
                  if ctype == "BANK" else
                  [("gross_margin", "Biên gộp"), ("net_margin", "Biên ròng"), ("roe", "ROE"), ("roa", "ROA")])
    sector = ctx["sector"]
    peers = sector.peers_table.copy()
    charts = {
        "price": ch.price_vs_benchmark(ctx["ohlcv"], ctx["bench"], info.symbol, ctx["bench_name"]),
        "radar": ch.radar(res.scores, GROUP_LABELS),
        "fin": ch.financial_bars(ctx["fin"], ctype),
        "ratios": ch.ratio_trends(ctx["ratios"], ratio_keys, "Hiệu quả hoạt động (%)"),
        "peers": (ch.peers_scatter(peers, "roe", "pb", "ROE (%)", "P/B (lần)",
                                   "Tương quan P/B – ROE trong nhóm ngành")
                  if "pb" in peers else None),
        "sector": ch.sector_vs_bench(sector.index_series, info.industry or info.type_label,
                                     ctx["bench_name"]),
        "football": ch.football_field(val),
        "macro": ch.macro_history(ctx["macro_data"].history),
        "technical": ch.technical_chart(ctx["ohlcv"], info.symbol,
                                        ctx["technical"].stop_loss if ctx["technical"] else None,
                                        ctx["technical"].target if ctx["technical"] else None)
        if "technical" in sections else None,
    }
    peer_rows = []
    for _, r in peers.iterrows():
        peer_rows.append({"symbol": r["symbol"], "is_target": bool(r.get("is_target")),
                          "price": fmt.price(r.get("price")), "mcap": fmt.bn(r.get("market_cap")),
                          "pe": fmt.times(r.get("pe"), 1), "pb": fmt.times(r.get("pb"), 2),
                          "ev_ebitda": fmt.times(r.get("ev_ebitda"), 1),
                          "roe": fmt.pct(r.get("roe")), "ni_cagr": fmt.pct(r.get("ni_cagr")),
                          "ret_1y": fmt.pct(r.get("ret_1y"), sign=True)})
    med = {k: sector.medians.get(k) for k in ("pe", "pb", "ev_ebitda", "roe", "ni_cagr", "net_margin", "nim")}
    narratives = {
        "macro": llm.polish("Vĩ mô", ctx["macro"].commentary),
        "sector": llm.polish("Ngành", nt.sector_paragraphs(ctx)),
        "company": llm.polish("Doanh nghiệp", nt.company_paragraphs(ctx)),
        "valuation": nt.valuation_paragraphs(ctx),
        "technical": nt.technical_paragraphs(ctx),
    }
    method_rows = [{"label": mth.label, "weight": mth.weight,
                    "bear": mth.values.get("bear"), "base": mth.values.get("base"),
                    "bull": mth.values.get("bull"),
                    "inputs": "; ".join(f"{k}: {_fmt_input(k, v)}" for k, v in mth.inputs.items())}
                   for mth in val.methods]
    rating = res.rating or "CHƯA ĐỦ DỮ LIỆU"
    return {
        "ctx": ctx, "info": info, "sections": sections, "section_labels": SECTION_LABELS,
        "template": template, "author": s.get("report.author", ""),
        "org": s.get("report.organization", "INVEST SYSTEM"),
        "rating": rating, "rating_color": RATING_COLORS.get(rating, "#5b6573"),
        "val": val, "res": res, "side_stats": side_stats, "charts": charts,
        "fin_table": _fin_table(ctx["fin"], ctype), "ratio_table": _ratio_table(ctx["ratios"], ctype),
        "peer_rows": peer_rows, "medians": med, "narratives": narratives,
        "scenarios": nt.scenario_rows(val), "method_rows": method_rows,
        "group_labels": GROUP_LABELS, "macro_table": ctx["macro"].table,
        "checks": [c.to_dict() for c in ctx["checks"]], "checks_summary": ctx["checks_summary"],
        "sources": ctx["sources"].to_list(), "source_summary": ctx["sources"].summary(),
        "news": ctx["sentiment"].items[:10], "macro_news": ctx["macro_news"],
        "font_dir": FONT_DIR.as_uri(), "is_demo": ctx["is_demo"],
        "generated_at": ctx["generated_at"].strftime("%d/%m/%Y %H:%M"),
        "tech": ctx["technical"], "mapping": ctx["fin"].mapping,
    }


def _fmt_input(key: str, v) -> str:
    if isinstance(v, str):
        return v
    k = key.lower()
    if any(t in k for t in ("wacc", "ke", "kd", "roe", "tăng trưởng", "g bền")):
        return fmt.pct(v)
    if any(t in k for t in ("p/e", "p/b", "ev/")):
        return fmt.times(v, 2)
    if any(t in k for t in ("eps", "bvps")):
        return fmt.price(v) + " đ"
    if abs(v) > 1e8:
        return fmt.bn(v) + " tỷ đ"
    return fmt.num(v, 2)


def build_html(ctx: dict, template: str = "full") -> str:
    return _env().get_template("report.html").render(**build_context(ctx, template))
