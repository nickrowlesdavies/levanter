#!/usr/bin/env python3
"""
Validate mean-reversion on the 4h trial timeframe.

The daily research picked mean-reversion as the best risk-adjusted family.
This checks whether that edge carries to 4h - the timeframe the live paper
trial actually runs on. Twelve Data's free tier gives ~2.9 years of 4h
history, so we use a compact walk-forward (train 1y, test 1y, rolling).
Every number is out-of-sample.

    python validate_4h.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.loader import Instrument, load_candles
from src.data.rates import carry_for_pair
from src.signals.registry import ALL_STRATEGIES
from src.backtest.walkforward import walk_forward
from src.backtest.metrics import format_report

START, END = "2020-01-01", "2027-01-01"   # free tier returns the recent ~5000 bars
START_EQUITY, RISK_PCT = 10000.0, 1.0

INSTRUMENTS = [
    Instrument("EURUSD", "EURUSD=X", 0.0001, 1.0),
    Instrument("GBPUSD", "GBPUSD=X", 0.0001, 1.2),
    Instrument("USDJPY", "USDJPY=X", 0.01, 1.0),
    Instrument("AUDUSD", "AUDUSD=X", 0.0001, 1.2),
    Instrument("USDCHF", "USDCHF=X", 0.0001, 1.5),
]

GRID = {"bb_std": [2.0, 2.5], "rsi_low": [25, 30], "atr_target_mult": [1.0, 1.5]}


def main():
    cls = ALL_STRATEGIES["mean_reversion"]
    print("\n" + "=" * 74)
    print(" MEAN-REVERSION on 4h  (walk-forward, train 1y / test 1y, rolling)")
    print(" Twelve Data 4h majors. Out-of-sample. Roll included.")
    print("=" * 74)

    curves, rets, expR, trades_tot, prof = [], [], [], 0, 0
    pair_n = 0

    for inst in INSTRUMENTS:
        df = load_candles(inst, START, END, "4h", source="twelvedata").copy()
        if len(df) < 500:
            print(f"  {inst.name}: only {len(df)} bars, skipping")
            continue
        df["carry"] = carry_for_pair(inst.name, df.index)
        wf = walk_forward(df, cls, GRID, inst, START_EQUITY, RISK_PCT,
                          train_years=1, test_years=1, step_years=1,
                          select="sharpe", carry_annual=df["carry"],
                          min_train_trades=5)
        m = wf["metrics"]
        if m.get("num_trades", 0) == 0:
            print(f"  {inst.name}: no OOS trades")
            continue
        pair_n += 1
        trades_tot += m["num_trades"]
        rets.append(m["total_return_pct"])
        expR.append(m.get("expectancy_R", np.nan))
        prof += 1 if m["total_return_pct"] > 0 else 0
        print(format_report(inst.name, m))
        c = wf["curve"] / wf["curve"].iloc[0] * 100
        curves.append((inst.name, c))

    print("-" * 74)
    if pair_n:
        print(f"  4h OOS: {pair_n} pairs, {trades_tot} trades, "
              f"avg return {np.nanmean(rets):+.2f}%, "
              f"avg expectancy {np.nanmean(expR):+.3f}R, "
              f"{prof}/{pair_n} pairs profitable")
        print("\n  Compare daily mean-reversion: +1.31% avg, +0.04R, 2/5 profitable.")
        print("  Edge carries to 4h if 4h numbers are in the same ballpark (>0).")
    else:
        print("  No pairs produced OOS trades on 4h (data too short for windows).")
    print("=" * 74)

    if curves:
        plt.figure(figsize=(11, 6))
        for name, c in curves:
            plt.plot(c.index, c.values, linewidth=1.3, label=name)
        plt.axhline(100, color="grey", linestyle="--", linewidth=0.8)
        plt.title("Mean-reversion on 4h - out-of-sample equity (start=100)")
        plt.ylabel("Equity (indexed to 100)")
        plt.legend()
        plt.tight_layout()
        out = "reports/mean_reversion_4h.png"
        plt.savefig(out, dpi=130)
        print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
