import pandas as pd

from invest_system.analysis.sentiment import analyze_news, score_title


def test_score_title_signs():
    assert score_title("Công ty lãi kỷ lục, vượt kế hoạch năm")[0] > 0
    assert score_title("Lãnh đạo bị khởi tố, cổ phiếu bị cảnh báo")[0] < 0


def test_recent_news_weigh_more():
    now = pd.Timestamp("2026-10-01")
    news = [{"title": "lãi kỷ lục", "published_at": now},
            {"title": "thua lỗ nặng", "published_at": now - pd.Timedelta(days=120)}]
    assert analyze_news(news, now).score > 0
