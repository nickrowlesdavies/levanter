#!/usr/bin/env python3
"""
Live crypto weekly signal - momentum + regime, run forward.

Once a week: rank the coin universe by trailing momentum and, if the market
regime is risk-on (BTC above its 15-week MA), recommend holding the top-K.
If risk-off, recommend sitting in stablecoin. Books the result into its own
paper account so it runs forward alongside the FX trial.

    python crypto_signal.py           # run a weekly cycle
    python crypto_signal.py --status  # show current holdings + account
    python crypto_signal.py --reset   # wipe the crypto paper account

Simulated only - never places a real order. HONEST EXPECTATION: walk-forward
showed this is roughly BTC-like returns with somewhat lower drawdown, not an
outsized edge. This trial is for learning whether even that thin edge holds
up live.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from crypto_momentum import load_prices, COINS

# Parameters the walk-forward consistently favoured.
LOOKBACK, K, SKIP, REGIME_MA = 8, 5, 1, 15
MARKET = "BTC"
STATE_PATH = "reports/crypto_state.json"
START_EQUITY = 10000.0
FEE_BPS = 10.0


def latest_weekly() -> pd.DataFrame:
    """Fresh weekly prices (bypass cache so the signal is current)."""
    if os.path.exists("data_cache/crypto_weekly.csv"):
        os.remove("data_cache/crypto_weekly.csv")
    return load_prices()


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"start_equity": START_EQUITY, "equity": START_EQUITY,
            "last_week": None, "holdings": [], "history": []}


def save_state(s: dict):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(s, f, indent=2, default=str)


def compute_signal(prices: pd.DataFrame):
    """Return (regime_on, ranked_top, momentum_series) as of the last week."""
    mom = prices.shift(SKIP) / prices.shift(SKIP + LOOKBACK) - 1.0
    last = mom.iloc[-1].dropna().sort_values(ascending=False)
    mkt = prices[MARKET]
    mkt_ma = mkt.rolling(REGIME_MA).mean()
    regime_on = bool(mkt.iloc[-1] > mkt_ma.iloc[-1])
    top = list(last.index[:K])
    return regime_on, top, last


def run_cycle(state: dict, prices: pd.DataFrame) -> dict:
    week = str(prices.index[-1].date())
    if state["last_week"] == week:
        return state  # already processed this week's bar

    # Realise last week's holdings vs this week's prices.
    if state["holdings"] and len(state["history"]):
        prev_prices = state.get("_last_prices", {})
        rets = []
        for c in state["holdings"]:
            if c in prev_prices and c in prices.columns:
                rets.append(prices[c].iloc[-1] / prev_prices[c] - 1)
        realized = float(np.mean(rets)) if rets else 0.0
        state["equity"] *= (1 + realized)

    regime_on, top, ranked = compute_signal(prices)
    new_holdings = top if regime_on else []

    # Turnover cost.
    turn = len(set(new_holdings) ^ set(state["holdings"])) / max(2 * K, 1)
    state["equity"] *= (1 - turn * (FEE_BPS / 10000.0))

    state["holdings"] = new_holdings
    state["last_week"] = week
    state["_last_prices"] = {c: float(prices[c].iloc[-1])
                             for c in new_holdings if c in prices.columns}
    state["history"].append({"week": week, "regime": "ON" if regime_on else "CASH",
                             "holdings": new_holdings,
                             "equity": round(state["equity"], 2)})
    return state


def print_signal(state: dict, prices: pd.DataFrame):
    regime_on, top, ranked = compute_signal(prices)
    ret = (state["equity"] / state["start_equity"] - 1) * 100
    week = str(prices.index[-1].date())
    print("\n" + "=" * 66)
    print(f" CRYPTO WEEKLY SIGNAL  (momentum L={LOOKBACK}/top-{K} + "
          f"{REGIME_MA}wk regime)")
    print(f" Week ending {week}")
    print("=" * 66)
    if regime_on:
        print(" REGIME: RISK-ON (BTC above its 15-week MA)")
        print(" RECOMMENDED HOLDINGS (equal weight):")
        for c in top:
            print(f"      HOLD {c:<5}  (momentum {ranked[c]*100:+.0f}% over "
                  f"{LOOKBACK}wk)")
    else:
        print(" REGIME: RISK-OFF (BTC below its 15-week MA)")
        print(" RECOMMENDED: 100% STABLECOIN (sit out until regime turns)")
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
        print("Crypto paper account wiped.")
        return

    prices = latest_weekly()
    state = load_state()
    if not args.status:
        state = run_cycle(state, prices)
        save_state(state)
    print_signal(state, prices)


if __name__ == "__main__":
    main()
