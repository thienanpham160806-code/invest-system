"""Chan doan moi truong chay bot: RAM/CPU that cua container, goi thu nguon du
lieu (Vietcap getAll, gap-chart, DNSE), kho gia va snapshot hien co.

Chay duoc tren may ca nhan lan tren Render:
    python scripts/diagnose.py              # day du, co goi mang
    python scripts/diagnose.py --offline    # bo qua cac kiem tra goi mang

Tren Render goi Free (khong co Shell): go /trangthai chandoan tren Telegram
(cung cac kiem tra nay), hoac tam dat Docker Command cua service thanh
`python scripts/diagnose.py` roi xem tab Logs (nho dat lai lenh chay bot sau).
Ma thoat 1 neu co kiem tra LOI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from invest_system.diagnostics import FAIL, format_table, run_diagnostics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Khong goi thu nguon du lieu")
    args = parser.parse_args()

    checks = run_diagnostics(network=not args.offline)
    print(format_table(checks))
    sys.exit(1 if any(c.status == FAIL for c in checks) else 0)


if __name__ == "__main__":
    main()
