"""LNST CD me 4 QUY GAN NHAT (TTM) tu BCTC quy VCI raw - khong goi mang.

Thay scripts/build_ttm.py (vnstock che do final gan nham nhan quy, xem
.agent-coord/reviews/finding-claude-ttm-vnstock-quarter-labels.md). Dau vao:
data/reference/bctc_quarterly.parquet (scripts/fetch_bctc_quarterly.py: moi ban ghi co
yearReport/lengthReport va ngay cong bo). Dau ra: webdata/snapshot/ttm.parquet.

Chi nhan ma co DU 4 quy lien tiep, khong trung, khong thieu so (analysis/ttm.compute_ttm)
va quy cuoi khong cu hon quy moi nhat cua thi truong qua `--max-lag` quy. Moi dong mang
nguon goc de web kiem tra truoc khi hien P/E TTM:
    ttm_source   bat dau bang "VCI raw"
    ttm_periods  dung 4 quy lien tiep "YYYY-Qn", cach nhau dau phay
    ttm_label    "TTM Qn/YYYY" khop quy cuoi

    python scripts/build_ttm_quarterly.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.analysis.ttm import compute_ttm, qindex, qlabel  # noqa: E402
from invest_system.data.arminer_bctc import REF_DIR  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR  # noqa: E402

SOURCE = "VCI raw BCTC quý ({line}; kỳ theo yearReport/lengthReport)"
COLUMNS = ["symbol", "ni_ttm", "ttm_label", "ttm_periods", "ttm_source", "ttm_published_at", "ttm_fetched_at"]


def build(quarterly: pd.DataFrame, fetched_at: dict[str, str] | None = None, max_lag: int = 1,
          lines: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    """(bang TTM, ly do bo qua theo ma). `fetched_at`: ma -> thoi diem tai ban raw;
    `lines`: ma -> dong bao cao VCI da anh xa vao LNST co dong cong ty me (vd "income.isa22 ...")."""
    fetched_at, lines = fetched_at or {}, lines or {}
    last = {sym: max(qindex(y, q) for y, q in zip(g["year"], g["quarter"], strict=True))
            for sym, g in quarterly.groupby("symbol", sort=False)}
    if not last:
        return pd.DataFrame(columns=COLUMNS), {}
    market = int(pd.Series(last).mode().max())      # quy ma nhieu ma da cong bo nhat
    rows, skipped = [], {}
    for sym, g in quarterly.groupby("symbol", sort=False):
        end = last[sym]
        if end < market - max_lag:
            skipped[sym] = f"quý mới nhất {qlabel(end)} cũ hơn {qlabel(market)} quá {max_lag} quý"
            continue
        res = compute_ttm(g, end=(end // 4, end % 4 + 1))
        ni = res.get("net_income_parent") if res.ok else None
        if ni is None:
            skipped[sym] = "; ".join(res.notes) or "thiếu LNST cổ đông công ty mẹ"
            continue
        window = g[[qlabel(qindex(y, q)) in res.periods for y, q in zip(g["year"], g["quarter"], strict=True)]]
        published = pd.to_datetime(window["published_at"]).max() if "published_at" in window else pd.NaT
        rows.append({"symbol": sym, "ni_ttm": ni, "ttm_label": res.label, "ttm_periods": ",".join(res.periods),
                     "ttm_source": SOURCE.format(line=lines.get(sym) or "LNST cổ đông công ty mẹ"),
                     "ttm_published_at": f"{published:%Y-%m-%d}" if pd.notna(published) else None,
                     "ttm_fetched_at": fetched_at.get(sym)})
    return pd.DataFrame(rows, columns=COLUMNS), skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-lag", type=int, default=1, help="so quy toi da duoc cham hon quy moi nhat cua thi truong")
    ap.add_argument("--out", type=Path, default=SNAPSHOT_DIR / "ttm.parquet")
    args = ap.parse_args()
    quarterly = pd.read_parquet(REF_DIR / "bctc_quarterly.parquet")
    state_path = REF_DIR / "bctc_quarterly" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    success = state.get("success", {})
    fetched = {s: str(v.get("at", ""))[:16].replace("T", " ") for s, v in success.items()}
    lines = {s: v.get("mapping", {}).get("net_income_parent") for s, v in success.items()}
    ttm, skipped = build(quarterly, fetched, args.max_lag, lines)
    ttm.to_parquet(args.out, index=False)
    print(f"Ghi {args.out}: {len(ttm)} mã có TTM ({ttm['ttm_label'].value_counts().to_dict()}), "
          f"{int((ttm['ni_ttm'] <= 0).sum())} mã lỗ; bỏ qua {len(skipped)} mã")
    for sym, why in list(skipped.items())[:10]:
        print(f"   {sym}: {why}")


if __name__ == "__main__":
    main()
