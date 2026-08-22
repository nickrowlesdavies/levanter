"""
Event-driven, bar-by-bar backtester (honest by construction).

Design choices that keep it honest:
  * Signals are computed on bar t, but we ENTER on bar t+1's open. No
    strategy ever sees a price it could not have traded on.
  * Spread cost is charged on entry AND exit (round trip modelled as
    spread_pips * pip, split across both sides).
  * Stops and targets are checked against each bar's HIGH/LOW. If both are
    touched in the same bar we assume the STOP hit first (conservative).
  * One position at a time per instrument (config: max_open_positions).
  * Position size comes from the risk module, based on live equity.

Returns a Result with the equity curve and a trade blotter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from ..data.loader import Instrument
from ..risk.sizing import position_size


@dataclass
class Trade:
    instrument: str
    direction: int          # +1 long, -1 short
    entry_date: pd.Timestamp
    entry_price: float
    stop: float
    target: float
    units: float
    exit_date: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    reason: str = ""        # "stop", "target", "signal_flip", "end"
    pnl: float = 0.0


@dataclass
class Result:
    equity_curve: pd.Series
    trades: List[Trade] = field(default_factory=list)
    instrument: str = ""

    def blotter(self) -> pd.DataFrame:
        rows = [t.__dict__ for t in self.trades]
        return pd.DataFrame(rows)


def _carry_accrual(carry_annual, direction, entry_price, units, entry_date, exit_date):
    """Interest differential (swap/roll) earned or paid while holding.

    A real FX position accrues the rate differential daily. Long a positive-
    carry pair earns it; short pays it. carry_annual is an annualised % for
    being LONG the pair, looked up at entry (rates move slowly)."""
    if carry_annual is None:
        return 0.0
    try:
        c = float(carry_annual.asof(entry_date))
    except Exception:
        return 0.0
    if c != c:  # NaN
        return 0.0
    days = max((pd.Timestamp(exit_date) - pd.Timestamp(entry_date)).days, 0)
    notional = units * entry_price
    return direction * (c / 100.0) * (days / 365.25) * notional


def run_backtest(
    df: pd.DataFrame,
    signals: pd.DataFrame,
    inst: Instrument,
    starting_equity: float,
    risk_pct: float,
    carry_annual: Optional[pd.Series] = None,
) -> Result:
    """Simulate one instrument. `df` = OHLC, `signals` = signal/stop/target.

    If `carry_annual` (a date-indexed Series of annualised carry % for being
    long the pair) is given, each trade also earns/pays the interest
    differential over its holding period - realistic for any FX position."""
    half_spread = (inst.spread_pips * inst.pip) / 2.0

    equity = starting_equity
    equity_points = []
    trades: List[Trade] = []
    open_trade: Optional[Trade] = None

    dates = df.index
    for i in range(len(dates) - 1):
        today = dates[i]
        nxt = dates[i + 1]

        # ---- 1. Manage an open position on today's bar ----------------
        if open_trade is not None:
            bar = df.loc[today]
            hit = None
            exit_px = None
            if open_trade.direction == 1:
                # Conservative: check stop before target.
                if bar["low"] <= open_trade.stop:
                    hit, exit_px = "stop", open_trade.stop
                elif bar["high"] >= open_trade.target:
                    hit, exit_px = "target", open_trade.target
            else:
                if bar["high"] >= open_trade.stop:
                    hit, exit_px = "stop", open_trade.stop
                elif bar["low"] <= open_trade.target:
                    hit, exit_px = "target", open_trade.target

            if hit is not None:
                # Charge exit spread against the fill.
                fill = exit_px - open_trade.direction * half_spread
                pnl = open_trade.direction * (fill - open_trade.entry_price) * open_trade.units
                pnl += _carry_accrual(carry_annual, open_trade.direction,
                                      open_trade.entry_price, open_trade.units,
                                      open_trade.entry_date, today)
                equity += pnl
                open_trade.exit_date = today
                open_trade.exit_price = fill
                open_trade.reason = hit
                open_trade.pnl = pnl
                trades.append(open_trade)
                open_trade = None

        # ---- 2. Look for a new entry (act on next bar's open) ---------
        if open_trade is None:
            sig = signals.loc[today, "signal"]
            if sig != 0:
                raw_entry = df.loc[nxt, "open"]
                # Charge entry spread: buy a touch higher, sell a touch lower.
                entry = raw_entry + sig * half_spread
                stop = signals.loc[today, "stop"]
                target = signals.loc[today, "target"]
                units = position_size(equity, risk_pct, entry, stop)
                if units > 0:
                    open_trade = Trade(
                        instrument=inst.name,
                        direction=int(sig),
                        entry_date=nxt,
                        entry_price=entry,
                        stop=float(stop),
                        target=float(target),
                        units=units,
                    )

        equity_points.append((today, equity))

    # ---- 3. Close any position still open at the end -----------------
    if open_trade is not None:
        last = dates[-1]
        raw = df.loc[last, "close"]
        fill = raw - open_trade.direction * half_spread
        pnl = open_trade.direction * (fill - open_trade.entry_price) * open_trade.units
        pnl += _carry_accrual(carry_annual, open_trade.direction,
                              open_trade.entry_price, open_trade.units,
                              open_trade.entry_date, last)
        equity += pnl
        open_trade.exit_date = last
        open_trade.exit_price = fill
        open_trade.reason = "end"
        open_trade.pnl = pnl
        trades.append(open_trade)
    equity_points.append((dates[-1], equity))

    curve = pd.Series(
        [e for _, e in equity_points],
        index=pd.DatetimeIndex([d for d, _ in equity_points]),
        name="equity",
    )
    curve = curve[~curve.index.duplicated(keep="last")]
    return Result(equity_curve=curve, trades=trades, instrument=inst.name)
