"""Cam xuc tin tuc doanh nghiep bang TU DIEN tai chinh tieng Viet.

Cung tinh than Loughran-McDonald (tu dien chuyen nganh, khong dung tu dien
cam xuc pho thong): moi tieu de dem so tu tich cuc / tieu cuc, diem tin =
(P - N) / (P + N), diem tong = trung binh co trong so thoi gian (tin moi nang
hon, ban ky 30 ngay). Dau ra kem cac tu khoa khop -> giai thich duoc.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..data.fundamentals import strip_accents

POSITIVE = [
    "tang truong", "lai ky luc", "loi nhuan tang", "vuot ke hoach", "hoan thanh ke hoach",
    "co tuc", "chia thuong", "mo rong", "khoi cong", "trung thau", "ky hop dong", "hop tac",
    "nang hang", "nang tin nhiem", "phuc hoi", "tang von", "mua vao", "dong von ngoai",
    "khoi ngoai mua", "dot pha", "ky luc", "thang loi", "cai thien", "tich cuc", "giam no",
    "tang manh", "lai lon", "xuat khau tang", "don hang moi", "nhan room",
]
NEGATIVE = [
    "thua lo", "lo rong", "bao lo", "lai giam", "loi nhuan giam", "sut giam", "giam manh",
    "khoi to", "bat giam", "dieu tra", "xu phat", "bi phat", "vi pham", "cham cong bo",
    "canh bao", "kiem soat", "dinh chi", "huy niem yet", "no xau", "cham tra", "vo no",
    "giai chap", "ban thao", "khoi ngoai ban", "tranh chap", "kien tung", "ngung hoat dong",
    "ngoai tru", "y kien kiem toan", "khong dat", "giam von", "ap luc", "rui ro",
    "lo luy ke", "tam dung", "thu hoi",
]


@dataclass
class SentimentResult:
    score: float | None = None          # -1..1
    score_100: float | None = None      # 0..100
    items: list[dict] = field(default_factory=list)  # tin + diem + tu khop
    n_pos: int = 0
    n_neg: int = 0


def score_title(title: str) -> tuple[float, list[str], list[str]]:
    norm = strip_accents(title)
    pos = [w for w in POSITIVE if w in norm]
    neg = [w for w in NEGATIVE if w in norm]
    # "lai giam"/"loi nhuan giam" chua "giam" - khong dem trung "tang truong" trong cung cum
    total = len(pos) + len(neg)
    return ((len(pos) - len(neg)) / total if total else 0.0), pos, neg


def analyze_news(news: list[dict], as_of: pd.Timestamp | None = None) -> SentimentResult:
    res = SentimentResult()
    if not news:
        return res
    as_of = as_of or pd.Timestamp.now()
    num = den = 0.0
    for item in news:
        sc, pos, neg = score_title(item["title"])
        ts = pd.Timestamp(item["published_at"])
        ts = ts.tz_localize(None) if ts.tzinfo else ts
        age = max((as_of - ts).days, 0)
        w = 0.5 ** (age / 30)
        if pos or neg:
            num += w * sc
            den += w
        res.n_pos += bool(pos) and sc > 0
        res.n_neg += bool(neg) and sc < 0
        res.items.append({**item, "published_at": ts, "sentiment": sc, "pos": pos, "neg": neg})
    if den > 0:
        res.score = float(num / den)
        res.score_100 = float(np.clip(50 + 40 * res.score, 0, 100))
    else:
        res.score, res.score_100 = 0.0, 50.0
    return res
