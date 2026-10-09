"""Tao file mau data/manual/<MA>_financials.csv de nhom nhap BCTC bang tay
(khi vnstock / vnfinancialdata khong co ma do). Don vi: VND.

    python scripts/make_manual_template.py FPT
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from invest_system.data.fundamentals import FIELD_LABELS_VI, MANUAL_DIR, STANDARD_FIELDS  # noqa: E402


def main(symbol: str) -> None:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    path = MANUAL_DIR / f"{symbol.upper()}_financials.csv"
    cols = ["year"] + STANDARD_FIELDS + ["pe", "pb"]
    frame = pd.DataFrame({"year": [2021, 2022, 2023, 2024, 2025]}).reindex(columns=cols)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Đã tạo {path}. Mỗi cột là một chỉ tiêu (VND):")
    for k in STANDARD_FIELDS:
        print(f"  {k:24s} {FIELD_LABELS_VI.get(k, '')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ABC")
