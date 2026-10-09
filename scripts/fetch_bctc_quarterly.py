"""Tai BCTC QUY (moi quy tu 2018, kem ngay cong bo that) cho moi ma HOSE/HNX/UPCOM tu VCI.

    python scripts/fetch_bctc_quarterly.py --resume                 # toan bo, chay tiep
    python scripts/fetch_bctc_quarterly.py --symbols FPT,VCB,HPG    # vai ma
    python scripts/fetch_bctc_quarterly.py --assemble-only          # ghep lai tu cache, khong goi mang

Ton trong .agent-coord/locks/vnstock.lock: chi goi VCI khi tu giu khoa; giu theo
LO (`--batch` ma, ~3 request/ma) roi nha `--pause` giay de agent khac co luot.
Khoa dang do nguoi khac giu -> cho, khong chiem.

Cache: data/reference/bctc_quarterly/raw/<MA>_<bao cao>.parquet (ban raw VCI -
anh xa lai khong can tai lai), by_symbol/<MA>.parquet (da chuan hoa + kiem tra),
state.json (resume), failures.csv. Ket qua: data/reference/bctc_quarterly.parquet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from invest_system.data import vci_quarterly as vq  # noqa: E402
from invest_system.data.arminer_bctc import REF_DIR  # noqa: E402
from invest_system.web.universe import SNAPSHOT_DIR  # noqa: E402

OUT = REF_DIR / "bctc_quarterly.parquet"
BASE = REF_DIR / "bctc_quarterly"
RAW, BY_SYMBOL = BASE / "raw", BASE / "by_symbol"
STATE, FAILURES = BASE / "state.json", BASE / "failures.csv"
LOCK = Path(os.getenv("AGENT_LOCK_DIR", str(ROOT.parent / "invest-system" / ".agent-coord" / "locks"))) / "vnstock.lock"
OWNER = "CLAUDE"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ khoa
def acquire(purpose: str, wait: float = 30) -> None:
    while True:
        if not LOCK.exists():
            LOCK.parent.mkdir(parents=True, exist_ok=True)
            try:
                with LOCK.open("x", encoding="utf-8") as fh:  # "x": that bai neu ai vua tao
                    fh.write(f"{OWNER} | {_now()} | {purpose} | pid {os.getpid()}\n")
                return
            except FileExistsError:
                pass
        holder = LOCK.read_text(encoding="utf-8", errors="replace").strip() if LOCK.exists() else ""
        print(f"[{_now()}] vnstock.lock đang được giữ ({holder[:80]}) - chờ {wait:.0f}s", flush=True)
        time.sleep(wait)


def release() -> None:
    if LOCK.exists() and LOCK.read_text(encoding="utf-8", errors="replace").startswith(OWNER):
        LOCK.unlink()


# ------------------------------------------------------------------ tai
def _cached_raw(symbol: str, part: str) -> pd.DataFrame | None:
    path = RAW / f"{symbol}_{part}.parquet"
    return pd.read_parquet(path) if path.exists() else None


def _dictionary(template: str, symbol: str, delay: float) -> pd.DataFrame:
    path = BASE / f"dict_{template}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    rep = vq.TEMPLATE_REP.get(template, symbol)
    frame = vq.fetch_dictionary(rep)
    time.sleep(delay)
    frame.to_parquet(path, index=False)
    return frame


def _symbol_dictionary(symbol: str, template: str, raws: dict, delay: float) -> pd.DataFrame:
    """Tu dien theo mau; neu ma nay dung qua nhieu ma chi tieu la so voi mau -> lay tu dien rieng."""
    base = _dictionary(template, symbol, delay)
    known = set(base["field_name"].astype(str))
    codes = {c for raw in raws.values() for c in raw.columns if c[:3] in ("isa", "isb", "bsa", "bsb", "cfa", "cfb")}
    unknown = codes - known
    if codes and len(unknown) / len(codes) > 0.10:
        path = BASE / f"dict_symbol_{symbol}.parquet"
        if not path.exists():
            vq.fetch_dictionary(symbol).to_parquet(path, index=False)
            time.sleep(delay)
        return pd.read_parquet(path)
    return base


def fetch_symbol(symbol: str, company_type: str, delay: float) -> vq.QuarterlyResult:
    raws = {}
    for part in vq.PARTS:
        raw = _cached_raw(symbol, part)
        if raw is None:
            raw = vq.fetch_raw(symbol, part)
            time.sleep(delay)
            raw.to_parquet(RAW / f"{symbol}_{part}.parquet", index=False)
        raws[part] = raw
    dictionary = _symbol_dictionary(symbol, vq.template_for(company_type), raws, delay)
    return vq.validate(vq.standardize(symbol, raws, dictionary), company_type)


def assemble() -> pd.DataFrame:
    files = sorted(BY_SYMBOL.glob("*.parquet"))
    frames = [pd.read_parquet(p) for p in files]
    frames = [f for f in frames if not f.empty]
    if not frames:
        print("Chưa có mã nào.")
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).sort_values(["symbol", "year", "quarter"])
    out.to_parquet(OUT, index=False, compression="zstd")
    print(f"Ghi {OUT}: {out['symbol'].nunique()} mã, {len(out):,} quý "
          f"({out['year'].min()}-{out['year'].max()})")
    return out


def run(args: argparse.Namespace) -> None:
    for d in (RAW, BY_SYMBOL):
        d.mkdir(parents=True, exist_ok=True)
    if args.assemble_only:
        assemble()
        return
    universe = pd.read_parquet(SNAPSHOT_DIR / "market_universe.parquet")
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        universe = universe[universe["symbol"].isin(wanted)]
    elif args.exchange != "ALL":
        universe = universe[universe["exchange"] == args.exchange]
    universe = universe.sort_values("avg_value_20d", ascending=False, na_position="last")
    if args.top:
        universe = universe.head(args.top)
    state = (json.loads(STATE.read_text(encoding="utf-8")) if args.resume and STATE.exists()
             else {"success": {}, "failed": {}})
    todo = [r for r in universe.itertuples(index=False)
            if not (args.resume and r.symbol in state["success"] and (BY_SYMBOL / f"{r.symbol}.parquet").exists())]
    print(f"[{_now()}] {len(todo)} mã cần tải (universe {len(universe)})", flush=True)

    for start in range(0, len(todo), args.batch):
        batch = todo[start:start + args.batch]
        acquire(f"tải BCTC quý {len(batch)} mã ({start + 1}-{start + len(batch)}/{len(todo)}), scripts/fetch_bctc_quarterly.py")
        try:
            for row in batch:
                symbol = str(row.symbol).upper()
                try:
                    result = fetch_symbol(symbol, row.company_type, args.delay)
                    if result.errors:
                        raise ValueError("; ".join(result.errors))
                    result.frame.assign(exchange=row.exchange, company_type=row.company_type).to_parquet(
                        BY_SYMBOL / f"{symbol}.parquet", index=False)
                    state["success"][symbol] = {"quarters": len(result.frame), "rejected": result.rejected,
                                                "mapping": result.mapping, "at": _now()}
                    state["failed"].pop(symbol, None)
                except (Exception, SystemExit) as exc:  # noqa: BLE001 - vnai co the sys.exit khi bi chan
                    state["failed"][symbol] = {"error": str(exc)[:300], "exchange": row.exchange, "at": _now()}
                    if isinstance(exc, SystemExit) or "rate" in str(exc).lower() or "429" in str(exc):
                        print(f"[{_now()}] {symbol}: có vẻ bị giới hạn tốc độ - nghỉ 90s", flush=True)
                        time.sleep(90)
                STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        finally:
            release()
        done = start + len(batch)
        print(f"[{_now()}] {done}/{len(todo)} xong; thành công={len(state['success'])} lỗi={len(state['failed'])}",
              flush=True)
        if done < len(todo):
            time.sleep(args.pause)

    if state["failed"]:
        pd.DataFrame([{"symbol": k, **v} for k, v in state["failed"].items()]).to_csv(
            FAILURES, index=False, encoding="utf-8-sig")
    assemble()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", choices=("HOSE", "HNX", "UPCOM", "ALL"), default="ALL")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--delay", type=float, default=3.2, help="giây giữa hai request VCI")
    ap.add_argument("--batch", type=int, default=60, help="số mã mỗi lần giữ khoá")
    ap.add_argument("--pause", type=float, default=60, help="giây nhả khoá giữa hai lô")
    ap.add_argument("--assemble-only", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
