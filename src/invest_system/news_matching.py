"""Conservative ticker-to-headline matching shared by RSS consumers."""
from __future__ import annotations

import re
import unicodedata

AMBIGUOUS = {"VND", "GAS", "CEO", "POW", "BID", "PET", "HOT", "ART", "IDC"}
CONTEXT = re.compile(r"\b(co phieu|ma|ticker|shares|equity)\b", re.I)
GENERIC = re.compile(r"\b(công ty cổ phần|công ty cp|công ty|tập đoàn|ngân hàng thương mại cổ phần|ngân hàng|ctcp|jsc|group)\b", re.I)


def normalize(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", value.lower())).strip()


def match_reason(symbol: str, title: str, body: str = "", name: str | None = None,
                 brand: str | None = None) -> str | None:
    text = f"{title or ''} {body or ''}"
    upper = text.upper()
    ticker = re.escape(symbol.upper())
    if re.search(rf"\((?:HOSE|HSX|HNX|UPCOM)\s*:\s*{ticker}\)", upper):
        return "mã sàn trong ngoặc"
    if re.search(rf"\b(?:CHỨNG KHOÁN|TẬP ĐOÀN|NGÂN HÀNG|CÔNG TY)\b[^\n]{{0,50}}\(\s*{ticker}\s*\)", upper):
        return "mã trong ngoặc sau tên doanh nghiệp"
    if re.search(rf"\bMÃ\s+{ticker}\b|\bCỔ PHIẾU\s+{ticker}\b|\bCHỨNG KHOÁN\s+{ticker}\b", upper):
        return "mã được nêu kèm ngữ cảnh chứng khoán"
    match = re.search(rf"\b{ticker}\b", upper)
    if match:
        nearby = normalize(upper[max(0, match.start() - 45):match.end() + 45])
        if symbol.upper() not in AMBIGUOUS or CONTEXT.search(nearby):
            return "mã cổ phiếu xuất hiện độc lập"
    normalized_text = f" {normalize(text)} "
    for label, value in (("thương hiệu", brand), ("tên doanh nghiệp", name)):
        candidate = normalize(GENERIC.sub(" ", value or ""))
        if len(candidate) >= 5 and f" {candidate} " in normalized_text:
            return f"khớp {label} không dấu"
    return None
