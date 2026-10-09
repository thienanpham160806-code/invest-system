from invest_system.analysis import fintext
from scripts.audit_report_numbers import compare_pdf_text


def _record(**values):
    defaults = {
        "price": 57_900,
        "shares": 1_714_326_422,
        "market_cap": 99_259_499_833_800,
        "revenue_fy": 70_112_825_100_710,
        "net_income_parent_fy": 9_376_127_629_501,
        "total_assets": 88_141_991_634_625,
        "total_liabilities": 44_393_950_887_086,
        "equity": 43_748_040_747_539,
        "target_base": 80_600,
        "upside": 0.392055,
        "confidence": "TRUNG BÌNH",
    }
    defaults.update(values)
    return {"symbol": "FPT", "company_type": "NON_FINANCIAL", "values": defaults}


def test_pdf_audit_matches_headlines_and_skips_unprinted_statement_values(tmp_path, monkeypatch):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "FPT.pdf").touch()
    text = (
        "Giá hiện tại 57.900 Giá mục tiêu 80.600 Upside +39,2% "
        "Vốn hoá 99,3 nghìn tỷ Số CP 1.714.326.422 "
        "Độ tin cậy định giá: TRUNG BÌNH. "
        "PASS Tổng TS = Nợ phải trả + VCSH khớp 6/6 năm"
    )
    monkeypatch.setattr(fintext, "extract_text", lambda path: text)

    result = compare_pdf_text(pdf_dir, [_record()])["FPT"]

    assert result["status"] == "PASS"
    assert result["failures"] == []
    assert result["checks"]["equity_identity"] == "PASS"
    assert result["checks"]["revenue_fy"] == "SKIP"
    assert result["checks"]["total_assets"] == "SKIP"


def test_pdf_audit_does_not_match_numbers_without_their_labels(tmp_path, monkeypatch):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "FPT.pdf").touch()
    monkeypatch.setattr(fintext, "extract_text", lambda path: "57.900 80.600 1.714.326.422 88.142 44.394")

    result = compare_pdf_text(pdf_dir, [_record()])["FPT"]

    assert result["status"] == "FAIL"
    assert "price" in result["failures"]
    assert "market_cap" in result["failures"]


def test_pdf_audit_accepts_company_scale_market_cap_rounding(tmp_path, monkeypatch):
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    (pdf_dir / "FPT.pdf").touch()
    values = _record(market_cap=1_750_373_039_739_500)["values"]
    text = "Giá hiện tại 225.500 Vốn hoá 1,8 triệu tỷ Số CP 7.762.186.429"
    monkeypatch.setattr(fintext, "extract_text", lambda path: text)

    result = compare_pdf_text(pdf_dir, [{"symbol": "FPT", "company_type": "NON_FINANCIAL", "values": values}])["FPT"]

    assert result["checks"]["market_cap"] == "PASS"
