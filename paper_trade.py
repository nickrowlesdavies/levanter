#!/usr/bin/env python3
"""
Run the forward paper-trading loop (the trial).

    python paper_trade.py --once                 # one cycle, then exit (good for cron)
    python paper_trade.py --loop --interval 3600 # run forever, one cycle/hour
    python paper_trade.py --status               # print account state, do nothing
    python paper_trade.py --reset                # wipe the paper account and start fresh

Data source and instruments come from config.yaml. With data.source: "yfinance"
you can test the loop today (no token). Flip to "oanda" once your practice
token is set and it streams forward on live broker prices - same logic.

Nothing here places a real order. It maintains a SIMULATED account only.
"""
from __future__ import annotations

import argparse
import os
import time

import yaml

from src.paper.trader import PaperTrader


def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)


def run_once(trader: PaperTrader):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{stamp}] running cycle ({trader.source}, {trader.interval})...")
    actions = trader.run_cycle()
    if not actions:
        print("  no new signals or position changes this cycle.")
    for a in actions:
        line = f"  * {a['action']:<18} {a['instrument']:<7} {a['note']}"
        print(line)
    print("\n" + trader.summary())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--once", action="store_true", help="run a single cycle")
    ap.add_argument("--loop", action="store_true", help="run continuously")
    ap.add_argument("--interval", type=int, default=3600,
                    help="seconds between cycles in --loop mode")
    ap.add_argument("--status", action="store_true", help="print state only")
    ap.add_argument("--reset", action="store_true", help="wipe paper account")
    args = ap.parse_args()

    cfg = load_config(args.config)
    trader = PaperTrader(cfg)

    if args.reset:
        for p in (trader.state_path, trader.log_path):
            if os.path.exists(p):
                os.remove(p)
        print("Paper account wiped. Fresh start on next cycle.")
        return

    if args.status:
        print(trader.summary())
        return

    if args.loop:
        print(f"Looping every {args.interval}s. Ctrl-C to stop.")
        try:
            while True:
                run_once(trader)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped. State saved.")
        return

    # default: single cycle
    run_once(trader)


if __name__ == "__main__":
    main()
