"""Backtest point-in-time cua bang co hoi (/co-hoi) - docs/phase2/backtest-design.md.

    DATA_DIR=./data-phase2 python scripts/run_backtest_opportunity.py --score    # cham diem moi cuoi thang (resume)
    DATA_DIR=./data-phase2 python scripts/run_backtest_opportunity.py --run      # walk-forward, benchmark, IC, do nhay
    ... --score --start 2019-01-01 --end 2019-07-01 --out-dir <tam>               # chay thu ngan de go loi

Dau vao: webdata/snapshot (universe tinh), $DATA_DIR/market/ohlcv.parquet (OHLCV da dieu chinh,
MARKET_COUNT_BACK=2300 scripts/backfill_data.py --full; snapshot web chi giu 500 phien gan nhat),
$DATA_DIR/backtest/vnindex.parquet (scripts/backfill_vnindex.py),
data/reference/bctc_quarterly.parquet (TTM point-in-time).
Diem moi ngay luu $DATA_DIR/backtest/scores/<ngay>.parquet. Ket qua: outputs/backtest_opportunity/
va docs/backtest-opportunity.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.backtest import opportunity as opp  # noqa: E402
from invest_system.backtest.history import History, ttm_history  # noqa: E402
from invest_system.backtest.portfolio import Costs, Market, run  # noqa: E402
from invest_system.config import get_paths  # noqa: E402
from invest_system.data import market_store  # noqa: E402
from invest_system.data.arminer_bctc import REF_DIR  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR  # noqa: E402

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
CAPITAL = 1_000_000_000
# review-codex-on-claude-aeeb5c7 (BLOCKER): khong co cac phien ban BCTC theo ngay cong bo
PIT_CAVEAT = ("Kết quả thăm dò, chưa đạt chuẩn point-in-time nghiêm ngặt: BCTC năm và quý là bản mới nhất của nguồn "
              "(có thể đã điều chỉnh hồi tố). Bộ lọc ngày công bố chỉ chặn việc dùng kỳ chưa công bố, không khôi phục "
              "được con số nhà đầu tư thấy tại thời điểm đó. Không dùng làm kết quả đầu tư đã kiểm chứng.")
FIRST_SIGNAL = "2018-09-28"     # >= 12 thang gia (tu 10/2017) cho diem ky thuat / tang truong
MIN_SYMBOLS_AT_START = 100      # kho gia 500 phien (snapshot web) khong qua duoc nguong nay


def _paths(out_dir: Path | None):
    base = get_paths().data_dir / "backtest"
    return base, base / "scores", out_dir or ROOT / "outputs" / "backtest_opportunity"


def _load():
    universe = pd.read_parquet(SNAPSHOT_DIR / "market_universe.parquet")
    store = get_paths().data_dir / "market" / market_store.OHLCV_FILENAME
    ohlcv = pd.read_parquet(store if store.exists() else SNAPSHOT_DIR / "ohlcv.parquet")
    # nen loi cua nguon (gia = 0, vd 69 ma UPCOM ngay 23/07/2018) -> coi nhu phien khong giao dich
    ohlcv = ohlcv[(ohlcv[["open", "high", "low", "close"]] > 0).all(axis=1)]
    vni_path = get_paths().data_dir / "backtest" / "vnindex.parquet"
    if not vni_path.exists():
        raise SystemExit(f"Thiếu {vni_path} - chạy scripts/backfill_vnindex.py trước")
    vnindex = pd.read_parquet(vni_path)
    qpath = REF_DIR / "bctc_quarterly.parquet"
    quarterly = pd.read_parquet(qpath) if qpath.exists() else None
    return universe, ohlcv, vnindex, quarterly


def _ttm(base: Path, quarterly: pd.DataFrame | None) -> pd.DataFrame:
    """ttm_history mat ~35 phut voi 1.222 ma -> luu $DATA_DIR/backtest/ttm_history.parquet,
    tinh lai khi bctc_quarterly.parquet moi hon ban luu."""
    cache, src = base / "ttm_history.parquet", REF_DIR / "bctc_quarterly.parquet"
    if quarterly is not None and cache.exists() and cache.stat().st_mtime >= src.stat().st_mtime:
        return pd.read_parquet(cache)
    ttm = ttm_history(quarterly).sort_values("available_from")
    if quarterly is not None:
        ttm.to_parquet(cache, index=False)
    return ttm


def month_ends(calendar: pd.DatetimeIndex, start, end) -> list[pd.Timestamp]:
    cal = calendar[(calendar >= pd.Timestamp(start)) & (calendar < pd.Timestamp(end))]
    return list(pd.Series(cal).groupby(cal.to_period("M")).max())


def score(args) -> None:
    base, score_dir, _ = _paths(args.out_dir)
    score_dir.mkdir(parents=True, exist_ok=True)
    universe, ohlcv, vnindex, quarterly = _load()
    dates = month_ends(pd.DatetimeIndex(sorted(vnindex["time"].unique())), args.start, args.end)
    n_start = int((ohlcv.groupby("symbol")["time"].min() <= dates[0]).sum()) if dates else 0
    if dates and n_start < MIN_SYMBOLS_AT_START:
        raise SystemExit(f"Chỉ {n_start} mã có giá trước {dates[0]:%Y-%m-%d} - backfill giá trước: "
                         "MARKET_COUNT_BACK=2300 python scripts/backfill_data.py --full")
    t0 = time.time()
    hist = History(universe, ohlcv, vnindex)
    hist.ttm = _ttm(base, quarterly)
    print(f"Chuẩn bị dữ liệu {time.time() - t0:.0f}s; BCTC năm {hist.fin['symbol'].nunique()} mã; "
          f"TTM {hist.ttm['symbol'].nunique()} mã", flush=True)
    for d in dates:
        path = score_dir / f"{d:%Y-%m-%d}.parquet"
        if path.exists() and not args.rescore:
            continue
        t1 = time.time()
        day = hist.score(d)
        day.to_parquet(path, index=False)
        n_elig = int(day["eligible"].sum()) if "eligible" in day else 0
        errors = int(day["error"].notna().sum()) if "error" in day else 0
        print(f"{d:%Y-%m-%d}: {len(day)} mã đủ điều kiện mục 4, {n_elig} đạt /co-hoi, {errors} lỗi "
              f"({time.time() - t1:.0f}s)", flush=True)


def _scores(score_dir: Path) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for p in sorted(score_dir.glob("*.parquet"))]
    scores = pd.concat(frames, ignore_index=True)
    if "error" in scores:
        scores = scores[scores["error"].isna()]
    scores["as_of"] = pd.to_datetime(scores["as_of"])
    return scores


def _git_sha() -> str:
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    try:
        dirty = git("status", "--porcelain", "--untracked-files=no", "--", "src", "scripts", "config")
        return git("rev-parse", "--short", "HEAD") + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "?"


def run_all(args) -> None:
    base, score_dir, out = _paths(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    universe, ohlcv, vnindex, _ = _load()
    scores = _scores(score_dir)
    exchanges = dict(zip(universe["symbol"], universe["exchange"], strict=True))
    calendar = pd.DatetimeIndex(sorted(vnindex["time"].unique()))
    market = Market.from_ohlcv(ohlcv[ohlcv["symbol"].isin(set(scores["symbol"]))], exchanges, calendar)
    costs = Costs.from_settings()
    start = scores["as_of"].min() + pd.Timedelta(days=1)
    end = calendar[-1] + pd.Timedelta(days=1)
    print(f"{scores['as_of'].nunique()} ngày tín hiệu, {scores['symbol'].nunique()} mã; {start:%Y-%m-%d} → {end:%Y-%m-%d}")

    wf_kw = {"train_months": args.train_months, "test_months": args.test_months}
    wf = opp.walk_forward(market, scores, start, end, capital=CAPITAL, costs=costs, **wf_kw)
    oos_start, oos_end = wf.equity.index[0], wf.equity.index[-1] + pd.Timedelta(days=1)
    vni_eq = opp.index_equity(vnindex, oos_start, oos_end, CAPITAL)
    report = wf.sharpe_report()

    # benchmark tren cung giai doan OOS, cung phi/thue/T+2
    chosen_n = max((cfg.top_n for *_, cfg in wf.chosen), key=[c.top_n for *_, c in wf.chosen].count)
    bench_runs = {
        "Cân bằng toàn universe đủ điều kiện": run(market, opp.equal_weight_targets(scores), CAPITAL, costs,
                                                  start=oos_start, end=oos_end),
        f"Top {chosen_n} vốn hoá": run(market, opp.market_cap_targets(scores, chosen_n), CAPITAL, costs,
                                       start=oos_start, end=oos_end),
    }
    rows = {"Chiến lược (walk-forward OOS)": {**opp.summary(wf.equity, vni_eq, wf.turnover()),
                                               "PSR(0)": report["psr"], "DSR": report["dsr"]},
            "VN-Index (chỉ số giá)": opp.summary(vni_eq)}
    for name, res in bench_runs.items():
        rows[name] = opp.summary(res.equity, vni_eq, res.turnover())
    benchmarks = pd.DataFrame(rows).T

    # 4 cau hinh tren toan giai doan (minh bach, khong dung de chon)
    full = {}
    for cfg in opp.GRID:
        res = run(market, opp.strategy_targets(scores, cfg), CAPITAL, costs, start=oos_start, end=oos_end)
        full[cfg.label()] = opp.summary(res.equity, vni_eq, res.turnover())

    # do nhay tren dung cac lua chon walk-forward
    universe_syms = set(scores["symbol"])
    winners = opp.top_return_symbols(market, universe_syms, oos_start, oos_end, 0.10)
    sens = {
        "Gốc": wf,
        "Phí × 2": opp.walk_forward(market, scores, start, end, CAPITAL, Costs.from_settings(fee_rate=2 * costs.fee_rate),
                                    fixed=wf.chosen),
        "Trễ thêm 1 phiên": opp.walk_forward(market, scores, start, end, CAPITAL, costs, delay=2, fixed=wf.chosen),
        f"Bỏ {len(winners)} mã lợi suất cao nhất (10%)": opp.walk_forward(market, scores, start, end, CAPITAL, costs,
                                                                         exclude=winners, fixed=wf.chosen),
    }
    sensitivity = pd.DataFrame({k: {**opp.summary(v.equity, vni_eq, v.turnover()), "PSR(0)": v.sharpe_report()["psr"]}
                                for k, v in sens.items()}).T

    ic = opp.ic_table(market, scores)

    # ---- ghi ket qua
    equity = pd.DataFrame({"Chiến lược": wf.equity, "VN-Index": vni_eq,
                           **{k: v.equity for k, v in bench_runs.items()}})
    equity.index.name = "time"
    equity.to_csv(out / "equity_oos.csv", encoding="utf-8-sig")
    wf.slices.to_csv(out / "slices.csv", index=False, encoding="utf-8-sig")
    wf.trials.to_csv(out / "trials.csv", index=False, encoding="utf-8-sig")
    benchmarks.to_csv(out / "benchmarks.csv", encoding="utf-8-sig")
    pd.DataFrame(full).T.to_csv(out / "configs_full_period.csv", encoding="utf-8-sig")
    sensitivity.to_csv(out / "sensitivity.csv", encoding="utf-8-sig")
    ic.to_csv(out / "ic.csv", index=False, encoding="utf-8-sig")
    verdict = conclude(benchmarks, report, ic, sensitivity)
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "commit": _git_sha(),
        "oos_start": f"{oos_start:%Y-%m-%d}", "oos_end": f"{wf.equity.index[-1]:%Y-%m-%d}",
        "signals": int(scores["as_of"].nunique()), "symbols_scored": int(scores["symbol"].nunique()),
        "capital_vnd": CAPITAL, "fee_rate_round_trip": costs.fee_rate, "sell_tax": costs.sell_tax,
        "settlement_days": costs.settle_days, "participation": costs.participation,
        "grid": [c.label() for c in opp.GRID], "sharpe_report": report, "verdict": verdict, "caveat": PIT_CAVEAT,
        "chosen": [{"test_start": f"{a:%Y-%m-%d}", "test_end": f"{b:%Y-%m-%d}", "config": c.label()}
                   for a, b, c in wf.chosen],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    if not args.no_doc:
        write_doc(summary, benchmarks, pd.DataFrame(full).T, sensitivity, ic, wf.slices)
        write_web(summary, benchmarks, pd.DataFrame(full).T, sensitivity, ic, wf.slices, equity)
    print(json.dumps(verdict, ensure_ascii=False, indent=1))


def conclude(benchmarks: pd.DataFrame, report: dict, ic: pd.DataFrame, sensitivity: pd.DataFrame) -> dict:
    """Tieu chi muc 9 (chot truoc khi chay)."""
    strat = benchmarks.loc["Chiến lược (walk-forward OOS)"]
    others = benchmarks.drop(index="Chiến lược (walk-forward OOS)")
    ic3 = ic[(ic["nhóm"] == "tổng hợp") & (ic["kỳ hạn (tháng)"] == 3)]
    ic_mean = float(ic3["IC trung binh"].iloc[0]) if len(ic3) and "IC trung binh" in ic3 else float("nan")
    ic_t = float(ic3["t-stat Newey-West"].iloc[0]) if len(ic3) and "t-stat Newey-West" in ic3 else float("nan")
    fee2 = sensitivity.loc["Phí × 2"]
    checks = {
        "DSR ≥ 0,95": bool(report["dsr"] >= 0.95),
        "IC tổng hợp 3 tháng > 0 và t Newey–West ≥ 2": bool(ic_mean > 0 and ic_t >= 2),
        "Sharpe OOS vượt cả ba benchmark": bool((strat["Sharpe"] > others["Sharpe"]).all()),
        "Phí × 2 vẫn vượt VN-Index (CAGR)": bool(fee2["CAGR"] > benchmarks.loc["VN-Index (chỉ số giá)", "CAGR"]),
    }
    return {"checks": checks, "edge": all(checks.values()),
            "text": ("Có lợi thế có ý nghĩa thống kê theo cả bốn tiêu chí chốt trước." if all(checks.values()) else
                     "Không có bằng chứng lợi thế có ý nghĩa thống kê (không đạt: "
                     + "; ".join(k for k, v in checks.items() if not v) + ").")}


def _fmt(v, key: str) -> str:
    if not isinstance(v, (int, float)) or pd.isna(v):
        return "—"
    if any(t in key for t in ("Sharpe", "PSR", "DSR", "Vòng quay", "IC", "t-stat", "ICIR")):
        return f"{v:.2f}"
    if "Số" in key:
        return f"{v:,.0f}"
    return f"{v:.1%}"


def _table(frame: pd.DataFrame, cols: list[str] | None = None) -> list[str]:
    cols = [c for c in (cols or list(frame.columns)) if c in frame.columns]
    lines = ["| | " + " | ".join(cols) + " |", "|---|" + "---:|" * len(cols)]
    for name, row in frame.iterrows():
        lines.append(f"| {name} | " + " | ".join(_fmt(row[c], c) for c in cols) + " |")
    return lines


def write_doc(summary: dict, benchmarks, full, sensitivity, ic, slices) -> None:
    main_cols = ["CAGR", "Sharpe", "Sụt giảm tối đa", "Tỷ lệ tháng dương", "Tỷ lệ tháng thắng VN-Index",
                 "Vòng quay (lần/năm)", "PSR(0)", "DSR"]
    v = summary["verdict"]
    lines = [
        "# Backtest point-in-time bảng cơ hội", "",
        f"Sinh tự động bởi `scripts/run_backtest_opportunity.py` lúc {summary['generated_at']} (commit `{summary['commit']}`). "
        "Thiết kế và các quyết định chốt trước: [`docs/phase2/backtest-design.md`](phase2/backtest-design.md).", "",
        "## Kết luận", "", f"**{v['text']}**", "",
        *[f"- {'✅' if ok else '❌'} {name}" for name, ok in v["checks"].items()], "",
        f"> **{PIT_CAVEAT}**", "",
        f"Out-of-sample {summary['oos_start']} → {summary['oos_end']}; {summary['signals']} ngày tín hiệu cuối tháng; "
        f"{summary['symbols_scored']} mã từng đủ điều kiện; vốn {summary['capital_vnd'] / 1e9:.0f} tỷ đồng; phí hai chiều "
        f"{summary['fee_rate_round_trip']:.2%}, thuế bán {summary['sell_tax']:.1%}, T+{summary['settlement_days']}, "
        f"lệnh ≤ {summary['participation']:.0%} GTGD TB20. DSR với {summary['sharpe_report']['n_trials']} lần thử.", "",
        "## Chiến lược so với benchmark (OOS)", "", *_table(benchmarks, main_cols), "",
        "VN-Index là chỉ số **giá** (không gồm cổ tức); các danh mục dùng giá đã điều chỉnh nên đã gồm cổ tức.", "",
        "## Năng lực xếp hạng (IC Spearman theo tháng)", "",
        "| Nhóm | Kỳ hạn | IC TB | ICIR | t thường | t Newey–West | Tháng IC>0 | Số tháng |", "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, d in ic.iterrows():
        lines.append(f"| {d['nhóm']} | {d['kỳ hạn (tháng)']}T | {_fmt(d.get('IC trung binh'), 'IC')} | "
                     f"{_fmt(d.get('ICIR'), 'ICIR')} | {_fmt(d.get('t-stat'), 't-stat')} | "
                     f"{_fmt(d.get('t-stat Newey-West'), 't-stat')} | {_fmt(d.get('Ti le thang IC>0'), '%')} | "
                     f"{_fmt(d.get('So thang'), 'Số')} |")
    lines += ["", "## Độ nhạy (cùng lựa chọn walk-forward, không chọn lại)", "",
              *_table(sensitivity, ["CAGR", "Sharpe", "Sụt giảm tối đa", "PSR(0)"]), "",
              "## Bốn cấu hình trên cả giai đoạn OOS (minh bạch, không dùng để chọn)", "",
              *_table(full, ["CAGR", "Sharpe", "Sụt giảm tối đa", "Vòng quay (lần/năm)"]), "",
              "## Các lát walk-forward", "", "| Train từ | Test | Cấu hình chọn | Sharpe train | Lợi suất test |", "|---|---|---|---:|---:|"]
    for _, d in slices.iterrows():
        lines.append(f"| {pd.Timestamp(d['train_start']):%m/%Y} | {pd.Timestamp(d['test_start']):%m/%Y}–"
                     f"{pd.Timestamp(d['test_end']):%m/%Y} | {d['cấu hình']} | {_fmt(d['Sharpe train'], 'Sharpe')} | "
                     f"{_fmt(d.get('Lợi suất tích luỹ'), '%')} |")
    lines += ["", "## Giới hạn", "",
              "- Universe là mã **đang niêm yết hôm nay** (survivorship) → kết quả là cận trên.",
              "- Điểm backtest dùng 5/7 nhóm: vĩ mô và tin tức không có lịch sử theo ngày công bố.",
              "- Số CP, ngành ICB, sàn và lãi suất phi rủi ro lấy giá trị hiện tại; BCTC năm dùng quy tắc 01/04 năm sau, "
              "BCTC quý dùng ngày công bố thật của VCI; số liệu có thể đã điều chỉnh hồi tố.",
              "- UPCOM gần như không có BCTC năm trong nguồn arminer nên ít khi đủ điều kiện.",
              "- Kho giá Vietcap có nến giá = 0 (chủ yếu UPCOM, 2015–2018) đã bị bỏ, coi như phiên không giao dịch; "
              "các biến động bất thường khác của giá điều chỉnh được giữ nguyên."]
    (ROOT / "docs" / "backtest-opportunity.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _records(frame: pd.DataFrame, name: str | None = None) -> list[dict]:
    frame = frame.reset_index(names=name) if name else frame
    return json.loads(frame.to_json(orient="records", date_format="iso", force_ascii=False))   # NaN -> null


def write_web(summary: dict, benchmarks, full, sensitivity, ic, slices, equity) -> None:
    """Goi du lieu cho trang /backtest: outputs/ khong duoc commit nen web doc file nay.
    Duong von lay cuoi tuan, quy ve 100 tai ngay dau OOS."""
    weekly = (equity / equity.iloc[0] * 100).resample("W-FRI").last().dropna(how="all").round(2)
    weekly.index = weekly.index.strftime("%Y-%m-%d")
    bundle = {"summary": summary, "benchmarks": _records(benchmarks, "name"), "configs": _records(full, "name"),
              "sensitivity": _records(sensitivity, "name"), "ic": _records(ic), "slices": _records(slices),
              "equity": _records(weekly, "time"), "equity_series": list(equity.columns)}
    path = ROOT / "webdata" / "backtest" / "opportunity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--start", default=FIRST_SIGNAL)
    ap.add_argument("--end", default="2100-01-01")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--train-months", type=int, default=24)
    ap.add_argument("--test-months", type=int, default=6)
    ap.add_argument("--no-doc", action="store_true", help="khong ghi docs/backtest-opportunity.md (chay thu)")
    args = ap.parse_args()
    if args.score:
        score(args)
    if args.run:
        run_all(args)


if __name__ == "__main__":
    main()
