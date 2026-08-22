#!/usr/bin/env python3
"""
Walk-forward validation of the crypto weekly momentum + regime strategy.

The full-sample results (Sharpe ~1.2, drawdown -60%) were tuned with
hindsight. This is the honest gate: on each step, choose parameters
(lookback, basket size, regime MA) using ONLY past weeks, then trade the
next unseen year with those fixed choices. Stitch the unseen slices
together. If the edge survives, it's real; if it collapses, we found out
before risking a cent.

    python crypto_walkforward.py
"""
from __future__ import annotations

from itertools import product

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from crypto_momentum import load_prices, momentum_backtest, _metrics, benchmark

TRAIN_WEEKS, TEST_WEEKS, STEP_WEEKS = 156, 52, 52   # ~3y train, 1y test, roll 1y

# Parameter grid the walk-forward may choose from each window.
# regime_ma=0 means "no filter" - so the WF decides whether the filter helps.
GRID = {
    "lookback": [4, 8, 12],
    "k": [3, 5],
    "regime_ma": [0, 10, 15, 20],
}


def combos():
    keys = list(GRID)
    return [dict(zip(keys, v)) for v in product(*[GRID[k] for k in keys])]


def main():
    prices = load_prices()
    idx = prices.index
    all_combos = combos()

    equity = 1.0
    stitched, choices = [], []
    warmup = 40  # weeks of prior data each test window may warm up on

    start = TRAIN_WEEKS
    while start + TEST_WEEKS <= len(idx):
        tr = prices.iloc[start - TRAIN_WEEKS:start]
        test_start_date = idx[start]
        test_end = min(start + TEST_WEEKS, len(idx))
        # Test frame includes warmup weeks before the test window.
        test_frame = prices.iloc[max(0, start - warmup):test_end]

        # --- choose params on TRAIN only (by Sharpe) ---
        best, best_sharpe = None, -np.inf
        for cmb in all_combos:
            _, r = momentum_backtest(tr, **cmb)
            if len(r) < 20:
                continue
            m = _metrics((1 + r).cumprod(), r)
            if m["sharpe"] == m["sharpe"] and m["sharpe"] > best_sharpe:
                best_sharpe, best = m["sharpe"], cmb
        if best is None:
            start += STEP_WEEKS
            continue

        # --- trade the unseen test window with the chosen params ---
        _, rtest = momentum_backtest(test_frame, eval_start=test_start_date, **best)
        for d, v in rtest.items():
            stitched.append((d, v))
        choices.append({"test_from": str(test_start_date.date()),
                        "params": best, "weeks": len(rtest)})
        start += STEP_WEEKS

    if not stitched:
        print("Not enough data for walk-forward.")
        return

    r = pd.Series([v for _, v in stitched], index=[d for d, _ in stitched])
    r = r[~r.index.duplicated(keep="first")].sort_index()
    curve = (1 + r).cumprod()
    m = _metrics(curve, r)

    print("\n" + "=" * 72)
    print(" CRYPTO MOMENTUM - WALK-FORWARD (OUT-OF-SAMPLE) VALIDATION")
    print(" Params chosen on past data only, tested on unseen years, stitched.")
    print("=" * 72)
    print(f" OOS period : {curve.index[0].date()} -> {curve.index[-1].date()} "
          f"({len(r)} weeks)")
    print(f" Total ret  : {m['total_pct']:+.0f}%     CAGR {m['cagr_pct']:+.1f}%")
    print(f" Sharpe     : {m['sharpe']:.2f}")
    print(f" Max DD     : {m['maxdd_pct']:.0f}%")
    print("-" * 72)
    print(" Params chosen per window:")
    for ch in choices:
        p = ch["params"]
        print(f"   from {ch['test_from']}: lookback={p['lookback']}, k={p['k']}, "
              f"regime_ma={p['regime_ma']}  ({ch['weeks']} wks)")

    # Benchmark over the same OOS window.
    btc_eq, btc_r = benchmark(prices, equal_weight=False)
    btc_r = btc_r[btc_r.index >= curve.index[0]]
    bm = _metrics((1 + btc_r).cumprod(), btc_r)
    print("-" * 72)
    print(f" BTC buy-hold (same window): Sharpe {bm['sharpe']:.2f}, "
          f"CAGR {bm['cagr_pct']:.0f}%, maxDD {bm['maxdd_pct']:.0f}%")
    print("=" * 72)
    verdict = ("EDGE SURVIVES walk-forward" if m["sharpe"] > bm["sharpe"]
               else "edge does NOT clearly beat buy-hold OOS")
    print(f" VERDICT: {verdict} (OOS Sharpe {m['sharpe']:.2f} vs "
          f"BTC {bm['sharpe']:.2f}).")

    plt.figure(figsize=(11, 6))
    plt.plot(curve.index, curve.values, label="crypto momentum (walk-forward OOS)",
             linewidth=1.8, color="#d62728")
    bc = (1 + btc_r).cumprod()
    plt.plot(bc.index, bc.values, label="BTC buy-hold (same window)",
             linewidth=1.1, color="#ff7f0e", alpha=0.8)
    plt.yscale("log")
    plt.title("Crypto momentum - walk-forward out-of-sample (log scale)")
    plt.ylabel("Growth of 1 (log)")
    plt.legend()
    plt.tight_layout()
    out = "reports/crypto_walkforward.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
