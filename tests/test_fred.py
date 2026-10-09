"""Client FRED: API co key, CSV khong key, cache 1 ngay, cache cu khi mat mang. Khong goi mang."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from invest_system.config import Paths
from invest_system.data import cache, fred


class FakeResponse:
    def __init__(self, json_data=None, text="", status=200):
        self._json, self.text, self.status_code = json_data, text, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if self.error:
            raise self.error
        return self.response


API_PAYLOAD = {"observations": [
    {"date": "2026-10-05", "value": "5.20"},
    {"date": "2026-10-06", "value": "."},        # ngay nghi: FRED ghi "."
    {"date": "2026-10-07", "value": "5.28"},
]}
CSV_TEXT = "observation_date,DGS10\n2026-10-05,5.20\n2026-10-06,\n2026-10-07,5.28\n"


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    paths = Paths(data_dir=tmp_path, cache_db=tmp_path / "cache.sqlite3", model_dir=tmp_path)
    monkeypatch.setattr(cache, "get_paths", lambda: paths)
    monkeypatch.delenv("FRED_API_KEY", raising=False)


def test_series_catalog_uses_verified_ids_and_no_dxy():
    ids = {s.series_id for s in fred.SERIES.values()}
    assert ids == {"FEDFUNDS", "DFF", "DGS10", "DTWEXBGS", "DCOILBRENTEU", "VIXCLS"}
    assert "DXY" not in ids
    assert "DXY" in fred.SERIES["usd_broad"].note


def test_api_with_key_parses_and_drops_missing():
    session = FakeSession(FakeResponse(API_PAYLOAD))
    result = fred.FredClient(api_key="k", session=session).get("ust_10y")
    url, params = session.calls[0]
    assert url == fred.API_URL and params["series_id"] == "DGS10" and params["api_key"] == "k"
    assert params["file_type"] == "json"
    assert list(result.values) == [5.20, 5.28]
    assert result.last_date == pd.Timestamp("2026-10-07")
    assert result.source == "FRED API" and not result.stale


def test_key_read_from_env(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "env-key")
    session = FakeSession(FakeResponse(API_PAYLOAD))
    fred.FredClient(session=session).get("ust_10y")
    assert session.calls[0][1]["api_key"] == "env-key"


def test_without_key_uses_public_csv():
    session = FakeSession(FakeResponse(text=CSV_TEXT))
    result = fred.FredClient(session=session).get("ust_10y")
    assert session.calls[0][0] == fred.CSV_URL and session.calls[0][1]["id"] == "DGS10"
    assert list(result.values) == [5.20, 5.28] and result.source == "FRED CSV"


def test_invalid_csv_is_error_not_numbers():
    session = FakeSession(FakeResponse(text="<!DOCTYPE html><html>not found</html>"))
    with pytest.raises(fred.FredError):
        fred.FredClient(session=session).get("ust_10y")


def test_api_error_message_raises():
    session = FakeSession(FakeResponse({"error_code": 400, "error_message": "Bad api_key"}))
    with pytest.raises(fred.FredError, match="Bad api_key"):
        fred.FredClient(api_key="bad", session=session).get("vix")


def test_cache_hit_within_one_day_skips_network():
    first = FakeSession(FakeResponse(API_PAYLOAD))
    fred.FredClient(api_key="k", session=first).get("ust_10y")
    second = FakeSession(error=AssertionError("không được gọi mạng"))
    result = fred.FredClient(api_key="k", session=second).get("ust_10y")
    assert second.calls == [] and result.source == "FRED (cache)"
    assert list(result.values) == [5.20, 5.28]


def test_expired_cache_refetches(monkeypatch):
    fred.FredClient(api_key="k", session=FakeSession(FakeResponse(API_PAYLOAD))).get("ust_10y")
    real_time = time.time
    monkeypatch.setattr(cache.time, "time", lambda: real_time() + fred.CACHE_MAX_AGE + 60)
    session = FakeSession(FakeResponse(API_PAYLOAD))
    fred.FredClient(api_key="k", session=session).get("ust_10y")
    assert len(session.calls) == 1


def test_network_error_falls_back_to_stale_cache(monkeypatch):
    fred.FredClient(api_key="k", session=FakeSession(FakeResponse(API_PAYLOAD))).get("ust_10y")
    real_time = time.time
    monkeypatch.setattr(cache.time, "time", lambda: real_time() + 3 * fred.CACHE_MAX_AGE)
    result = fred.FredClient(api_key="k", session=FakeSession(error=ConnectionError("down"))).get("ust_10y")
    assert result.stale and "cache cũ" in result.source
    assert list(result.values) == [5.20, 5.28]


def test_network_error_without_cache_raises():
    with pytest.raises(fred.FredError):
        fred.FredClient(api_key="k", session=FakeSession(error=ConnectionError("down"))).get("brent")


def test_get_all_isolates_failures():
    class PerSeries(FakeSession):
        def get(self, url, params=None, timeout=None):
            if params["series_id"] == "VIXCLS":
                raise ConnectionError("down")
            return FakeResponse(API_PAYLOAD)

    results, errors = fred.FredClient(api_key="k", session=PerSeries()).get_all(["ust_10y", "vix"])
    assert set(results) == {"ust_10y"} and set(errors) == {"vix"}


def test_unknown_key():
    with pytest.raises(KeyError):
        fred.FredClient(api_key="k", session=FakeSession()).get("dxy")


def test_cache_write_failure_does_not_break(monkeypatch):
    def broken(*_a, **_k):
        raise OSError("read-only fs")

    monkeypatch.setattr(cache, "write_frame", broken)
    result = fred.FredClient(api_key="k", session=FakeSession(FakeResponse(API_PAYLOAD))).get("ust_10y")
    assert list(result.values) == [5.20, 5.28]
