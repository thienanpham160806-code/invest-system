"""Kiem thu cache gia cua data/router.py: khong duoc tra ve ban cache NGAN hon
khoang thoi gian duoc hoi (loi cu: backtest 6 thang lay nham VN-Index 3 thang)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from invest_system.config import Paths
from invest_system.data import cache, market_store, router


class FakeProvider:
    def __init__(self):
        self.calls: list[date] = []

    def ohlcv(self, symbol, start, end, resolution="1D"):
        self.calls.append(start)
        days = pd.bdate_range(start, end)
        return pd.DataFrame({
            "time": days, "open": 1.0, "high": 1.0, "low": 1.0,
            "close": range(1, len(days) + 1), "volume": 1.0,
        })


@pytest.fixture
def fake_router(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache, "get_paths", lambda: paths)
    monkeypatch.setattr(market_store, "get_paths", lambda: paths)
    cache.init_db()
    provider = FakeProvider()
    data_router = router.DataRouter()
    data_router._price_names = ["fake"]
    data_router._instances = {"fake": provider}
    return data_router, provider


def test_longer_request_refetches_instead_of_returning_short_cache(fake_router):
    data_router, provider = fake_router
    end = date(2026, 9, 25)
    three_months = data_router.ohlcv("VNINDEX", end - timedelta(days=90), end)
    six_months = data_router.ohlcv("VNINDEX", end - timedelta(days=180), end)

    assert len(provider.calls) == 2
    assert len(six_months) > len(three_months) * 1.8
    assert six_months["time"].iloc[0].date() <= end - timedelta(days=175)


def test_shorter_request_is_served_from_cache(fake_router):
    data_router, provider = fake_router
    end = date(2026, 9, 25)
    data_router.ohlcv("VNINDEX", end - timedelta(days=180), end)
    short = data_router.ohlcv("VNINDEX", end - timedelta(days=30), end)

    assert len(provider.calls) == 1
    assert short["time"].iloc[0].date() >= end - timedelta(days=30)
