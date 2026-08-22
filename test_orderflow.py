#!/usr/bin/env python3
"""
Honest test: does adding ORDER FLOW (taker-buy ratio + funding) improve the
crypto directional predictions, or not? Backtests the perp-listed coins over
~3 months, point-in-time, scoring the SAME dates with and without the
order-flow term. If accuracy doesn't rise out-of-sample, order flow doesn't
help at these horizons and we say so.

    python test_orderflow.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from backtest_predict import fetch, inputs_at, GEN, HALVING, phase  # noqa
from orderflow import orderflow, PERP

HORIZONS = [7, 30]
WINDOW = 95


def _clip(v, lo=-1, hi=1):
    return max(lo, min(hi, v))


def _logistic(x):
    return 1 / (1 + math.exp(-x))


def bull_base(s, h):
    v = _clip(-s.get("pct_vs_trend", 0) / 40)
    m7 = _clip(s.get("chg7", 0) / 15)
    m30 = _clip(s.get("chg30", 0) / 40)
    tr = 0.6 if s.get("trend") == "up" else -0.6
    cyc = {"Pre-peak bull": 0.4, "Peak window": -0.1,
           "Post-peak cooldown": -0.4, "Late cycle": -0.2}.get(s.get("phase"), 0)
    reg = 0.4 if s.get("regime") else -0.4
    return (0.5 * m7 + 0.25 * tr + 0.15 * reg + 0.1 * m30) if h <= 7 \
        else (0.4 * v + 0.25 * cyc + 0.2 * tr + 0.15 * m30)


def of_term(s):
    tk = _clip((s.get("taker7", 0.5) - 0.5) * 20)     # aggressive-buy pressure
    fd = -_clip(s.get("funding", 0.0) * 3000)         # crowded-long = contrarian
    return 0.6 * tk + 0.4 * fd


def main():
    coins = list(PERP.keys())
    prices = {c: fetch(c + "-USD") for c in coins}
    of = {c: orderflow(c) for c in coins}
    btc = prices["BTC"]
    btc_ma = btc.rolling(70).mean()
    last = btc.index[-1]

    base_hits, of_hits, n = {7: 0, 30: 0}, {7: 0, 30: 0}, {7: 0, 30: 0}
    for c in coins:
        s, ofd = prices.get(c), of.get(c)
        if s is None or ofd is None or len(s) < 260:
            continue
        for h in HORIZONS:
            k = 1
            while True:
                tt = last - pd.Timedelta(days=h + (k - 1) * h)
                if (last - tt).days > WINDOW:
                    break
                k += 1
                idx = s.index[s.index <= tt]
                if len(idx) == 0:
                    continue
                t = idx[-1]
                inp = inputs_at(t, c, s, False, btc, btc_ma)
                if inp is None:
                    continue
                after = s[s.index >= t + pd.Timedelta(days=h)]
                if len(after) == 0:
                    continue
                # point-in-time order flow at t
                ofa = ofd[ofd.index <= t]
                if len(ofa) < 7:
                    continue
                inp["taker7"] = float(ofa["taker_ratio"].tail(7).mean())
                inp["funding"] = float(ofa["funding"].tail(3).mean())

                actual = "up" if float(after.iloc[0]) >= inp["price"] else "down"
                pb = "up" if _logistic(2 * bull_base(inp, h)) >= 0.5 else "down"
                w = 0.35 if h <= 7 else 0.20
                po = "up" if _logistic(2 * (bull_base(inp, h) + w * of_term(inp))) >= 0.5 else "down"
                n[h] += 1
                base_hits[h] += (pb == actual)
                of_hits[h] += (po == actual)

    print("\n Does order flow help crypto? (same dates, with vs without)\n")
    print(f" {'horizon':<8}{'n':>5}{'base':>9}{'+flow':>9}")
    tb = to = tn = 0
    for h in HORIZONS:
        if n[h]:
            print(f" {str(h)+'d':<8}{n[h]:>5}{base_hits[h]/n[h]*100:>8.0f}%"
                  f"{of_hits[h]/n[h]*100:>8.0f}%")
            tb += base_hits[h]; to += of_hits[h]; tn += n[h]
    print(f" {'ALL':<8}{tn:>5}{tb/tn*100:>8.0f}%{to/tn*100:>8.0f}%")
    delta = (to - tb) / tn * 100
    print(f"\n Order flow moves crypto accuracy by {delta:+.1f} points "
          f"({'keep it' if delta >= 2 else 'no real help - drop it'}).")
    print(" Small sample. Not a forecast. Educational only.\n")


if __name__ == "__main__":
    main()
