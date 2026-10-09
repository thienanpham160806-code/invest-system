# Vietcap index symbol audit

Date checked: 2026-10-09. Production endpoint: `/api/py/market/live`.

## Findings

The production endpoint returned VN-Index only. HNX-Index and UPCOM-Index were marked unavailable. The previous implementation uppercased every symbol before calling Vietcap. That changed the documented, case-sensitive request symbols `HNXIndex` and `HNXUpcomIndex` into unsupported spellings `HNXINDEX` and `HNXUPCOMINDEX`. It also dropped `accumulatedValue` and therefore displayed no turnover for VN-Index.

The production server response does not include the upstream Vietcap request or response body, so the exact upstream error was not observable from `/api/py/market/live`. A local direct probe was blocked by the execution environment (`WinError 10013`, outbound socket permission denied). `scripts/probe_market_indices.py` records the original payload for all three canonical symbols when run from a network-enabled machine. This is the remaining verification for the upstream error/cache/IP hypotheses.

## Change

- Request the canonical symbols independently and concurrently, preserving their case.
- Validate each close against that same symbol's returned 250-session history; never compare HNX/UPCOM levels with VN-Index.
- Carry `accumulatedVolume` and `accumulatedValue` through the response. Normalize turnover to VND only when the implied value per share is plausible; otherwise leave it unavailable.
- Keep the last valid quote marked stale after a later request fails. A symbol is listed as unavailable only when no valid live or cached quote exists.
- Show a visible `trễ` marker for a stale quote. Source and timestamp remain available in the hover title.

## Verification status

- Production before change: VN-Index present; HNX/UPCOM absent; all three turnover values absent.
- Direct Vietcap raw response: not captured in this environment because outbound Python sockets are denied.
- Automated fixture tests cover canonical-case preservation, parallel index output, own-history validation, turnover unit normalization, and stale fallback.
- Production after change: pending preview verification.
