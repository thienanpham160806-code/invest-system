"""Pipeline top-down: Vi mo -> Nganh -> Doanh nghiep -> Dinh gia -> Khuyen nghi -> PDF.

    from invest_system.pipeline import analyze, run
    ctx = analyze("FPT")                    # chi phan tich (dict ket qua)
    pdf_path = run("FPT", sections=[...])   # phan tich + xuat PDF
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analysis import composite as comp
from .analysis.macro import analyze_macro
from .analysis.ratios import compute_ratios, growth_summary
from .analysis.sector import analyze_sector, metrics_for
from .analysis.sentiment import analyze_news
from .analysis.valuation import value_company
from .config import get_settings, now_local
from .data import prices
from .data.company import load_company, load_news, macro_headlines
from .data.fundamentals import load_financials
from .data.macro import load_macro
from .logging_conf import get_logger
from .provenance import SourceLog
from .validation import checks

log = get_logger(__name__)

ALL_SECTIONS = ["macro", "sector", "company", "valuation", "technical", "news", "appendix"]
SECTION_LABELS = {
    "macro": "Tổng quan vĩ mô", "sector": "Phân tích ngành", "company": "Phân tích doanh nghiệp",
    "valuation": "Định giá", "technical": "Phân tích kỹ thuật", "news": "Tin tức & cảm xúc",
    "appendix": "Phụ lục dữ liệu",
}


def _fintext(symbol: str, fin_raw_bundle=None) -> tuple[str | None, list[str]]:
    """Text mining BCTC PDF neu nhom dat file vao data/reports/<MA>/ (tai su dung fintext.py)."""
    from .analysis import fintext
    from .config import PROJECT_ROOT

    folder = PROJECT_ROOT / "data" / "reports" / symbol.upper()
    pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
    if not pdfs:
        return None, []
    try:
        text = fintext.extract_text(pdfs[-1])
        if fintext.is_scanned_text(text):
            return f"File {pdfs[-1].name} là bản scan — cần OCR để text mining.", []
        audit = fintext.audit_opinion(text)
        hits = fintext.risk_keywords(text)
        risks = sorted({f"Thuyết minh BCTC nhắc tới '{h.keyword}' ({h.group})." for h in hits})
        opinion = audit.get("opinion") or "chưa nhận diện được"
        para = (f"Text mining BCTC ({pdfs[-1].name}): ý kiến kiểm toán {opinion}; "
                f"{len(hits)} lần xuất hiện từ khóa rủi ro trong thuyết minh.")
        return para, list(risks)[:3]
    except Exception as exc:  # noqa: BLE001
        log.warning("fintext loi: %s", exc)
        return None, []


def analyze(symbol: str, years: int | None = None, sections: list[str] | None = None) -> dict:
    s = get_settings()
    symbol = symbol.strip().upper()
    years = years or s.get("analysis.default_years", 5)
    src = SourceLog()
    sections = sections or ALL_SECTIONS

    info = load_company(symbol, src)
    ohlcv = prices.get_ohlcv(symbol, s.get("analysis.price_history_days", 730), src)
    bench = prices.get_benchmark(symbol, s.get("analysis.price_history_days", 730), src)
    bench_name = "Chỉ số mẫu (giả lập)" if info.is_demo else "VN-Index"
    fin = load_financials(symbol, info.exchange, years)
    if not fin.empty:
        src.add(f"BCTC năm {symbol}", fin.source, fin.last_year(),
                note=f"{len(fin.years)} năm")
    else:
        src.fail(f"BCTC năm {symbol}", "; ".join(fin.notes))

    shares = info.shares_outstanding
    target_metrics = metrics_for(symbol, fin, ohlcv, info.company_type, shares)
    shares = target_metrics.get("shares") or shares
    ratios = compute_ratios(fin, info.company_type)
    growth = growth_summary(fin, info.company_type) if not fin.empty else {}

    # Vi mo -> nganh
    macro_data = load_macro(src, demo_mode=info.is_demo)
    macro_res = analyze_macro(macro_data, info.company_type)
    rf = None
    bond = macro_data.latest.get("gov_bond_10y")
    if bond:
        rf = bond["value"] / 100

    sector_res = analyze_sector(info, target_metrics, ohlcv, bench,
                                s.get("analysis.max_peers", 6), src)
    beta = prices.beta(ohlcv, bench)
    price_now = target_metrics.get("price")
    val = value_company(fin, info.company_type, price_now, shares, ratios,
                        sector_res.quantiles, beta, rf)

    # Ky thuat (tai su dung analysis/technical.py cua bot)
    tech = None
    if ohlcv is not None and len(ohlcv) >= 120:
        try:
            from .analysis.technical import recommend

            tech = recommend(ohlcv, symbol)
        except Exception as exc:  # noqa: BLE001
            log.warning("technical loi: %s", exc)

    news = load_news(info, 180, src)
    as_of = pd.Timestamp(ohlcv["time"].iloc[-1]) if not ohlcv.empty else pd.Timestamp.now()
    sent = analyze_news(news, as_of)
    fintext_para, fintext_risks = _fintext(symbol)

    # Kiem tra du lieu
    vchecks = (checks.check_financials(fin, info.company_type)
               + checks.check_prices(ohlcv, info.exchange,
                                     as_of if info.is_demo else None)
               + checks.cross_check(fin, ratios, target_metrics.get("pe")))

    scores = {
        "macro": macro_res.sector_score,
        "sector": sector_res.score,
        "quality": comp.quality_score(ratios, info.company_type),
        "growth": comp.growth_score(growth),
        "valuation": comp.valuation_score(val.upside),
        "technical": comp.technical_score(tech.total_score if tech else None),
        "sentiment": sent.score_100 if news else None,
    }
    result = comp.combine(scores, val.upside)

    ctx = {
        "symbol": symbol, "info": info, "company_type": info.company_type,
        "ohlcv": ohlcv, "bench": bench, "bench_name": bench_name,
        "price_summary": prices.returns_summary(ohlcv), "beta": beta,
        "fin": fin, "ratios": ratios, "growth": growth, "metrics": target_metrics,
        "macro_data": macro_data, "macro": macro_res, "sector": sector_res,
        "valuation": val, "technical": tech, "news": news, "sentiment": sent,
        "macro_news": [] if info.is_demo else macro_headlines()[:6],
        "fintext_commentary": fintext_para, "fintext_risks": fintext_risks,
        "checks": vchecks, "checks_summary": checks.summarize(vchecks),
        "composite": result, "sources": src, "sections": sections, "years": years,
        "generated_at": now_local(), "is_demo": info.is_demo,
    }
    comp.build_thesis_and_risks(ctx, result)
    return ctx


def run(symbol: str, sections: list[str] | None = None, years: int | None = None,
        template: str = "full", out_dir: str | Path | None = None,
        engine: str | None = None) -> tuple[Path, dict]:
    """Phan tich va xuat bao cao. Tra ve (duong dan file, ctx)."""
    from .report.builder import build_html
    from .report.render import render_pdf

    ctx = analyze(symbol, years, sections)
    html = build_html(ctx, template=template)
    s = get_settings()
    out = Path(out_dir or s.get("report.output_dir", "outputs/reports"))
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{ctx['symbol']}_{ctx['generated_at']:%Y%m%d_%H%M}_{template}"
    path = render_pdf(html, out / f"{stem}.pdf", engine or s.get("report.pdf_engine", "auto"))
    return path, ctx
