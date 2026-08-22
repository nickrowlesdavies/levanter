#!/usr/bin/env python3
"""
Live combined-portfolio tracker - the research arc's actual deliverable.

Each week it reports the target allocation of a diversified portfolio:
  * 70% CORE  : 60/40 (SPY / IEF)   - the stock/bond engine
  * 30% TREND : cross-asset trend sleeve - holds only markets in an uptrend,
                inverse-vol weighted; anything not trending sits in cash.
It books the blend into its own paper account and runs forward, alongside
the FX, carry, and crypto trials.

    python combined_tracker.py           # weekly cycle
    python combined_tracker.py --status  # show target + account, no change
    python combined_tracker.py --reset   # wipe the paper account

Simulated only. This is the un-levered version (gross <= 100%); the tested
'best blend' vol-matched the sleeve with ~2x leverage, which lifts impact
but adds financing - kept simple here. HONEST NOTE: the validated benefit of
this blend was modest (Sharpe ~1.02 -> 1.08) but real: lower drawdown for
similar return. Its value is a smoother ride, not outsized gains.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from trend_basket import load_prices, UNIVERSE

CORE = {"SPY": 0.60, "IEF": 0.40}
CORE_WEIGHT, TREND_WEIGHT = 0.70, 0.30
LOOKBACK, VOL_LB = 26, 13
CASH_APY = 0.04
STATE_PATH = "reports/combined_state.json"
START_EQUITY = 10000.0


def fresh_prices() -> pd.DataFrame:
    if os.path.exists("data_cache/trend_basket_weekly.csv"):
        os.remove("data_cache/trend_basket_weekly.csv")
    return load_prices()


def target_weights(prices: pd.DataFrame):
    """Return (weights dict asset->weight, trend_on list, trend_off list)."""
    rets = prices.pct_change()
    mom = prices / prices.shift(LOOKBACK) - 1.0
    vol = rets.rolling(VOL_LB).std()
    m, v = mom.iloc[-1], vol.iloc[-1]

    trend_cols = [c for c in prices.columns]
    up = [c for c in trend_cols if pd.notna(m[c]) and pd.notna(v[c])
          and v[c] > 0 and m[c] > 0]                     # long-flat: uptrend only
    off = [c for c in trend_cols if c not in up and pd.notna(m[c])]

    weights = {}
    # Core sleeve.
    for a, w in CORE.items():
        weights[a] = weights.get(a, 0.0) + CORE_WEIGHT * w
    # Trend sleeve: inverse-vol across uptrending markets.
    if up:
        invvol = {c: 1.0 / v[c] for c in up}
        s = sum(invvol.values())
        for c in up:
            weights[c] = weights.get(c, 0.0) + TREND_WEIGHT * invvol[c] / s
    # Whatever the trend sleeve doesn't deploy stays in cash.
    deployed = TREND_WEIGHT * (1.0 if up else 0.0)
    cash = TREND_WEIGHT - deployed
    return weights, up, off, cash


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"start_equity": START_EQUITY, "equity": START_EQUITY,
            "last_week": None, "weights": {}, "cash": 0.0,
            "_prices": {}, "history": []}


def save_state(s):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(s, f, indent=2, default=str)


def run_cycle(state, prices):
    week = str(prices.index[-1].date())
    if state["last_week"] == week:
        return state

    cash_weekly = (1 + CASH_APY) ** (1 / 52) - 1
    # Realise last week's portfolio.
    if state["weights"] and state["_prices"]:
        r = 0.0
        for a, w in state["weights"].items():
            p0 = state["_prices"].get(a)
            if p0 and a in prices.columns and pd.notna(prices[a].iloc[-1]):
                r += w * (prices[a].iloc[-1] / p0 - 1)
        r += state.get("cash", 0.0) * cash_weekly
        state["equity"] *= (1 + r)

    weights, up, off, cash = target_weights(prices)
    state["weights"] = weights
    state["cash"] = cash
    state["_prices"] = {a: float(prices[a].iloc[-1]) for a in weights
                        if pd.notna(prices[a].iloc[-1])}
    state["last_week"] = week
    state["history"].append({"week": week, "equity": round(state["equity"], 2),
                             "trend_on": up})
    return state


def print_target(state, prices):
    weights, up, off, cash = target_weights(prices)
    ret = (state["equity"] / state["start_equity"] - 1) * 100
    week = str(prices.index[-1].date())
    print("\n" + "=" * 66)
    print(" COMBINED PORTFOLIO TRACKER  (70% core / 30% trend sleeve)")
    print(f" Week ending {week}")
    print("=" * 66)
    print(" CORE (70%):")
    for a, w in CORE.items():
        print(f"      {a:<5} {CORE_WEIGHT*w*100:>5.1f}% of total")
    print(f" TREND SLEEVE (30%):  {len(up)} markets trending, "
          f"{cash*100:.0f}% of total in cash")
    if up:
        print("   HOLDING (uptrend):")
        for c in sorted(up, key=lambda x: weights[x], reverse=True):
            print(f"      {c:<6} {weights[c]*100:>4.1f}% of total")
    if off:
        print("   AVOIDING (not trending, in cash): " + ", ".join(sorted(off)))
    print("-" * 66)
    print(f" Paper account: {state['equity']:,.2f}  ({ret:+.2f}% vs "
          f"{state['start_equity']:,.0f} start, {len(state['history'])} weeks)")
    print("=" * 66 + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
        print("Combined paper account wiped.")
        return

    prices = fresh_prices()
    state = load_state()
    if not args.status:
        state = run_cycle(state, prices)
        save_state(state)
    print_target(state, prices)


if __name__ == "__main__":
    main()
