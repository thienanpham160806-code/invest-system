import pandas as pd

from invest_system.analysis.fintext import (
    audit_opinion,
    generate_commentary,
    risk_keywords,
    segment_sections,
    trend_analysis,
)


def test_audit_opinion_classifies_chap_nhan_toan_phan():
    text = "Theo ý kiến của chúng tôi, báo cáo tài chính đã trình bày trung thực và hợp lý."
    result = audit_opinion(text)
    assert result["opinion"] == "chấp nhận toàn phần"


def test_audit_opinion_classifies_ngoai_tru():
    text = "Chúng tôi đưa ra ý kiến ngoại trừ về khoản mục hàng tồn kho nêu trên."
    result = audit_opinion(text)
    assert result["opinion"] == "ngoại trừ"


def test_audit_opinion_classifies_tu_choi():
    text = "Chúng tôi từ chối đưa ra ý kiến do không thu thập được đầy đủ bằng chứng."
    result = audit_opinion(text)
    assert result["opinion"] == "từ chối"


def test_audit_opinion_classifies_trai_nguoc():
    text = "Theo ý kiến trái ngược của chúng tôi, báo cáo tài chính không phản ánh đúng thực tế."
    result = audit_opinion(text)
    assert result["opinion"] == "trái ngược"


def test_audit_opinion_none_when_no_match():
    result = audit_opinion("Day la mot doan van khong lien quan den kiem toan.")
    assert result["opinion"] is None


def test_audit_opinion_matches_diacritics_stripped_text():
    """PDF trich xuat doi khi MAT DAU (loi font/encoding) - audit_opinion() phai
    van nhan dien duoc, va evidence tra ve VAN CO DAU (tu tu dien goc, khong
    phai ban da bo dau dung de so khop noi bo)."""
    text = "Theo y kien cua chung toi, bao cao tai chinh da trinh bay trung thuc va hop ly."
    result = audit_opinion(text)
    assert result["opinion"] == "chấp nhận toàn phần"
    assert result["evidence"] == "trình bày trung thực và hợp lý"


def test_audit_opinion_matches_diacritics_stripped_text_containing_d_with_hook():
    """Rieng truong hop nay con kiem tra ky tu 'd' (khong dau) khop duoc voi
    'đ' (co dau) trong "từ chối đưa ra ý kiến" - "đ" KHONG tach duoc bang NFD
    thong thuong nhu cac nguyen am co dau khac (no la mot chu cai rieng trong
    khoi Latin Extended-A, khong phai "d" + dau ket hop), can xu ly rieng."""
    text = "Chung toi tu choi dua ra y kien do khong thu thap duoc day du bang chung."
    result = audit_opinion(text)
    assert result["opinion"] == "từ chối"


def test_risk_keywords_detects_going_concern_group():
    text = (
        "Ban Tổng Giám đốc cho biết có nghi ngờ đáng kể về khả năng hoạt động "
        "liên tục của Công ty do lỗ luỹ kế lớn tính đến cuối năm."
    )
    hits = risk_keywords(text)
    groups = {h.group for h in hits}
    assert "hoat_dong_lien_tuc" in groups
    assert any("nghi ngờ đáng kể" in h.sentence for h in hits)


def test_risk_keywords_detects_multiple_groups_in_one_paragraph():
    text = (
        "Công ty đang có nợ quá hạn thanh toán với một số ngân hàng. "
        "Ngoài ra, Công ty đang trong quá trình tranh chấp hợp đồng với một khách hàng lớn."
    )
    hits = risk_keywords(text)
    groups = {h.group for h in hits}
    assert "no_va_thanh_khoan" in groups
    assert "phap_ly" in groups


def test_risk_keywords_matches_diacritics_stripped_text():
    """PDF trich xuat mat dau - risk_keywords() phai van nhan dien duoc tu
    khoa, va Hit.sentence tra ve la CAU GOC (mat dau, dung nhu van ban dau
    vao) - khong bi "sua lai" thanh ban co dau gia tao."""
    text = (
        "Ban Tong Giam doc cho biet co nghi ngo dang ke ve kha nang hoat dong "
        "lien tuc cua Cong ty do lo luy ke lon tinh den cuoi nam."
    )
    hits = risk_keywords(text)
    groups = {h.group for h in hits}
    assert "hoat_dong_lien_tuc" in groups
    # sentence tra ve dung ban goc (mat dau) - khong bi thay the boi ban co dau
    assert any("nghi ngo dang ke" in h.sentence for h in hits)


def test_risk_keywords_empty_when_no_keyword_present():
    hits = risk_keywords("Doanh thu va loi nhuan cua cong ty deu tang truong tot trong nam.")
    assert hits == []


def test_segment_sections_finds_known_headings():
    text = (
        "BÁO CÁO CỦA KIỂM TOÁN ĐỘC LẬP\nNội dung ý kiến kiểm toán ở đây.\n\n"
        "BẢNG CÂN ĐỐI KẾ TOÁN\nSố liệu cân đối kế toán ở đây.\n\n"
        "THUYẾT MINH BÁO CÁO TÀI CHÍNH\nCác thuyết minh chi tiết ở đây."
    )
    sections = segment_sections(text)
    assert "y_kien_kiem_toan" in sections
    assert "bang_can_doi" in sections
    assert "thuyet_minh" in sections
    assert "kiểm toán" in sections["y_kien_kiem_toan"].lower()


def _financials(revenues, net_incomes, cfos=None, years=(2021, 2022, 2023)):
    income = pd.DataFrame({"year": list(years), "netRevenue": revenues, "netIncome": net_incomes})
    cashflow = (
        pd.DataFrame({"year": list(years), "cfo": cfos}) if cfos is not None else pd.DataFrame()
    )
    return {
        "income": income, "balance": pd.DataFrame(),
        "cashflow": cashflow, "ratios": pd.DataFrame(),
    }


def test_trend_analysis_computes_revenue_cagr_and_margins():
    financials = _financials(
        revenues=[100.0, 121.0, 144.0], net_incomes=[10.0, 12.0, 15.0]
    )
    result = trend_analysis(financials)

    assert result["years"] == [2021, 2022, 2023]
    assert abs(result["revenue_cagr"] - 0.20) < 1e-6  # 100 -> 144 qua 2 nam = 20%/nam
    assert result["net_margin_by_year"][2023] == 15.0 / 144.0


def test_trend_analysis_flags_low_earnings_quality():
    financials = _financials(
        revenues=[100.0, 110.0, 120.0],
        net_incomes=[10.0, 10.0, 10.0],
        cfos=[2.0, 2.0, 2.0],  # CFO/LNST = 0.2, rat thap
    )
    result = trend_analysis(financials)
    assert result["cfo_to_ni_avg"] < 0.8


def test_trend_analysis_missing_data_reports_note_not_fabricated():
    financials = {"income": pd.DataFrame(), "balance": pd.DataFrame(), "cashflow": pd.DataFrame()}
    result = trend_analysis(financials)
    assert result["years"] == []
    assert "revenue_cagr" not in result
    assert len(result["notes"]) > 0


def test_generate_commentary_cites_numbers_and_years():
    financials = _financials(
        revenues=[100.0, 121.0, 144.0], net_incomes=[10.0, 12.0, 15.0], cfos=[9.0, 11.0, 14.0]
    )
    trend = trend_analysis(financials)
    audit = audit_opinion("Bao cao da trinh bay trung thuc va hop ly.")
    hits = risk_keywords("Doanh thu tang truong tot, khong co dau hieu bat thuong.")

    commentary = generate_commentary("FPT", audit, hits, trend)

    assert "FPT" in commentary
    assert "2023" in commentary
    assert "20.0%" in commentary or "20,0%" in commentary  # revenue CAGR ~20%/nam


def test_generate_commentary_leads_with_exception_opinion():
    audit = audit_opinion("Chúng tôi đưa ra ý kiến ngoại trừ về một số khoản mục.")
    commentary = generate_commentary("ABC", audit, [], {"years": []})
    first_section = commentary.split("<b>2.")[0]
    assert "NGOẠI TRỪ" in first_section
