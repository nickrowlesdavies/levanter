#!/usr/bin/env python3
"""
Strategy research: walk-forward every strategy across all majors and rank
them by honest, out-of-sample performance.

    python research.py

Uses free yfinance DAILY data (fast, 15y history, no API quota) to compare
strategy FAMILIES. The winner is then re-validated on the 4h trial timeframe
before it drives anything live - families that work daily usually carry to
4h, but we never assume it.

Every number printed is out-of-sample: parameters were chosen only on data
prior to the window they were tested on. There is no hindsight in these
results.
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

START, END = "2010-01-01", "2024-12-31"
START_EQUITY, RISK_PCT = 10000.0, 1.0

INSTRUMENTS = [
    Instrument("EURUSD", "EURUSD=X", 0.0001, 1.0),
    Instrument("GBPUSD", "GBPUSD=X", 0.0001, 1.2),
    Instrument("USDJPY", "USDJPY=X", 0.01, 1.0),
    Instrument("AUDUSD", "AUDUSD=X", 0.0001, 1.2),
    Instrument("USDCHF", "USDCHF=X", 0.0001, 1.5),
]

# Small, sane parameter grids. Walk-forward picks per window from these.
GRIDS = {
    "trend_breakout": {"breakout_lookback": [20, 40], "trend_ma": [100, 200],
                       "atr_target_mult": [2.0, 3.0]},
    "ma_crossover":   {"fast": [10, 20], "slow": [50, 100],
                       "atr_target_mult": [2.0, 3.0]},
    "momentum":       {"lookback": [40, 80], "threshold": [0.02, 0.04],
                       "atr_target_mult": [2.0, 3.0]},
    "mean_reversion": {"bb_std": [2.0, 2.5], "rsi_low": [25, 30],
                       "atr_target_mult": [1.0, 1.5]},
    "carry":          {"carry_threshold": [0.5, 1.0], "trend_ma": [100, 200],
                       "atr_target_mult": [3.0, 5.0]},
}


def main():
    # Cache data once per pair, with the carry column attached.
    data, carry = {}, {}
    for inst in INSTRUMENTS:
        df = load_candles(inst, START, END, "1d", source="yfinance").copy()
        c = carry_for_pair(inst.name, df.index)
        df["carry"] = c
        data[inst.name] = df
        carry[inst.name] = c

    rows = []
    portfolio_curves = {}   # strategy -> normalized portfolio OOS curve

    for sname, cls in ALL_STRATEGIES.items():
        grid = GRIDS[sname]
        per_pair_norm = []
        agg = {"trades": 0, "ret": [], "expR": [], "sharpe": [], "dd": [], "prof": 0}
        pair_count = 0

        for inst in INSTRUMENTS:
            df = data[inst.name]
            wf = walk_forward(df, cls, grid, inst, START_EQUITY, RISK_PCT,
                              train_years=4, test_years=2, step_years=2,
                              select="sharpe", carry_annual=carry[inst.name])
            m = wf["metrics"]
            if m.get("num_trades", 0) == 0 or len(wf["curve"]) == 0:
                continue
            pair_count += 1
            agg["trades"] += m["num_trades"]
            agg["ret"].append(m["total_return_pct"])
            agg["expR"].append(m.get("expectancy_R", np.nan))
            agg["sharpe"].append(m.get("sharpe", np.nan))
            agg["dd"].append(m.get("max_drawdown_pct", np.nan))
            agg["prof"] += 1 if m["total_return_pct"] > 0 else 0
            norm = wf["curve"] / wf["curve"].iloc[0] * 100
            per_pair_norm.append(norm)

        if pair_count == 0:
            continue

        # Equal-weight portfolio OOS curve = mean of per-pair normalized curves.
        combined = pd.concat(per_pair_norm, axis=1).ffill().dropna()
        portfolio_curves[sname] = combined.mean(axis=1)

        rows.append({
            "strategy": sname,
            "pairs": pair_count,
            "oos_trades": agg["trades"],
            "avg_return_%": np.nanmean(agg["ret"]),
            "avg_expectancy_R": np.nanmean(agg["expR"]),
            "avg_sharpe": np.nanmean(agg["sharpe"]),
            "avg_maxDD_%": np.nanmean(agg["dd"]),
            "pairs_profitable": f"{agg['prof']}/{pair_count}",
        })

    table = pd.DataFrame(rows).sort_values("avg_expectancy_R", ascending=False)
    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    print("\n" + "=" * 78)
    print(" WALK-FORWARD OUT-OF-SAMPLE RESULTS  (daily majors, 2010-2024)")
    print(" Params chosen only on prior data each window. No hindsight.")
    print(" P&L now includes the carry roll (interest differential) for all held")
    print(" positions - more realistic than price-only.")
    print("=" * 78)
    print(table.to_string(index=False))
    print("=" * 78)

    best = table.iloc[0]["strategy"] if len(table) else None
    if best:
        print(f"\n Most robust family by OOS expectancy: {best}")
        print(" (Positive expectancy across pairs after costs = worth carrying to 4h.)")

    # Chart the portfolio OOS curves.
    plt.figure(figsize=(11, 6))
    for sname, curve in portfolio_curves.items():
        plt.plot(curve.index, curve.values, label=sname, linewidth=1.4)
    plt.axhline(100, color="grey", linestyle="--", linewidth=0.8)
    plt.title("Walk-forward OOS equity by strategy (equal-weight majors, start=100)")
    plt.ylabel("Equity (indexed to 100)")
    plt.legend()
    plt.tight_layout()
    out = "reports/walkforward_comparison.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
