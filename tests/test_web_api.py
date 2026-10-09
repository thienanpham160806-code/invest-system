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


def test_sector_detail_lists_all_members(client):
    j = client.get("/api/py/sectors?level=2").json()
    node = j["items"][0]
    d = client.get(f"/api/py/sectors/{node['slug']}").json()
    assert len(d["members"]) == node["n_symbols"]


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
