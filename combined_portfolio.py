#!/usr/bin/env python3
"""
Combined portfolio: 60/40 core + diversified trend sleeve.

The real payoff of the whole research arc. Neither piece is a standout on
its own (60/40 Sharpe ~1.0, trend ~0.8), but they are nearly UNCORRELATED -
trend makes money in the crises where 60/40 bleeds. When you blend two
uncorrelated return streams, diversification cuts the combined volatility
faster than it cuts the combined return, so the BLEND can out-Sharpe either
piece alone. This tests whether that actually happens here.

Method (all out-of-sample):
  * trend sleeve  = the walk-forward OOS returns from trend_basket.py
  * core          = 60/40 (60% SPY, 40% IEF), weekly
  * trend is scaled to the core's volatility (it runs at ~5% vol; matching
    lets the allocation weights mean risk, not just capital). Achievable
    with modest leverage since it's low-vol.
  * blend at several core/trend splits; report Sharpe, CAGR, vol, maxDD.

    python combined_portfolio.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from trend_basket import load_prices, walk_forward, benchmark_6040, _metrics


def main():
    prices = load_prices()
    wf_curve, r_trend, _ = walk_forward(prices)
    _, r_core = benchmark_6040(prices)

    # Align on common weeks (the OOS window).
    df = pd.concat([r_core.rename("core"), r_trend.rename("trend")], axis=1).dropna()
    r_core, r_trend = df["core"], df["trend"]

    corr = r_core.corr(r_trend)
    vol_core = r_core.std()
    vol_trend = r_trend.std()
    lever = vol_core / vol_trend                 # scale trend to core's vol
    r_trend_m = r_trend * lever

    print("\n" + "=" * 70)
    print(" COMBINED PORTFOLIO: 60/40 CORE + TREND SLEEVE (out-of-sample)")
    print("=" * 70)
    print(f" OOS window     : {df.index[0].date()} -> {df.index[-1].date()} "
          f"({len(df)} weeks)")
    diver = ("strong diversifier" if corr < 0.3 else
             "moderate diversifier" if corr < 0.6 else "weak diversifier")
    print(f" Correlation    : {corr:+.2f}  ({diver}; lower = more benefit)")
    print(f" Trend scaled x{lever:.1f} to match core volatility")
    print("-" * 70)
    print(f" {'core%':>6} {'trend%':>7} | {'CAGR%':>7} {'Sharpe':>7} "
          f"{'vol%':>6} {'maxDD%':>8}")
    print("-" * 70)

    rows = {}
    for w_trend in (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
        blend = (1 - w_trend) * r_core + w_trend * r_trend_m
        eq = (1 + blend).cumprod()
        m = _metrics(eq, blend)
        rows[w_trend] = (eq, m)
        tag = ""
        print(f" {(1-w_trend)*100:>5.0f}% {w_trend*100:>6.0f}% | "
              f"{m['cagr_pct']:>7.1f} {m['sharpe']:>7.2f} {m['vol_pct']:>6.1f} "
              f"{m['maxdd_pct']:>8.1f}{tag}")

    # Identify the best-Sharpe blend and compare to the pure pieces.
    best_w = max(rows, key=lambda w: rows[w][1]["sharpe"])
    s_core = rows[0.0][1]["sharpe"]
    s_trend = rows[1.0][1]["sharpe"]
    s_best = rows[best_w][1]["sharpe"]
    print("-" * 70)
    print(f" Pure core (0% trend) Sharpe : {s_core:.2f}")
    print(f" Pure trend (100%)    Sharpe : {s_trend:.2f}")
    print(f" BEST BLEND {int((1-best_w)*100)}/{int(best_w*100)}  Sharpe : "
          f"{s_best:.2f}   maxDD {rows[best_w][1]['maxdd_pct']:.0f}%")
    beat = s_best > max(s_core, s_trend) + 1e-9
    print("=" * 70)
    if beat:
        print(f" VERDICT: the BLEND beats both pieces on Sharpe "
              f"({s_best:.2f} > core {s_core:.2f}, trend {s_trend:.2f}).")
        print(" Diversification free lunch confirmed: uncorrelated sleeves ->")
        print(" better risk-adjusted return than either alone.")
    else:
        print(f" VERDICT: best blend Sharpe {s_best:.2f} does not exceed the best "
              f"single piece ({max(s_core, s_trend):.2f}); still lower drawdown.")

    # Chart: pure core vs pure trend vs best blend.
    plt.figure(figsize=(11, 6))
    for w, style in [(0.0, ("60/40 core only", "#ff7f0e")),
                     (1.0, ("trend sleeve only", "#2ca02c")),
                     (best_w, (f"best blend {int((1-best_w)*100)}/{int(best_w*100)}",
                               "#1f77b4"))]:
        eq = rows[w][0]
        lw = 2.0 if w == best_w else 1.2
        plt.plot(eq.index, eq.values / eq.iloc[0], label=style[0],
                 linewidth=lw, color=style[1])
    plt.title("Core vs trend vs best blend (out-of-sample, vol-matched)")
    plt.ylabel("Growth of 1")
    plt.legend()
    plt.tight_layout()
    out = "reports/combined_portfolio.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
