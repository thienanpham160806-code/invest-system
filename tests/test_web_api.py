"""Test web API bang TestClient tren du lieu dong goi (webdata/), KHONG can mang:
moi lenh goi nguon live (gap-chart, CafeF, RSS) bi chan -> he thong phai tu dung ban chup."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from invest_system.data import arminer_bctc  # noqa: E402
from invest_system.web import service  # noqa: E402

pytestmark = pytest.mark.skipif(not arminer_bctc.PACKED.exists(), reason="chua co webdata")


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setattr(service, "_gap_chart", lambda *a, **k: None)
    mp.setattr(service, "_cafef_topic", lambda *a, **k: [])
    import invest_system.data.macro_news as mn

    mp.setattr(mn, "fetch_all_macro_news", lambda: [])
    import api.index as api

    yield TestClient(api.app)
    mp.undo()


def test_arminer_known_totals():
    fpt = arminer_bctc.from_arminer("FPT")
    vcb = arminer_bctc.from_arminer("VCB")
    assert abs(fpt.get("total_assets", 2025) / 1e9 - 88_142) < 1
    assert abs(vcb.get("total_assets", 2025) / 1e9 - 2_442_279) < 1
    for std in (fpt, vcb):
        y = 2025
        assert abs(std.get("total_liabilities", y) + std.get("equity", y) - std.get("total_assets", y)) < 1e9


def test_arminer_drops_duplicated_year():
    ssi = arminer_bctc.from_arminer("SSI")
    assert any("trùng" in n for n in ssi.notes)
    assert ssi.last_year() == 2024


def test_health_and_universe_invariants(client):
    j = client.get("/api/py/health").json()
    assert j["universe_symbols"] > 1400
    uni, meta = service.load_universe()
    assert uni["symbol"].is_unique
    assert uni.groupby("icb1").size().sum() == len(uni)
    assert meta["checks"]["one_icb4_per_symbol"]


def test_sectors_cover_all_symbols(client):
    for level in (1, 4):
        j = client.get(f"/api/py/sectors?level={level}").json()
        assert j["coverage"]["sum_nodes"] == j["coverage"]["n_symbols"]
        assert all("provenance" in j for _ in [0])
        if level == 1:
            assert len(j["items"]) == 11
            assert j["coverage"]["n_symbols"] == 1522


def test_market_map_covers_full_hierarchy_and_all_symbols(client):
    response = client.get("/api/py/market-map?period=ret_3m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker_count"] == 1522
    assert payload["period"] == "ret_3m"
    assert all(node["children"] for node in payload["items"])
    first_sector = payload["items"][0]
    assert first_sector["slug"].startswith("1-")
    assert first_sector["children"][0]["slug"].startswith("2-")
    assert first_sector["children"][0]["children"][0]["slug"].startswith("3-")


def test_opportunities_endpoint_reads_full_precomputed_ranking(client):
    result = client.get("/api/py/opportunities?limit=10")
    assert result.status_code == 200
    payload = result.json()
    assert payload["ready"] is True
    assert payload["universe_count"] == 1522
    assert payload["analyzed_count"] == 1522
    assert payload["items"] and all(
        r["eligible"] and r["rating"] == "MUA" and r["confidence"] in {"CAO", "TRUNG BÌNH"}
        and r["avg_value_20d"] >= 5e9 and not r["quality_failures"] and r["rank"] > 0
        for r in payload["items"]
    )
    tracking = client.get("/api/py/opportunities?eligible_only=false&limit=2000").json()
    assert any(not row["eligible"] and row["tracking_reasons"] for row in tracking["items"])


def test_pb_roe_adjustment_requires_eight_positive_fit_and_caps_target():
    import pandas as pd

    roe = pd.Series([0.05, 0.08, 0.1, 0.14, 0.18, 0.22, 0.26, 0.30, 0.34, 0.38])
    peers = pd.DataFrame({"pe": None, "pb": 1 + 8 * roe, "roe": roe, "liquidity_flag": True})
    quant = {"pb": (1.5, 2.0, 2.5), "pb_p90": 4.0}
    adjusted, fit = service._pb_roe_adjust(peers, 0.9, quant)
    assert fit and fit["n"] == 10 and fit["r2"] >= 0.1
    assert 1 + 8 * roe.quantile(0.25) <= fit["pb_target"] <= 1 + 8 * roe.quantile(0.9)
    assert adjusted["pb"][0] == quant["pb"][0]
    assert adjusted["pb"][0] <= adjusted["pb"][1] <= quant["pb_p90"]

    rejected, no_fit = service._pb_roe_adjust(peers.head(7), 0.2, quant)
    assert rejected is quant and no_fit is None


def test_symbols_picker_has_exchange_company_and_financial_coverage(client):
    response = client.get("/api/py/symbols?exchange=HOSE")
    assert response.status_code == 200
    assert "s-maxage=3600" in response.headers["cache-control"]
    items = response.json()["items"]
    assert items and all(x["exchange"] == "HOSE" for x in items)
    fpt = next(x for x in items if x["symbol"] == "FPT")
    assert fpt["name"] and fpt["icb1"] and fpt["has_bctc"] is True


def test_search_ranks_tickers_before_names_and_filters_exchange_first():
    import pandas as pd

    from invest_system.web.symbol_search import rank_symbol_rows

    rows = pd.DataFrame([
        {"symbol": "VICEM", "name": "Tập đoàn VICEM", "brand": "VICEM", "exchange": "HNX", "market_cap": 100},
        {"symbol": "VIC", "name": "Tập đoàn Vingroup", "brand": "Vingroup", "exchange": "HOSE", "market_cap": 1000},
        {"symbol": "VNM", "name": "Công ty Cổ phần Sữa Việt Nam", "brand": "Vinamilk", "exchange": "HOSE", "market_cap": 800},
        {"symbol": "HPG", "name": "Công ty Cổ phần Tập đoàn Hòa Phát", "brand": "Hoa Phat", "exchange": "HOSE", "market_cap": 700},
        {"symbol": "VICEM2", "name": "Công ty VICEM 2", "brand": "VICEM", "exchange": "HNX", "market_cap": 90},
    ])
    assert rank_symbol_rows(rows, "vic")["symbol"].tolist() == ["VIC", "VICEM", "VICEM2"]
    assert rank_symbol_rows(rows, "vinamilk").iloc[0]["symbol"] == "VNM"
    assert rank_symbol_rows(rows, "hoa phat").iloc[0]["symbol"] == "HPG"
    assert rank_symbol_rows(rows, "vicem")["symbol"].tolist() == ["VICEM", "VICEM2"]
    assert rank_symbol_rows(rows, "vic", "HNX")["symbol"].tolist() == ["VICEM", "VICEM2"]


def test_live_endpoints_use_short_cache_and_return_session(client, monkeypatch):
    monkeypatch.setattr(service, "_index_live_quote", lambda symbol: {
        "symbol": symbol.upper(), "price": {"VNINDEX": 100.0, "HNXINDEX": 50.0,
        "HNXUPCOMINDEX": 25.0}[symbol.upper()], "change": 1.0, "change_pct": 0.01,
        "volume": 10.0, "turnover": 1_000_000_000.0, "as_of": "2026-10-09", "stale": False,
    })
    market = client.get("/api/py/market/live")
    assert market.status_code == 200 and "s-maxage=10" in market.headers["cache-control"]
    assert market.json()["session"] and market.json()["indices"][0]["symbol"] == "VNINDEX"
    assert [x["symbol"] for x in market.json()["indices"]] == ["VNINDEX", "HNXINDEX", "HNXUPCOMINDEX"]
    assert all(x["turnover"] == 1_000_000_000.0 for x in market.json()["indices"])
    assert market.json()["unavailable_indices"] == []
    quote = client.get("/api/py/stock/FPT/live")
    assert quote.status_code == 200 and quote.json()["symbol"] == "FPT"
    assert "s-maxage=10" in quote.headers["cache-control"]


def test_index_quote_preserves_vietcap_symbol_case_and_uses_own_history(monkeypatch):
    import pandas as pd

    seen = []
    frame = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3),
        "close": [120.0, 121.0, 124.0],
        "accumulated_volume": [100_000_000] * 3,
        "accumulated_value": [2_000_000_000_000] * 3,
    })
    monkeypatch.setattr(service, "_gap_chart", lambda symbol, count: (seen.append((symbol, count)) or frame))
    monkeypatch.setattr(service, "_LIVE_CACHE", {})
    quote = service._index_live_quote("HNXUpcomIndex")
    assert seen == [("HNXUpcomIndex", 260)]
    assert quote["price"] == 124.0
    assert quote["turnover"] == 2_000_000_000_000.0
    assert quote["change"] == 3.0


def test_index_turnover_normalizes_million_vnd_and_rejects_bad_data():
    assert service._index_turnover_vnd(2_000_000, 100_000_000) == 2_000_000_000_000
    assert service._index_turnover_vnd(2_000_000_000_000, 100_000_000) == 2_000_000_000_000
    assert service._index_turnover_vnd(0, 100_000_000) is None


def test_bctc_coverage_api_reports_market_exchanges(client):
    data = client.get("/api/py/bctc-coverage").json()
    assert data["listed_total"] == 1522
    assert data["by_exchange"]["UPCOM"]["missing_count"] == data["by_exchange"]["UPCOM"]["listed"]
    assert data["by_exchange"]["HOSE"]["missing_count"] == len(data["missing"]["HOSE"])


def test_missing_secondary_index_live_data_never_reuses_vnindex_snapshot(monkeypatch):
    import pandas as pd

    import invest_system.data.vietcap as vietcap
    import invest_system.web.universe as web_universe

    service._LIVE_CACHE.pop("HNXINDEX", None)
    monkeypatch.setattr(vietcap, "fetch_daily_bars", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(web_universe, "load_ohlcv_snapshot", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(web_universe, "load_vnindex_snapshot", lambda: pytest.fail("must not reuse VN-Index snapshot"))
    quote = service._live_quote("HNXINDEX", is_index=True)
    assert quote["price"] is None and quote["stale"] is True


def test_sector_detail_lists_all_members(client):
    j = client.get("/api/py/sectors?level=2").json()
    node = j["items"][0]
    d = client.get(f"/api/py/sectors/{node['slug']}").json()
    assert len(d["members"]) == node["n_symbols"]


def test_macro_api_returns_openai_narrative_when_configured(client, monkeypatch):
    monkeypatch.setattr(service, "analyze_macro_narrative", lambda ctx: ["Tóm tắt vĩ mô từ OpenAI."])
    response = client.get("/api/py/macro?world_bank=false")
    assert response.status_code == 200
    assert response.json()["commentary"] == ["Tóm tắt vĩ mô từ OpenAI."]


def test_stock_analysis_bank_and_nonfin(client):
    for sym, ctype in (("FPT", "NON_FINANCIAL"), ("VCB", "BANK")):
        r = client.get(f"/api/py/stock/{sym}/analysis?news=false")
        assert r.status_code == 200
        j = r.json()
        assert j["company_type"] == ctype
        assert j["provenance"]["source"]
        assert j["bctc_available"]
        keys = {m["key"] for m in j["valuation"]["methods"]}
        if ctype == "BANK":
            assert "dcf_fcff" not in keys and "ev_ebitda" not in keys
        assert j["sources"]


def test_upcom_without_bctc_says_why(client):
    j = client.get("/api/py/stock/ACV/analysis?news=false").json()
    assert j["bctc_available"] is False
    assert j["recommendation"]["target_price"] is None
    p = client.get("/api/py/stock/ACV/profile").json()
    assert p["bctc_note"]


def test_financials_and_404(client):
    j = client.get("/api/py/stock/FPT/financials?statement=bs&years=3").json()
    assert len(j["years"]) == 3 and j["rows"]
    assert client.get("/api/py/stock/ZZZZ/profile").status_code == 404
