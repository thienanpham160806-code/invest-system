"""Vi mo quoc te (FRED): thay doi 1T/3T/1N, z, do nhay theo nganh, gop 70/30, khong lot vao backtest."""
import pandas as pd
import pytest

from invest_system.analysis import macro_intl as mi
from invest_system.analysis.macro import MacroResult
from invest_system.data.fred import SERIES, FredResult


def _series(start_value, end_value, days=400):
    idx = pd.bdate_range(end="2026-10-07", periods=days)
    return pd.Series(pd.Series(range(days), dtype=float).to_numpy() * (end_value - start_value) / (days - 1)
                     + start_value, index=idx)


def _result(key, values):
    return FredResult(key, SERIES[key], values, "FRED CSV")


def test_describe_rates_in_points_others_in_percent():
    rate = mi.describe("ust_10y", _series(4.0, 5.0))
    assert rate["change_unit"] == "điểm %" and rate["value"] == pytest.approx(5.0)
    assert 0 < rate["chg_3m"] < rate["chg_1y"] < 1.0                 # tang deu: 3T < 1N, don vi diem %
    brent = mi.describe("brent", _series(100.0, 125.0))
    assert brent["change_unit"] == "%" and 0 < brent["chg_1m"] < brent["chg_3m"] < brent["chg_1y"] < 0.25
    assert 50 <= len(brent["spark"]) <= 54 and brent["spark"][-1]["v"] == pytest.approx(125.0)


def test_describe_short_history_has_no_one_year_change():
    short = mi.describe("vix", _series(15, 20, days=40))
    assert short["chg_1y"] is None and short["chg_1m"] is not None


def test_z_scores_level_and_change_are_clipped():
    vix = {"value": 40.0}
    assert mi._z("vix", vix) == 2.0                                   # (40-18)/6 > 2 -> cat
    assert mi._z("usd_broad", {"value": 120, "chg_3m": -0.03}) == pytest.approx(-1.0)
    assert mi._z("brent", {"value": 100, "chg_3m": None}) is None


def test_scores_and_sector_overrides():
    results = {"fed_funds": _result("fed_funds", _series(3.0, 3.0)), "ust_10y": _result("ust_10y", _series(4, 4)),
               "usd_broad": _result("usd_broad", _series(120, 120)), "vix": _result("vix", _series(18, 18)),
               "brent": _result("brent", _series(80, 120))}             # dau tang manh, cac bien khac trung tinh
    oil = mi.analyze_international(results, "NON_FINANCIAL", "Dầu khí")
    travel = mi.analyze_international(results, "NON_FINANCIAL", "Du lịch và Giải trí")
    plain = mi.analyze_international(results, "NON_FINANCIAL")
    assert oil.sector_score > plain.sector_score > travel.sector_score
    assert oil.score == plain.score < 50                               # diem chung khong phu thuoc nganh
    assert len(oil.rows) == 5 and all(r["reading"] for r in oil.rows)
    assert any("DXY" in r["note"] for r in oil.rows if r["key"] == "usd_broad")
    assert "Bối cảnh quốc tế" in oil.commentary[-1]


def test_blend_weights_and_fallbacks():
    domestic = MacroResult(score=60.0, sector_score=70.0, commentary=["trong nước"])
    intl = mi.IntlResult(score=40.0, sector_score=30.0, commentary=["quốc tế"])
    mixed = mi.blend(domestic, intl, weight=0.3)
    assert mixed.score == pytest.approx(0.7 * 60 + 0.3 * 40)
    assert mixed.sector_score == pytest.approx(0.7 * 70 + 0.3 * 30)
    assert mixed.parts["domestic"]["weight"] == pytest.approx(0.7)
    assert mixed.parts["international"]["score"] == 40.0
    assert mixed.commentary == ["trong nước", "quốc tế"]
    only_dom = mi.blend(domestic, None, weight=0.3)
    assert only_dom.score == 60.0 and any("FRED" in n for n in only_dom.notes)
    no_dom = mi.blend(MacroResult(score=None, sector_score=None), intl, weight=0.3)
    assert no_dom.sector_score == 30.0
    assert domestic.score == 60.0                                      # khong sua doi tuong goc


def test_default_weight_from_settings():
    assert mi.intl_weight() == pytest.approx(0.30)


def test_service_macro_exposes_both_parts(monkeypatch):
    from invest_system.web import service

    results = {k: _result(k, _series(v, v)) for k, v in
               {"fed_funds": 3.0, "ust_10y": 4.0, "usd_broad": 120, "brent": 80, "vix": 18}.items()}
    monkeypatch.setattr(service, "_intl_macro", lambda: (results, {}))
    out = service.macro("BANK", world_bank=False)
    assert out["international"]["score"] == pytest.approx(50.0)
    assert set(out["parts"]) == {"domestic", "international"}
    dom = out["parts"]["domestic"]["score"]
    assert out["score"] == pytest.approx(0.7 * dom + 0.3 * 50.0)


def test_backtest_never_sees_current_fred(monkeypatch):
    from invest_system.backtest.history import History
    from invest_system.web import service

    called = []
    monkeypatch.setattr(service, "_intl_macro", lambda: called.append(1) or None)
    days = pd.bdate_range("2026-01-05", periods=5)
    ohlcv = pd.DataFrame({"symbol": "AAA", "time": days, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0,
                          "volume": 1.0})
    base = pd.DataFrame([{"symbol": "AAA", "exchange": "HOSE", "icb1": "X", "icb2": "X", "icb3": "X", "icb4": "X",
                          "company_type": "NON_FINANCIAL", "shares": 1.0}])
    hist = History(base, ohlcv, ohlcv[["time", "open", "high", "low", "close", "volume"]], symbols_with_annual=[])
    with hist.patched_service(days[-1], hist.universe_as_of(days[-1])) as svc:
        assert svc._intl_macro() is None
    assert called == []
