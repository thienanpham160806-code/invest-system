"""VN-Index day du (>= 6 nam) cho backtest -> $DATA_DIR/backtest/vnindex.parquet.

    DATA_DIR=./data-phase2 python scripts/backfill_vnindex.py --sessions 2600

Mot request Vietcap gap-chart (giu .agent-coord/locks/vnstock.lock). Doi chieu phan
trung voi webdata/snapshot/vnindex.parquet: lech dong cua > 0,1% -> dung, khong ghi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

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
    ap.add_argument("--from-file", type=Path, default=None,
                    help="dung file da tai (vd vnindex_rejected.parquet) thay vi goi mang")
    args = ap.parse_args()
    out = get_paths().data_dir / "backtest" / "vnindex.parquet"
    if args.from_file:
        frame = pd.read_parquet(args.from_file)
    else:
        acquire(f"VN-Index {args.sessions} phiên cho backtest (1 request gap-chart)")
        try:
            frame = service._gap_chart("VNINDEX", args.sessions)
        finally:
            release()
    if frame is None or frame.empty:
        raise SystemExit("Không lấy được VN-Index")
    snap = load_vnindex_snapshot()
    # Phien cuoi cua snapshot co the chup trong phien (chua chot) -> bao cao, khong dung de tu choi.
    both = frame.merge(snap[["time", "close"]], on="time", suffixes=("", "_snap"))
    both["gap"] = (both["close"] - both["close_snap"]).abs() / both["close_snap"]
    last_snap = snap["time"].max()
    settled = both[both["time"] < last_snap]
    if not both.empty:
        print(f"Đối chiếu {len(both)} phiên trùng với snapshot: lệch tối đa {settled['gap'].max():.4%} "
              f"(trừ phiên cuối snapshot {last_snap:%d/%m/%Y}: lệch {both.loc[both['time'] == last_snap, 'gap'].max():.4%})")
        if settled["gap"].max() > 0.001:
            rejected = out.with_name("vnindex_rejected.parquet")
            out.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(rejected, index=False)
            print(settled.nlargest(5, "gap")[["time", "close", "close_snap", "gap"]].to_string(index=False))
            raise SystemExit(f"Lệch > 0,1% so với snapshot - không ghi ({rejected} để kiểm tra)")
    out.parent.mkdir(parents=True, exist_ok=True)
    frame[["time", "open", "high", "low", "close", "volume"]].to_parquet(out, index=False)
    print(f"Ghi {out}: {len(frame)} phiên {frame['time'].min():%d/%m/%Y} → {frame['time'].max():%d/%m/%Y}")


if __name__ == "__main__":
    main()
