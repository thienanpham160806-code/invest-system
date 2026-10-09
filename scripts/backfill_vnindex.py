"""VN-Index day du (>= 6 nam) cho backtest -> $DATA_DIR/backtest/vnindex.parquet.

    DATA_DIR=./data-phase2 python scripts/backfill_vnindex.py --sessions 2600

Mot request Vietcap gap-chart (giu .agent-coord/locks/vnstock.lock). Doi chieu phan
trung voi webdata/snapshot/vnindex.parquet: lech dong cua > 0,1% -> dung, khong ghi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_bctc_quarterly import acquire, release  # noqa: E402

from invest_system.config import get_paths  # noqa: E402
from invest_system.web import service  # noqa: E402
from invest_system.web.universe import load_vnindex_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=2600)
    args = ap.parse_args()
    out = get_paths().data_dir / "backtest" / "vnindex.parquet"
    acquire(f"VN-Index {args.sessions} phiên cho backtest (1 request gap-chart)")
    try:
        frame = service._gap_chart("VNINDEX", args.sessions)
    finally:
        release()
    if frame is None or frame.empty:
        raise SystemExit("Không lấy được VN-Index")
    snap = load_vnindex_snapshot()
    both = frame.merge(snap[["time", "close"]], on="time", suffixes=("", "_snap"))
    if not both.empty:
        both["gap"] = (both["close"] - both["close_snap"]).abs() / both["close_snap"]
        print(f"Đối chiếu {len(both)} phiên trùng với snapshot: lệch tối đa {both['gap'].max():.4%}")
        worst = both.nlargest(5, "gap")[["time", "close", "close_snap", "gap"]]
        print(worst.to_string(index=False))
        if both["gap"].max() > 0.001:
            rejected = out.with_name("vnindex_rejected.parquet")
            out.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(rejected, index=False)
            raise SystemExit(f"Lệch > 0,1% so với snapshot - không ghi ({rejected} để kiểm tra)")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame[["time", "open", "high", "low", "close", "volume"]].to_parquet(out, index=False)
    print(f"Ghi {out}: {len(frame)} phiên {frame['time'].min():%d/%m/%Y} → {frame['time'].max():%d/%m/%Y}")


if __name__ == "__main__":
    main()
