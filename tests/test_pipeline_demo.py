"""Smoke test toan pipeline tren du lieu GIA LAP (khong can mang)."""
from invest_system.pipeline import run


def test_demo_pipeline_html(tmp_path):
    path, ctx = run("DEMO", out_dir=tmp_path, engine="html")
    html = path.read_text(encoding="utf-8")
    assert "DỮ LIỆU MẪU" in html
    assert ctx["composite"].rating is not None
    assert ctx["valuation"].target_price > 0
    assert ctx["checks_summary"]["fail"] == 0


def test_demo_bank_pipeline_summary(tmp_path):
    path, ctx = run("DEMOB", sections=["valuation", "appendix"], template="summary",
                    out_dir=tmp_path, engine="html")
    assert ctx["company_type"] == "BANK"
    assert path.exists()
