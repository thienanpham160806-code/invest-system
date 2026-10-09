from __future__ import annotations

import httpx

from invest_system.data.dnse import _DnseRestClient


def test_dnse_rest_signs_market_data_requests_and_preserves_official_paths():
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"data": []})

    client = _DnseRestClient("key", "secret", "https://openapi.dnse.com.vn", "2026-05-07")
    client.http.close()
    client.http = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        status, body = client.get_ohlc("STOCK", {
            "symbol": "FPT", "resolution": "1D", "from": 1, "to": 2,
        })
        assert status == 200 and httpx.Response(200, text=body).json() == {"data": []}
        request = captured[-1]
        assert request.url.path == "/price/ohlc"
        assert request.url.params["type"] == "STOCK"
        assert request.url.params["symbol"] == "FPT"
        assert request.headers["x-api-key"] == "key"
        assert request.headers["version"] == "2026-05-07"
        assert request.headers["x-signature"].startswith('Signature keyId="key"')
        assert request.headers["date"]

        client.get_instruments(market_id="UPX", limit=100, page=1)
        request = captured[-1]
        assert request.url.path == "/market/instruments"
        assert request.url.params["marketId"] == "UPX"
        assert request.url.params["page"] == "1"
    finally:
        client.http.close()
