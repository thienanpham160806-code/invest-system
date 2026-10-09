"""Giao dien web (Streamlit): chon ma, chon muc, xem nhanh ket qua, tai PDF.

    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from invest_system import fmt  # noqa: E402
from invest_system.analysis.composite import GROUP_LABELS, RATING_COLORS  # noqa: E402
from invest_system.pipeline import ALL_SECTIONS, SECTION_LABELS, analyze  # noqa: E402
from invest_system.report.builder import build_html  # noqa: E402
from invest_system.report.render import render_pdf  # noqa: E402

st.set_page_config(page_title="Phân tích cơ hội đầu tư cổ phiếu", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def _analyze(symbol: str, years: int):
    return analyze(symbol, years)


def _sidebar():
    st.sidebar.header("Thiết lập báo cáo")
    ticker = st.sidebar.text_input("Mã cổ phiếu", "DEMO", help="VD: FPT, VCB, HPG. 'DEMO'/'DEMOB' = dữ liệu mẫu").strip().upper()
    years = st.sidebar.slider("Số năm BCTC", 3, 10, 5)
    sections = st.sidebar.multiselect("Các mục trong PDF", ALL_SECTIONS, default=ALL_SECTIONS,
                                      format_func=lambda k: SECTION_LABELS[k])
    template = st.sidebar.radio("Mẫu báo cáo", ["full", "summary"],
                                format_func=lambda k: "Đầy đủ" if k == "full" else "Tóm tắt (2 trang)")
    go = st.sidebar.button("Phân tích", type="primary", width="stretch")
    return ticker, years, sections, template, go


def _overview(ctx):
    res, val, info = ctx["composite"], ctx["valuation"], ctx["info"]
    if ctx["is_demo"]:
        st.warning("Đang dùng DỮ LIỆU MẪU (giả lập) — chỉ để chạy thử hệ thống.")
    st.subheader(f"{info.symbol} — {info.name or ''}")
    st.caption(f"{info.exchange or '—'} · {info.industry or info.type_label} · phương pháp định giá: {info.type_label}")
    c = st.columns(5)
    color = RATING_COLORS.get(res.rating or "", "#5b6573")
    c[0].markdown(f"<div style='background:{color};color:white;padding:10px;border-radius:6px'>"
                  f"<div style='font-size:12px'>KHUYẾN NGHỊ</div><b style='font-size:22px'>"
                  f"{res.rating or 'N/A'}</b></div>", unsafe_allow_html=True)
    c[1].metric("Giá hiện tại", fmt.price(val.price))
    c[2].metric("Giá mục tiêu", fmt.price(val.target_price), fmt.pct(val.upside, sign=True))
    c[3].metric("Điểm tổng hợp", fmt.num(res.total, 0))
    cs = ctx["checks_summary"]
    c[4].metric("Kiểm tra dữ liệu", f"{cs['passed']}/{cs['total']} đạt",
                f"{cs['warn']} cảnh báo · {cs['fail']} lỗi", delta_color="off")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("**Luận điểm đầu tư**")
        for t in res.thesis:
            st.markdown(f"- {t}")
        st.markdown("**Rủi ro**")
        for r in res.risks:
            st.markdown(f"- {r}")
    with right:
        st.markdown("**Điểm theo nhóm (0–100)**")
        st.bar_chart(pd.DataFrame({"Điểm": {GROUP_LABELS[k]: v for k, v in res.scores.items()}}))


def _tabs(ctx):
    t = st.tabs(["Vĩ mô", "Ngành", "Doanh nghiệp", "Định giá", "Dữ liệu & nguồn"])
    with t[0]:
        for p in ctx["macro"].commentary:
            st.write(p)
        st.dataframe(pd.DataFrame(ctx["macro"].table), width="stretch")
        for n in ctx["macro"].notes:
            st.caption("⚠ " + n)
    with t[1]:
        st.dataframe(ctx["sector"].peers_table, width="stretch")
        if not ctx["sector"].index_series.empty:
            st.line_chart(ctx["sector"].index_series.set_index("time"))
    with t[2]:
        st.dataframe(ctx["ratios"].T, width="stretch")
        st.dataframe((ctx["fin"].frame / 1e9).T.round(0), width="stretch")
    with t[3]:
        val = ctx["valuation"]
        rows = [{"Phương pháp": m.label, "Tỷ trọng": f"{m.weight:.0%}",
                 **{k: fmt.price(v) for k, v in m.values.items()}} for m in val.methods]
        st.dataframe(pd.DataFrame(rows), width="stretch")
        st.json({k: (round(v, 4) if isinstance(v, float) else v) for k, v in val.assumptions.items()})
        for sk in val.skipped:
            st.caption(sk)
    with t[4]:
        st.dataframe(pd.DataFrame([c.to_dict() for c in ctx["checks"]]), width="stretch")
        st.dataframe(pd.DataFrame(ctx["sources"].to_list()), width="stretch")


def main():
    st.title("📈 Hệ thống phân tích cơ hội đầu tư cổ phiếu")
    st.caption("Top-down: Vĩ mô → Ngành → Doanh nghiệp → Định giá theo loại DN → Khuyến nghị → PDF")
    ticker, years, sections, template, go = _sidebar()
    if go:
        st.session_state["ticker"] = ticker
    ticker = st.session_state.get("ticker")
    if not ticker:
        st.info("Nhập mã ở thanh bên trái rồi bấm **Phân tích**. Thử 'DEMO' (DN thường) hoặc 'DEMOB' (ngân hàng) nếu chưa có mạng.")
        return
    with st.spinner(f"Đang thu thập và phân tích {ticker}…"):
        ctx = dict(_analyze(ticker, years))
    ctx["sections"] = sections
    _overview(ctx)
    _tabs(ctx)
    st.divider()
    if st.button("📄 Xuất báo cáo PDF", type="primary"):
        with st.spinner("Đang dựng PDF…"):
            out = Path("outputs/reports")
            path = render_pdf(build_html(ctx, template),
                              out / f"{ticker}_{ctx['generated_at']:%Y%m%d_%H%M}_{template}.pdf")
        mime = "application/pdf" if path.suffix == ".pdf" else "text/html"
        st.download_button("Tải xuống " + path.name, path.read_bytes(), file_name=path.name, mime=mime)
        if path.suffix != ".pdf":
            st.warning("Chưa có engine PDF (WeasyPrint/Playwright) — đã xuất HTML, mở bằng trình duyệt → In → Lưu PDF.")


main()
