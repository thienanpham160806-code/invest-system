"""LNST CD me 4 QUY GAN NHAT (TTM) cho cac ma thanh khoan cao - chay tren may co vnstock.

BCTC arminer chi co NAM -> P/E theo FY. Script nay goi vnstock (Vietcap) BCTC quy cho
top N ma HSX/HNX theo GTGD TB20, cong 4 quy gan nhat -> webdata/snapshot/ttm.parquet.
Tong 4 quy khong phu thuoc thu tu hang (tranh loi dao hang cua vnstock, xem vietcap.py).
Chi nhan khi co DU 4 quy lien tiep; thieu -> bo qua (web hien P/E FY).

    python scripts/build_ttm.py --top 120
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.data.vietcap import VietcapProvider, _parent_profit_column  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR  # noqa: E402


def _qkey(p: str) -> tuple[int, int] | None:
    try:
        y, q = str(p).split("-Q")
        return int(y), int(q)
    except ValueError:
        return None


def _consecutive(keys: list[tuple[int, int]]) -> bool:
    idx = [y * 4 + q for y, q in keys]
    return idx == list(range(idx[0], idx[0] + len(idx)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=120)
    ap.add_argument("--sleep", type=float, default=3.5)
    args = ap.parse_args()
    uni = pd.read_parquet(SNAPSHOT_DIR / "market_universe.parquet")
    cand = uni[uni["has_bctc"].fillna(False)].sort_values("avg_value_20d", ascending=False).head(args.top)
    out_path = SNAPSHOT_DIR / "ttm.parquet"
    old = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame(columns=["symbol"])
    cand = cand[~cand["symbol"].isin(old["symbol"])]  # chay tiep (vnstock community gioi han ~20 req/phut)
    prov = VietcapProvider()
    rows, fails = [], []
    for i, sym in enumerate(cand["symbol"], 1):
        try:
            inc = prov.income_statement(sym, period="quarter")
            col = _parent_profit_column(inc)
            if col is None or inc.empty:
                raise ValueError("không có cột LNST CĐ mẹ")
            frame = inc[["period", col]].copy()
            frame["k"] = frame["period"].map(_qkey)
            frame = frame.dropna(subset=["k"]).sort_values("k").tail(4)
            keys = list(frame["k"])
            if len(keys) < 4 or not _consecutive(keys):
                raise ValueError(f"không đủ 4 quý liên tiếp: {list(frame['period'])}")
            vals = pd.to_numeric(frame[col], errors="coerce")
            if vals.isna().any():
                raise ValueError("thiếu số quý")
            y, q = keys[-1]
            rows.append({"symbol": sym, "ni_ttm": float(vals.sum()), "ttm_label": f"TTM Q{q}/{y}",
                         "ttm_periods": ",".join(frame["period"]), "ttm_column": f"vnstock income_statement(quarter).{col}",
                         "ttm_fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M")})
        except (Exception, SystemExit) as exc:  # noqa: BLE001
            fails.append((sym, str(exc)[:120]))
        if i % 20 == 0:
            print(f"{i}/{len(cand)} ok={len(rows)} fail={len(fails)}", flush=True)
        time.sleep(args.sleep)
    out = pd.concat([old, pd.DataFrame(rows)], ignore_index=True).drop_duplicates("symbol", keep="last")
    out.to_parquet(out_path, index=False)
    print(f"Xong: {len(out)} mã có TTM, {len(fails)} lỗi")
    for f in fails[:15]:
        print("  ", f)


if __name__ == "__main__":
    main()
