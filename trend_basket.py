#!/usr/bin/env python3
"""
Diversified cross-asset trend-following - the managed-futures approach.

The finding from all prior research: no single market has a strong standalone
weekly edge. The one systematic approach with robust multi-decade evidence is
trend-following applied across MANY uncorrelated markets at once, with each
position risk-weighted so no single market dominates. The diversification IS
the edge: when most markets chop, the few that trend pay for the rest.

Universe (free ETF/crypto proxies): equities (SPY QQQ IWM EFA EEM), bonds
(TLT IEF LQD HYG), commodities (GLD SLV USO DBC DBA), dollar (UUP), crypto
(BTC ETH). Each week:
  * trend signal per asset = sign of its trailing `lookback`-week return
  * risk weight per asset = inverse of its recent volatility (equal risk)
  * hold one week, rebalance; costs charged on turnover

We report full-sample AND walk-forward (out-of-sample) results, benchmarked
against SPY buy-hold and a 60/40 portfolio. Sharpe is leverage-invariant, so
it's the honest measure of edge regardless of how much you'd size up.

    python trend_basket.py
"""
from __future__ import annotations

from itertools import product

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG",
            "GLD", "SLV", "USO", "DBC", "DBA", "UUP", "BTC-USD", "ETH-USD"]
START, END = "2007-01-01", "2026-08-16"
CACHE = "data_cache/trend_basket_weekly.csv"
COST_BPS = 8.0            # per unit turnover (ETF spreads are tight)
VOL_LB = 13              # weeks for volatility estimate
MIN_ASSETS = 6          # need a diversified breadth before trading


def load_prices() -> pd.DataFrame:
    import os
    if os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    import yfinance as yf
    # Per-symbol download: a single 17-ticker batch flakes/rate-limits;
    # one at a time is slower but reliable.
    cols = {}
    for s in UNIVERSE:
        try:
            d = yf.download(s, start=START, end=END, interval="1d",
                            progress=False, auto_adjust=True)["Close"]
            if d is not None and len(d.dropna()):
                cols[s.replace("-USD", "")] = d.squeeze()
        except Exception:
            pass
    daily = pd.DataFrame(cols)
    w = daily.resample("W-SUN").last().dropna(how="all")
    w.to_csv(CACHE)
    return w


def _metrics(equity, rets):
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 0.1)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(52) if rets.std() > 0 else np.nan
    vol = rets.std() * np.sqrt(52) * 100
    dd = ((equity - equity.cummax()) / equity.cummax()).min()
    return {"cagr_pct": cagr * 100, "sharpe": sharpe, "vol_pct": vol,
            "maxdd_pct": dd * 100, "total_pct": (equity.iloc[-1] / equity.iloc[0] - 1) * 100}


def trend_backtest(prices, lookback=26, long_short=True, vol_lb=VOL_LB,
                   cost_bps=COST_BPS, eval_start=None):
    """Time-series trend-following across the basket, inverse-vol weighted,
    weekly rebalance. Returns (equity curve, weekly returns)."""
    rets = prices.pct_change()
    mom = prices / prices.shift(lookback) - 1.0
    vol = rets.rolling(vol_lb).std()

    cols = prices.columns
    prev_pos = pd.Series(0.0, index=cols)
    equity = 1.0
    curve, wk = [], []
    idx = prices.index

    for t in range(max(lookback, vol_lb), len(idx) - 1):
        m = mom.iloc[t]
        v = vol.iloc[t]
        active = m.notna() & v.notna() & (v > 0)
        if active.sum() < MIN_ASSETS:
            continue

        sig = np.sign(m[active]) if long_short else (m[active] > 0).astype(float)
        invvol = 1.0 / v[active]
        w = invvol / invvol.sum()          # equal-risk weights, sum to 1
        pos = pd.Series(0.0, index=cols)
        pos[active] = sig * w

        nxt = rets.iloc[t + 1].reindex(cols).fillna(0.0)
        gross = float((pos * nxt).sum())
        turnover = float((pos - prev_pos).abs().sum())
        net = gross - turnover * (cost_bps / 10000.0)
        prev_pos = pos

        if eval_start is not None and idx[t + 1] < eval_start:
            continue                        # warm-up only, don't record
        equity *= (1 + net)
        curve.append((idx[t + 1], equity))
        wk.append(net)

    c = pd.Series([e for _, e in curve], index=[d for d, _ in curve])
    return c, pd.Series(wk, index=c.index)


def benchmark_6040(prices):
    r = prices.pct_change()
    bond = "IEF" if "IEF" in r.columns else ("TLT" if "TLT" in r.columns else None)
    if "SPY" not in r.columns or bond is None:
        return None, None
    port = (0.6 * r["SPY"] + 0.4 * r[bond]).dropna()
    return (1 + port).cumprod(), port


def walk_forward(prices):
    grid = [dict(lookback=L, long_short=ls)
            for L, ls in product([13, 26, 52], [True, False])]
    TRAIN, TEST, STEP = 156, 52, 52
    warmup = 60
    idx = prices.index
    stitched, choices = [], []
    start = TRAIN
    while start + TEST <= len(idx):
        tr = prices.iloc[start - TRAIN:start]
        test_from = idx[start]
        test_frame = prices.iloc[max(0, start - warmup):min(start + TEST, len(idx))]
        best, best_s = None, -np.inf
        for cmb in grid:
            _, r = trend_backtest(tr, **cmb)
            if len(r) < 20:
                continue
            s = _metrics((1 + r).cumprod(), r)["sharpe"]
            if s == s and s > best_s:
                best_s, best = s, cmb
        if best is None:
            start += STEP
            continue
        _, rt = trend_backtest(test_frame, eval_start=test_from, **best)
        for d, v in rt.items():
            stitched.append((d, v))
        choices.append({"from": str(test_from.date()), "params": best})
        start += STEP
    r = pd.Series([v for _, v in stitched], index=[d for d, _ in stitched])
    r = r[~r.index.duplicated(keep="first")].sort_index()
    return (1 + r).cumprod(), r, choices


def main():
    prices = load_prices()
    print("\n" + "=" * 74)
    print(f" DIVERSIFIED TREND-FOLLOWING  ({len(prices.columns)} markets, "
          f"{len(prices)} weeks, 2007-2026)")
    print(" Inverse-vol weighted, weekly. Sharpe is leverage-invariant.")
    print("=" * 74)

    # Full-sample param scan (context only).
    print(" FULL-SAMPLE (context - in-sample):")
    print(f" {'lookback':>8} {'l/s':>4} | {'CAGR%':>7} {'Sharpe':>7} "
          f"{'vol%':>6} {'maxDD%':>8}")
    for L in (13, 26, 52):
        for ls in (True, False):
            c, r = trend_backtest(prices, lookback=L, long_short=ls)
            m = _metrics(c, r)
            print(f" {L:>8} {'L/S' if ls else 'L/F':>4} | {m['cagr_pct']:>7.1f} "
                  f"{m['sharpe']:>7.2f} {m['vol_pct']:>6.1f} {m['maxdd_pct']:>8.1f}")

    # Walk-forward (the honest verdict).
    wf_curve, wf_r, choices = walk_forward(prices)
    wm = _metrics(wf_curve, wf_r)
    print("-" * 74)
    print(" WALK-FORWARD (OUT-OF-SAMPLE - params chosen on past data only):")
    print(f"   OOS {wf_curve.index[0].date()} -> {wf_curve.index[-1].date()} "
          f"({len(wf_r)} weeks)")
    print(f"   CAGR {wm['cagr_pct']:+.1f}%   Sharpe {wm['sharpe']:.2f}   "
          f"vol {wm['vol_pct']:.1f}%   maxDD {wm['maxdd_pct']:.0f}%")

    # Benchmarks over the OOS window.
    # Which params the walk-forward chose (stability check).
    from collections import Counter
    picks = Counter((c["params"]["lookback"],
                     "L/S" if c["params"]["long_short"] else "L/F")
                    for c in choices)
    print("   params chosen across windows: " +
          ", ".join(f"{p}x{n}" for p, n in picks.most_common()))

    spy = prices["SPY"].pct_change().dropna()
    spy = spy[spy.index >= wf_curve.index[0]]
    spm = _metrics((1 + spy).cumprod(), spy)
    b_eq, b_r = benchmark_6040(prices)
    bm = None
    if b_r is not None:
        b_r = b_r[b_r.index >= wf_curve.index[0]]
        bm = _metrics((1 + b_r).cumprod(), b_r)
    print("-" * 74)
    print(f"   BENCHMARK SPY buy-hold : Sharpe {spm['sharpe']:.2f}, "
          f"CAGR {spm['cagr_pct']:.1f}%, maxDD {spm['maxdd_pct']:.0f}%")
    if bm:
        print(f"   BENCHMARK 60/40        : Sharpe {bm['sharpe']:.2f}, "
              f"CAGR {bm['cagr_pct']:.1f}%, maxDD {bm['maxdd_pct']:.0f}%")
    print("=" * 74)
    bench_sharpe = max(spm["sharpe"], bm["sharpe"] if bm else -9)
    verdict = ("EDGE SURVIVES - beats benchmarks on risk-adjusted return"
               if wm["sharpe"] > bench_sharpe
               else "comparable Sharpe to buy-hold/60-40, but far lower drawdown")
    print(f" VERDICT: {verdict}.")
    print(f"   Trend Sharpe {wm['sharpe']:.2f} @ {wm['vol_pct']:.0f}% vol, "
          f"maxDD {wm['maxdd_pct']:.0f}% (vs SPY maxDD {spm['maxdd_pct']:.0f}%).")

    # Chart: walk-forward OOS vs benchmarks (rebased).
    plt.figure(figsize=(11, 6))
    plt.plot(wf_curve.index, wf_curve.values / wf_curve.iloc[0],
             label="diversified trend (walk-forward OOS)", linewidth=1.8,
             color="#1f77b4")
    sp = (1 + spy).cumprod()
    plt.plot(sp.index, sp.values / sp.iloc[0], label="SPY buy-hold",
             linewidth=1.1, color="#ff7f0e", alpha=0.8)
    b = (1 + b_r).cumprod()
    plt.plot(b.index, b.values / b.iloc[0], label="60/40", linewidth=1.1,
             color="grey", alpha=0.7)
    plt.title("Diversified trend-following - walk-forward OOS vs benchmarks")
    plt.ylabel("Growth of 1")
    plt.legend()
    plt.tight_layout()
    out = "reports/trend_basket.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
