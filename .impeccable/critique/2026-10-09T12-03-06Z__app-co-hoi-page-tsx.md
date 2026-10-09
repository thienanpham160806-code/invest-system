---
target: opportunity ranking page and market treemap
total_score: 25
max_score: 40
na_heuristics:
p0_count: 0
p1_count: 3
target_identity: "file:C:\\Users\\Dell\\invest-system\\app\\co-hoi\\page.tsx"
target_fingerprint: "sha256:b7b6188a39325dc4a0285ef66440b2b99bedbb3bfe7385f2ebf8e2b99f43a87c"
target_path: "C:\\Users\\Dell\\invest-system\\app\\co-hoi\\page.tsx"
timestamp: 2026-10-09T12-03-06Z
slug: app-co-hoi-page-tsx
---
# Impeccable critique — opportunity ranking and market treemap

Method: dual-agent (A: /root/critique_design · B: /root/critique_detector)

## Design health — Operate

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of System Status | 3/4 | Loading, errors, snapshot date, and empty states are present but not equally prominent. |
| 2 | Match System / Real World | 3/4 | Vietnamese exchange/financial context fits; ICB, BCTC, and GTGD need short explanations. |
| 3 | User Control and Freedom | 3/4 | Search, filters, sorting, export, and treemap breadcrumbs; no quick filter reset before polish. |
| 4 | Consistency and Standards | 3/4 | Shared card/table patterns; sort and row navigation had incomplete keyboard semantics. |
| 5 | Error Prevention | 2/4 | Duplicate liquidity inputs shared the same state and request parameter. |
| 6 | Recognition Rather Than Recall | 3/4 | Snapshot and source are visible; score/confidence meanings are not stated near results. |
| 7 | Flexibility and Efficiency | 3/4 | Practical filters, CSV, and sorting; many choices are exposed simultaneously. |
| 8 | Aesthetic and Minimalist Design | 2/4 | Restrained blue/slate style suits research, but homepage has many equally weighted sections. |
| 9 | Error Recovery | 2/4 | Error and empty states exist, with no inline retry action. |
| 10 | Help and Documentation | 1/4 | The buy caveat helps; methodology and terminology guidance are thin. |
| **Total** | | **25/40** | Usable foundation; density and decision support are the main opportunity. |

## Design specificity

VN equity terms, exchange symbols, ICB sectors, BCTC, market-cap sizing, and snapshot dates ground this in Vietnamese stock research. The restrained analytical visual language is appropriate. Its card-and-table structure remains fairly interchangeable with a generic market dashboard. The user requested a restrained polish and only a light/dark control, so the existing visual structure should remain.

The deterministic detector returned `[]` (0 findings) for `app/co-hoi/page.tsx`. Independent source review found a duplicate liquidity control and accessibility gaps not surfaced by the detector. No false positives were identified. Browser inspection and overlay injection were unavailable because this session exposes no browser automation; no local server was started.

## Overall impression

The interface gives useful market context and provenance, but asks users to interpret a dense set of controls and ranking outputs without enough methodology nearby. Fix clarity and keyboard access while retaining the current dashboard.

## What is working

- Exchange, index, industry, accounting, and market-cap context makes the product locally relevant.
- Data sources, as-of dates, and the non-advice caveat help users judge freshness and risk.
- Ranking search, filters, export, and treemap drill-down support practical analysis.

## Priority issues

1. **[P1] Too many filters at once.** The opportunity page exposes search, exchange, industry, rating, confidence, upside, liquidity, market cap, tabs, and CSV together. This slows scanning. Preserve the current layout per user scope; use concise labels, a reset action, and clear eligibility methodology rather than redesigning the page.
2. **[P1] Incomplete keyboard semantics in the shared table.** Clickable sort headers were plain `<th>` handlers; rows were focusable but not semantic links and only supported Enter. Keyboard users cannot reliably sort or navigate. Use real buttons for sorting and keep a semantic stock link as the keyboard navigation point.
3. **[P1] Treemap color lacked a readable key.** The page said color represented performance but had no scale; small tiles also hid details. Add a compact red/neutral/green legend and a native tooltip for name, return, market cap, and group count.
4. **[P2] Ranking logic was not explained next to results.** Users could not infer how score, upside, liquidity, confidence, and data checks combine. State the ranking formula and eligibility threshold in one short sentence.
5. **[P2] Homepage hierarchy is flat over a long scroll.** Many market sections compete equally. This is intentionally left structurally unchanged to honor the user's request not to overwork the UI.

## Persona red flags

- **Alex, power user:** sort headers and row navigation were not reliably keyboard-operable; the extra liquidity input repeated a filter.
- **Jordan, first-time investor:** ICB/BCTC/GTGD and confidence/score terms lack short definitions where results appear.
- **Careful investor:** source/date metadata is present, but rank rationale and treemap color range were not immediately legible.

## Minor observations

- The ranking page already has loading, error, and empty states and wraps filters on narrow screens.
- The homepage's “Vì sao?” disclosure is a useful pattern for explaining a score without adding permanent text.
- Browser-level visual, contrast, and layout checks remain unverified because browser automation was unavailable.

## Questions considered

The user has already narrowed polish to a restrained light/dark toggle and asked not to overwork the interface. Keep structural redesign out of scope.
