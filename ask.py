#!/usr/bin/env python3
"""
Interrogate the crypto map. Answers quick questions from reports/crypto_map.json.

    python ask.py                 # overview: regime, model buy-basket, movers
    python ask.py best            # best by 90-day momentum (in uptrend)
    python ask.py best 7d         # best over the last 7 days (short horizon)
    python ask.py best 30d        # best over the last 30 days
    python ask.py BTC             # detail on one coin
    python ask.py stables         # stablecoin peg status

These are the MODEL'S mechanical read (trend + momentum), NOT financial advice.
Shorter horizons (7d) are noisier and less reliable than the model's native
weekly-to-monthly momentum.
"""
from __future__ import annotations

import json
import os
import sys

J = "reports/crypto_map.json"
HZN = {"7": ("chg7", "7-day"), "7d": ("chg7", "7-day"),
       "30": ("chg30", "30-day"), "30d": ("chg30", "30-day"),
       "90": ("ret", "90-day"), "90d": ("ret", "90-day")}


def load():
    if not os.path.exists(J):
        sys.exit("No crypto_map.json yet. Run: ./run.sh crypto_map.py --force")
    return json.load(open(J))


def mv(v):
    return "  n/a" if v is None else f"{v:+6.1f}%"


def overview(d):
    reg = "RISK-ON" if d["regime_on"] else "RISK-OFF"
    print(f"\nRegime: {reg}   (window {d['start']} -> {d['end']})")
    print(f"Market: cap-weighted {d['cap_weighted_ret']:+.1f}%  "
          f"equal-weight {d['equal_weighted_ret']:+.1f}%  "
          f"BTC dominance {d['btc_dominance']:.0f}%")
    if d["regime_on"] and d["recommendation"]:
        print("Model buy-basket: " + ", ".join(d["recommendation"]))
    elif not d["regime_on"]:
        print("Model: hold stablecoin (risk-off).")
    cs = d["coins"]
    print("\nTop 5 movers (90d):  " +
          "  ".join(f"{c['coin']} {c['ret']:+.0f}%" for c in cs[:5]))
    print("Worst 5 (90d):       " +
          "  ".join(f"{c['coin']} {c['ret']:+.0f}%" for c in cs[-5:]))
    print()


def best(d, args):
    field, label = "ret", "90-day"
    for a in args:
        if a.lower() in HZN:
            field, label = HZN[a.lower()]
    up = [c for c in d["coins"] if c.get("trend") == "up" and c.get(field) is not None]
    up.sort(key=lambda c: c[field], reverse=True)
    print(f"\nBest by {label} momentum, in an uptrend "
          f"(model read, not advice){' - regime RISK-OFF, caution' if not d['regime_on'] else ''}:")
    print(f"  {'#':<3}{'coin':<7}{'price':>12}{'7d':>9}{'30d':>9}{'90d':>9}"
          f"{'risk':>10}  signal")
    for i, c in enumerate(up[:6], 1):
        p = c["price"]
        ps = f"${p:,.0f}" if p >= 1000 else f"${p:,.2f}" if p >= 1 else f"${p:.4f}"
        risk = f"{c.get('risk','?')} {c.get('risk_band','')}"
        print(f"  {i:<3}{c['coin']:<7}{ps:>12}{mv(c.get('chg7'))}"
              f"{mv(c.get('chg30'))}{mv(c.get('ret'))}{risk:>10}  {c.get('signal','')}")
    if label == "7-day":
        print("  Note: 7-day is short and noisy; the model's edge is weekly-to-monthly.")
    print()


def coin_detail(d, sym):
    c = next((x for x in d["coins"] if x["coin"] == sym.upper()), None)
    if not c:
        print(f"{sym.upper()} not in the tracked universe.")
        return
    print(f"\n{c['coin']}  (rank {c.get('rank','?')} by 90d momentum)")
    print(f"  price ${c['price']:,.4f}   trend {c.get('trend')}   signal {c.get('signal')}")
    print(f"  moves: 7d {mv(c.get('chg7'))}  30d {mv(c.get('chg30'))}  90d {mv(c.get('ret'))}")
    print(f"  risk score {c.get('risk','?')}/100 ({c.get('risk_band','?')})   "
          f"vol {c.get('vol',0):.0f}%   90d max drawdown {c.get('dd',0):.0f}%\n")


def stables(d):
    print("\nStablecoin peg monitor:")
    for s in d["stables"]:
        print(f"  {s['coin']:<7} ${s['price']:.4f}  90d low ${s['minp']:.4f}  "
              f"[{s['status']}]")
    print()


def main():
    d = load()
    args = sys.argv[1:]
    if not args:
        overview(d)
    elif args[0].lower() == "best":
        best(d, args[1:])
    elif args[0].lower() in ("stable", "stables", "peg"):
        stables(d)
    else:
        coin_detail(d, args[0])


if __name__ == "__main__":
    main()
