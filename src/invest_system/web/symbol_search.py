"""Shared ranking rules for stock ticker search."""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

_LEGAL_WORDS = {"cong", "ty", "co", "phan", "tap", "doan", "ctcp", "jsc", "joint", "stock"}


def normalize_search(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.replace("đ", "d").replace("Đ", "D").lower()).strip()


def rank_symbol_rows(frame: pd.DataFrame, query: str, exchange: str = "ALL") -> pd.DataFrame:
    """Filter exchange first, then rank symbol, brand/abbreviation and company name."""
    q = normalize_search(query)
    if not q:
        return frame.iloc[0:0]
    ex = exchange.strip().upper()
    rows = frame if ex == "ALL" else frame[frame["exchange"].astype(str).str.upper() == ex]
    q_compact = q.replace(" ", "")
    matches: list[tuple[int, float, str, int]] = []
    for pos, row in enumerate(rows.itertuples(index=False)):
        symbol = str(getattr(row, "symbol", "")).upper()
        brand = normalize_search(getattr(row, "brand", ""))
        name = normalize_search(getattr(row, "name", ""))
        sym_compact = normalize_search(symbol).replace(" ", "")
        tier = None
        if sym_compact == q_compact:
            tier = 0
        elif sym_compact.startswith(q_compact):
            tier = 1
        elif q_compact in sym_compact:
            tier = 2
        else:
            brand_compact = brand.replace(" ", "")
            if brand_compact.startswith(q_compact):
                tier = 3
            else:
                words = [w for w in name.split() if w not in _LEGAL_WORDS]
                if any(w.startswith(q) for w in words):
                    tier = 4
                elif q in name or q in brand:
                    tier = 5
        if tier is not None:
            cap = pd.to_numeric(getattr(row, "market_cap", 0), errors="coerce")
            matches.append((tier, -float(cap) if pd.notna(cap) else 0.0, symbol, pos))
    if len(q_compact) <= 3 and any(tier <= 2 for tier, _, _, _ in matches):
        matches = [m for m in matches if m[0] <= 2]
    ordered = [pos for _, _, _, pos in sorted(matches)]
    return rows.iloc[ordered]
