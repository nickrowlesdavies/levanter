#!/usr/bin/env python3
"""
Live paper tracker: VOL-TARGETED diversified basket - the one sizing overlay
that survived honest backtesting (basket Sharpe 0.76 -> 0.81, lower vol, at
equal average exposure).

Equal-weight 8 assets (SPX, gold, oil, copper, silver, BTC, ETH, SOL); each
asset's weight is scaled inversely to its recent volatility (calm -> a bit
more, turbulent -> a bit less), normalised point-in-time so average gross
exposure stays ~1x. Rebalances weekly, books into a simulated account.

    python vol_basket_tracker.py            # weekly cycle
    python vol_basket_tracker.py --status   # show state, no change
    python vol_basket_tracker.py --reset     # wipe the paper account
Simulated only - never places a real order.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ASSETS = {"SPX": "SPY", "GOLD": "GC=F", "OIL": "CL=F", "COPPER": "HG=F",
          "SILVER": "SI=F", "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}
N = len(ASSETS)
VOL_WIN, LEV_CAP = 20, 2.5
STATE = "reports/volbasket_state.json"
START_EQUITY = 10000.0


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="400d", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def target_weights():
    weights, prices = {}, {}
    for a, sym in ASSETS.items():
        s = fetch(sym)
        if s is None or len(s) < VOL_WIN + 60:
            continue
        ret = s.pct_change()
        rv = ret.rolling(VOL_WIN).std()
        med = rv.expanding(min_periods=60).median().iloc[-1]
        lev = float(np.clip(med / rv.iloc[-1], 0, LEV_CAP)) if rv.iloc[-1] else 1.0
        weights[a] = (1.0 / N) * lev
        prices[a] = float(s.iloc[-1])
    return weights, prices


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"start_equity": START_EQUITY, "equity": START_EQUITY,
            "last_week": None, "weights": {}, "_prices": {}, "history": []}


def save_state(s):
    os.makedirs("reports", exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=2, default=str)


def run_cycle(state):
    wk = "-".join(map(str, datetime.utcnow().isocalendar()[:2]))
    if state["last_week"] == wk:
        return state
    weights, prices = target_weights()
    if not weights:
        return state
    # realise last week's return from stored prices
    if state["weights"] and state["_prices"]:
        r = 0.0
        for a, w in state["weights"].items():
            p0 = state["_prices"].get(a)
            if p0 and a in prices:
                r += w * (prices[a] / p0 - 1)
        state["equity"] *= (1 + r)
    state["weights"], state["_prices"], state["last_week"] = weights, prices, wk
    state["history"].append({"week": str(datetime.utcnow().date()),
                             "equity": round(state["equity"], 2),
                             "gross": round(sum(weights.values()), 3)})
    return state


def show(state):
    w = state["weights"]
    ret = (state["equity"] / state["start_equity"] - 1) * 100
    gross = sum(w.values()) if w else 0
    print("\n" + "=" * 60)
    print(" VOL-TARGETED BASKET  (8 assets, risk-scaled, weekly)")
    print("=" * 60)
    if w:
        print(f" Gross exposure {gross*100:.0f}%  (avg ~100%). Weights:")
        for a, wt in sorted(w.items(), key=lambda x: -x[1]):
            base = 100.0 / N
            tilt = "up" if wt * 100 > base + 1 else "down" if wt * 100 < base - 1 else "flat"
            print(f"    {a:<7}{wt*100:>5.1f}%  ({tilt} vs {base:.0f}% equal)")
    print("-" * 60)
    print(f" Paper account: {state['equity']:,.2f}  ({ret:+.2f}% vs "
          f"{state['start_equity']:,.0f} start, {len(state['history'])} weeks)")
    print("=" * 60 + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    if args.reset:
        if os.path.exists(STATE):
            os.remove(STATE)
        print("Vol-basket paper account wiped.")
        return
    state = load_state()
    if not args.status:
        state = run_cycle(state)
        save_state(state)
    show(state)


if __name__ == "__main__":
    main()
