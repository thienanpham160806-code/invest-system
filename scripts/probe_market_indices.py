"""Probe canonical Vietcap index symbols and preserve raw responses for audit."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from invest_system.data.vietcap import probe_endpoint


SYMBOLS = ("VNINDEX", "HNXIndex", "HNXUpcomIndex")


def probe(symbol: str) -> dict:
    status, body, error = probe_endpoint(
        "POST",
        "/chart/OHLCChart/gap-chart",
        {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": int(time.time()), "countBack": 260},
        timeout=8,
    )
    return {"request_symbol": symbol, "http_status": status, "error": error, "response": body}


def main() -> None:
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as pool:
        results = list(pool.map(probe, SYMBOLS))
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
