"""Engine danh muc tai can bang (rebalance) theo ty trong muc tieu.

Khac engine.py cua bot (lenh don le co stop/target), o day moi ky co mot danh
muc muc tieu {ma: ty trong}. Quy tac chong tu lua - docs/phase2/backtest-design.md muc 6:

  1. Tin hieu o gia DONG CUA phien t, khop o gia MO CUA phien t + delay (mac dinh 1).
  2. Phi `fee_rate` la phi HAI CHIEU (costs.fee_rate) -> moi lan mua/ban tru fee/2;
     thue `sell_tax` tren gia tri ban.
  3. T+2 theo PHIEN: co phieu mua phien j ban duoc tu phien j+2; tien ban ve sau
     2 phien moi dung de mua (khong ung truoc).
  4. Ket san (dong cua = gia san va low = dong cua): KHONG ban duoc phien do, lenh
     ban cho sang phien sau.
  5. Gia tri moi lenh <= `participation` x GTGD TB 20 phien tinh den phien tin hieu;
     phan vuot bo (giu tien mat). Lam tron lo 100 CP.
  6. Lenh chua khop het (thieu tien do T+2, ket san) giu den khi khop hoac den
     ky tai can bang ke tiep (bi thay the).
  7. Dinh gia cuoi phien theo gia dong cua; ma khong co phien dung gia gan nhat.

`floor_locked`, `tick_size`, `is_settled` port tu Kumo_VN_bot risk/constraints.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import get_settings


# ------------------------------------------------------------------ rang buoc san (port tu bot)
def price_band(exchange: str) -> float:
    return get_settings().get(f"price_band.{str(exchange).upper()}", 0.07)


def tick_size(price: float, exchange: str) -> float:
    if str(exchange).upper() != "HOSE":
        return 100.0
    if price < 10_000:
        return 10.0
    if price < 50_000:
        return 50.0
    return 100.0


def floor_locked(frame: pd.DataFrame, exchange: str) -> pd.Series:
    """Phien trang ben mua o gia san: close <= san (+1 buoc gia) va low == close."""
    close = frame["close"].astype(float)
    low = frame["low"].astype(float)
    reference = close.shift(1)
    floor = reference * (1 - price_band(exchange))
    tick = reference.map(lambda p: tick_size(p, exchange) if pd.notna(p) else 0.0)
    return ((close <= floor + tick) & (low >= close * (1 - 1e-6)) & reference.notna()).astype(bool)


def is_settled(entry_session: int, today_session: int, days: int) -> bool:
    return today_session - entry_session >= days


# ------------------------------------------------------------------ du lieu thi truong
@dataclass
class Market:
    """Bang gia (phien x ma) da can theo lich chung."""

    calendar: pd.DatetimeIndex
    open: pd.DataFrame
    close: pd.DataFrame
    locked: pd.DataFrame          # bool: ket san
    adv20: pd.DataFrame           # GTGD TB 20 phien tinh DEN phien do (dong)

    @classmethod
    def from_ohlcv(cls, ohlcv: pd.DataFrame, exchanges: dict[str, str] | None = None,
                   calendar: pd.DatetimeIndex | None = None) -> Market:
        exchanges = {str(k).upper(): str(v).upper() for k, v in (exchanges or {}).items()}
        frame = ohlcv.sort_values(["symbol", "time"])
        locked_parts = []
        for sym, g in frame.groupby("symbol", sort=False):
            locked_parts.append(floor_locked(g, exchanges.get(str(sym).upper(), "HOSE")))
        frame = frame.assign(locked=pd.concat(locked_parts).reindex(frame.index).fillna(False),
                             value=frame["close"].astype(float) * frame["volume"].astype(float))
        frame["adv20"] = frame.groupby("symbol")["value"].transform(lambda s: s.rolling(20, min_periods=1).mean())
        cal = calendar if calendar is not None else pd.DatetimeIndex(sorted(frame["time"].unique()))

        def pivot(col):
            return frame.pivot(index="time", columns="symbol", values=col).reindex(cal)

        return cls(cal, pivot("open"), pivot("close"), pivot("locked").fillna(False).astype(bool), pivot("adv20"))


@dataclass(frozen=True)
class Costs:
    fee_rate: float = 0.0025      # hai chieu
    sell_tax: float = 0.001
    settle_days: int = 2
    participation: float = 0.10
    lot: int = 100

    @classmethod
    def from_settings(cls, **overrides) -> Costs:
        s = get_settings()
        base = cls(fee_rate=s.get("costs.fee_rate", 0.0025), sell_tax=s.get("costs.sell_tax_rate", 0.001),
                   settle_days=int(s.get("costs.settlement_days", 2)))
        return cls(**{**base.__dict__, **overrides})


@dataclass
class Order:
    symbol: str
    side: str          # "buy" | "sell"
    shares: int


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    holdings: pd.DataFrame = field(default_factory=pd.DataFrame)   # moi ky: so ma nam giu, tien mat

    def turnover(self) -> float:
        """Vong quay MOT chieu theo nam = (mua + ban)/2 / von binh quan / so nam."""
        if self.trades.empty or len(self.equity) < 2:
            return 0.0
        years = len(self.equity) / 252
        return float(self.trades["value"].sum() / 2 / self.equity.mean() / years)


def run(market: Market, targets: dict[pd.Timestamp, dict[str, float]], capital: float = 1e9,
        costs: Costs | None = None, delay: int = 1, start=None, end=None,
        liquidate_at_end: bool = False) -> Result:
    """`targets`: {phien tin hieu t: {ma: ty trong}} (tong <= 1, phan con lai la tien mat).

    Chi chay cac phien trong [start, end). Tin hieu phai nam trong lich `market`.
    """
    costs = costs or Costs.from_settings()
    cal = market.calendar
    first = 0 if start is None else int(cal.searchsorted(pd.Timestamp(start)))
    stop = len(cal) if end is None else int(cal.searchsorted(pd.Timestamp(end)))
    exec_at: dict[int, tuple[pd.Timestamp, dict[str, float]]] = {}
    for signal, weights in targets.items():
        idx = int(cal.searchsorted(pd.Timestamp(signal)))
        if idx < len(cal) and cal[idx] == pd.Timestamp(signal) and first <= idx + delay < stop:
            exec_at[idx + delay] = (pd.Timestamp(signal), weights)

    open_px, close_px = market.open.to_numpy(float), market.close.to_numpy(float)
    locked, adv = market.locked.to_numpy(bool), market.adv20.to_numpy(float)
    col = {s: j for j, s in enumerate(market.close.columns)}
    half_fee = costs.fee_rate / 2

    cash = capital
    pending_cash: list[tuple[int, float]] = []          # (phien ve, so tien)
    lots: dict[str, list[list[int]]] = {}               # ma -> [[phien mua, so CP], ...]
    last_close: dict[str, float] = {}
    orders: list[Order] = []
    trades, equity, holdings = [], [], []

    def shares_of(sym: str) -> int:
        return sum(q for _, q in lots.get(sym, []))

    def mark(sym: str, i: int) -> float:
        px = close_px[i, col[sym]]
        if np.isfinite(px):
            last_close[sym] = px
        return last_close.get(sym, 0.0)

    for i in range(first, stop):
        # tien ban da ve (T+2)
        cash += sum(a for d, a in pending_cash if d <= i)
        pending_cash = [(d, a) for d, a in pending_cash if d > i]

        if i in exec_at:
            signal, weights = exec_at[i]
            s_idx = i - delay
            value = cash + sum(a for _, a in pending_cash) + sum(
                shares_of(s) * last_close.get(s, 0.0) for s in lots)
            orders = []
            for sym in sorted(set(lots) | set(weights)):
                if sym not in col:
                    continue
                j = col[sym]
                # gia tham chieu de tinh so CP: mo cua phien khop; ma chua giao dich lai thi
                # dung dong cua phien tin hieu (da biet tai t), lenh cho den khi co phien.
                ref = next((p for p in (open_px[i, j], close_px[s_idx, j], last_close.get(sym, np.nan))
                            if np.isfinite(p) and p > 0), np.nan)
                if not np.isfinite(ref) or ref <= 0:
                    continue
                have = shares_of(sym)
                want = weights.get(sym, 0.0) * value
                cap = costs.participation * adv[s_idx, j] if np.isfinite(adv[s_idx, j]) else 0.0
                diff = want - have * ref
                if weights.get(sym, 0.0) == 0 and have:
                    orders.append(Order(sym, "sell", have))
                elif diff < 0:
                    qty = min(have, int(math.ceil(min(-diff, cap) / ref / costs.lot)) * costs.lot)
                    if qty > 0:
                        orders.append(Order(sym, "sell", qty))
                elif diff > 0:
                    qty = int(min(diff, cap) / ref / costs.lot) * costs.lot
                    if qty > 0:
                        orders.append(Order(sym, "buy", qty))
            orders.sort(key=lambda o: o.side != "sell")    # ban truoc

        # ---- khop lenh o gia mo cua
        remaining: list[Order] = []
        for order in orders:
            j = col[order.symbol]
            px = open_px[i, j]
            if not np.isfinite(px) or px <= 0:
                remaining.append(order)
                continue
            if order.side == "sell":
                if locked[i, j]:
                    remaining.append(order)           # ket san: doi phien sau
                    continue
                settled = sum(q for d, q in lots.get(order.symbol, []) if is_settled(d, i, costs.settle_days))
                qty = min(order.shares, settled)
                if qty <= 0:
                    remaining.append(order)
                    continue
                gross = qty * px
                fee, tax = gross * half_fee, gross * costs.sell_tax
                pending_cash.append((i + costs.settle_days, gross - fee - tax))
                left = qty
                for lot in lots[order.symbol]:                     # FIFO
                    take = min(lot[1], left)
                    lot[1] -= take
                    left -= take
                lots[order.symbol] = [lot for lot in lots[order.symbol] if lot[1] > 0]
                if not lots[order.symbol]:
                    del lots[order.symbol]
                trades.append({"time": cal[i], "symbol": order.symbol, "side": "sell", "shares": qty,
                               "price": px, "value": gross, "fee": fee, "tax": tax})
                if qty < order.shares:
                    remaining.append(Order(order.symbol, "sell", order.shares - qty))
            else:
                affordable = int(cash / (px * (1 + half_fee)) / costs.lot) * costs.lot
                qty = min(order.shares, affordable)
                if qty > 0:
                    gross = qty * px
                    fee = gross * half_fee
                    cash -= gross + fee
                    lots.setdefault(order.symbol, []).append([i, qty])
                    last_close.setdefault(order.symbol, px)
                    trades.append({"time": cal[i], "symbol": order.symbol, "side": "buy", "shares": qty,
                                   "price": px, "value": gross, "fee": fee, "tax": 0.0})
                if qty < order.shares:
                    remaining.append(Order(order.symbol, "buy", order.shares - qty))
        orders = remaining

        held = sum(shares_of(s) * mark(s, i) for s in list(lots))
        if liquidate_at_end and i == stop - 1:
            for sym in list(lots):
                gross = shares_of(sym) * last_close.get(sym, 0.0)
                fee, tax = gross * half_fee, gross * costs.sell_tax
                trades.append({"time": cal[i], "symbol": sym, "side": "sell", "shares": shares_of(sym),
                               "price": last_close.get(sym, 0.0), "value": gross, "fee": fee, "tax": tax})
                cash += gross - fee - tax
                del lots[sym]
            held = 0.0
        total = cash + sum(a for _, a in pending_cash) + held
        equity.append(total)
        if i in exec_at:
            holdings.append({"time": cal[i], "n_targets": len(exec_at[i][1]), "n_held": len(lots),
                             "cash_pct": (cash + sum(a for _, a in pending_cash)) / total if total else 0.0})

    return Result(pd.Series(equity, index=cal[first:stop], dtype=float),
                  pd.DataFrame(trades, columns=["time", "symbol", "side", "shares", "price", "value", "fee", "tax"]),
                  pd.DataFrame(holdings))
