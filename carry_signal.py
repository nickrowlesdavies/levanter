#!/usr/bin/env python3
"""
Live carry overlay - the carry basket run forward as a monthly signal.

Each run: rank the 9 currencies by current yield spread vs USD, and if a new
month has started, rebalance the basket (long top-K, short bottom-K), booking
the result into a separate paper account. Prints the current recommended
positions, translated into the actual pair trades you'd place.

    python carry_signal.py           # run a cycle (rebalances once per month)
    python carry_signal.py --status  # show current basket + account, no change
    python carry_signal.py --reset   # wipe the carry paper account

Simulated account only - never sends a real order. This is the macro overlay
that complements the 4h mean-reversion trial (different timeframe, different
return driver, low correlation).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import pandas as pd

from src.data.loader import Instrument, load_candles
from src.data.rates import fetch_rate
from carry_basket import CCY_PAIRS, K, COST_BPS

STATE_PATH = "reports/carry_state.json"
START_EQUITY = 10000.0


def current_usd_values() -> dict:
    """Latest 'value of 1 unit of ccy in USD' for each currency."""
    end = (datetime.now(timezone.utc).replace(tzinfo=None)).strftime("%Y-%m-%d")
    out = {}
    for ccy, (sym, inv) in CCY_PAIRS.items():
        inst = Instrument(ccy, sym, 0.01 if "JPY" in sym else 0.0001, 1.0)
        px = load_candles(inst, "2025-01-01", end, "1d",
                          source="yfinance", use_cache=False)["close"]
        last = float(px.iloc[-1])
        out[ccy] = 1.0 / last if inv else last
    return out


def current_spreads() -> dict:
    """Latest annualised yield spread vs USD for each currency (%)."""
    usd = float(fetch_rate("USD", use_cache=False).iloc[-1])
    out = {}
    for ccy in CCY_PAIRS:
        out[ccy] = float(fetch_rate(ccy, use_cache=False).iloc[-1]) - usd
    return out


def pair_action(ccy: str, direction: int) -> str:
    """Translate 'long/short currency' into the actual pair trade."""
    sym, inv = CCY_PAIRS[ccy]
    pair = sym.replace("=X", "")
    # long ccy: BUY a USD-quote pair (EURUSD), SELL a USD-base pair (USDJPY)
    buy = (direction == 1) != inv
    return f"{'BUY ' if buy else 'SELL'} {pair}"


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"start_equity": START_EQUITY, "equity": START_EQUITY,
            "last_rebalance": None, "positions": {}, "history": []}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)


def choose_basket(spreads: dict, k: int):
    ranked = sorted(spreads.items(), key=lambda kv: kv[1], reverse=True)
    longs = [c for c, _ in ranked[:k]]
    shorts = [c for c, _ in ranked[-k:]]
    return longs, shorts


def run_cycle(state: dict) -> dict:
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    month = today.strftime("%Y-%m")
    spreads = current_spreads()
    vals = current_usd_values()

    if state["last_rebalance"] == month:
        return state  # already rebalanced this month; nothing to do

    # 1. Realise existing positions (price move + carry roll) minus turnover cost.
    realized = 0.0
    for ccy, pos in state["positions"].items():
        price_ret = vals[ccy] / pos["entry_val"] - 1.0
        days = max((today - datetime.fromisoformat(pos["entry_date"])).days, 0)
        carry = (pos["entry_spread"] / 100.0) * (days / 365.25)
        realized += pos["weight"] * (price_ret + carry)

    # 2. Build the new basket.
    longs, shorts = choose_basket(spreads, K)
    new_pos = {}
    for c in longs:
        new_pos[c] = {"weight": 1.0 / K, "entry_val": vals[c],
                      "entry_spread": spreads[c], "entry_date": today.isoformat()}
    for c in shorts:
        new_pos[c] = {"weight": -1.0 / K, "entry_val": vals[c],
                      "entry_spread": spreads[c], "entry_date": today.isoformat()}

    # 3. Turnover cost between old and new weights.
    old_w = {c: p["weight"] for c, p in state["positions"].items()}
    new_w = {c: p["weight"] for c, p in new_pos.items()}
    turnover = sum(abs(new_w.get(c, 0) - old_w.get(c, 0))
                   for c in set(old_w) | set(new_w))
    cost = turnover * (COST_BPS / 10000.0)

    state["equity"] *= (1 + realized - cost)
    state["positions"] = new_pos
    state["last_rebalance"] = month
    state["history"].append({"month": month, "realized_pct": round(realized * 100, 3),
                             "equity": round(state["equity"], 2),
                             "longs": longs, "shorts": shorts})
    return state


def print_basket(state: dict):
    spreads = current_spreads()
    longs, shorts = choose_basket(spreads, K)
    ret = (state["equity"] / state["start_equity"] - 1) * 100
    print("\n" + "=" * 66)
    print(f" CARRY BASKET OVERLAY  (monthly, long top-{K} / short bottom-{K})")
    print(f" Rebalanced for: {state['last_rebalance'] or '(not yet)'}")
    print("=" * 66)
    print(" RECOMMENDED POSITIONS (current yield ranking):")
    print("   LONG  the high-yielders:")
    for c in longs:
        print(f"      {c}  spread {spreads[c]:+.2f}%   ->  {pair_action(c, 1)}")
    print("   SHORT the low-yielders:")
    for c in shorts:
        print(f"      {c}  spread {spreads[c]:+.2f}%   ->  {pair_action(c, -1)}")
    print("-" * 66)
    print(f" Paper account: {state['equity']:,.2f}  ({ret:+.2f}% vs "
          f"{state['start_equity']:,.0f} start, {len(state['history'])} rebalances)")
    print("=" * 66 + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if args.reset:
        if os.path.exists(STATE_PATH):
            os.remove(STATE_PATH)
        print("Carry paper account wiped.")
        return

    state = load_state()
    if not args.status:
        state = run_cycle(state)
        save_state(state)
    print_basket(state)


if __name__ == "__main__":
    main()
