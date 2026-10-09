from invest_system.news_matching import match_reason


def test_ticker_search_requires_exact_token_and_context_for_ambiguous_codes():
    assert match_reason("VIC", "VIC công bố kế hoạch đầu tư") == "mã cổ phiếu xuất hiện độc lập"
    assert match_reason("VIC", "VICEM huy động vốn") is None
    assert match_reason("GAS", "GAS prices rise globally") is None
    assert match_reason("GAS", "Cổ phiếu GAS tăng giá") is not None
    assert match_reason("CEO", "Thu nhập của loạt CEO công ty chứng khoán") is None
    assert match_reason("IDC", "Becamex IDC lãi quý I") is None
    assert match_reason("IDC", "Cổ phiếu IDC chốt quyền cổ tức") is not None
    assert match_reason("ART", "Chứng khoán BOS (ART) không thể tiến hành ĐHĐCĐ") is not None
    assert match_reason("FPT", "FPT công bố kết quả", "", "Công ty Cổ phần FPT")


def test_company_name_matches_without_accents_but_macro_does_not_match_ticker():
    assert match_reason("HPG", "Hoa Phat announces new factory", name="Công ty Cổ phần Hòa Phát")
    assert match_reason("FPT", "Lạm phát toàn cầu tiếp tục giảm", "") is None

