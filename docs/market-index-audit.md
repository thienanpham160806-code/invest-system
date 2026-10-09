# Vietcap index symbol audit

Probe: `POST https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart`, timeframe `ONE_DAY`, `countBack=5`, 2026-10-09 (UTC timestamps in the response map to 2026-10-09 Vietnam time).

| Request symbol | HTTP | Response symbol | Last close | Result |
|---|---:|---|---:|---|
| `VNINDEX` | 200 | `VNINDEX` | 1735.09 | Use as VN-Index |
| `HNXIndex` | 200 | `HNXIndex` | 261.60 | Use as HNX-Index |
| `HNXUpcomIndex` | 200 | `HNXUpcomIndex` | 124.67 | Use as UPCOM-Index |
| `HNXINDEX` | 200 | no item | — | Unsupported spelling |
| `UPCOMINDEX` | 200 | no item | — | Unsupported spelling |
| `UpcomIndex` | 200 | no item | — | No Vietcap gap-chart item |

The response objects included `symbol`, `o`, `h`, `l`, `c`, `v`, `t`, `accumulatedVolume`, and `accumulatedValue`. The live ribbon uses the three exact response symbols, rejects response-symbol mismatches, hides unavailable or duplicate secondary values, and reports them as unavailable.
