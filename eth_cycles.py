#!/usr/bin/env python3
"""
Ethereum cycle analysis.

ETH has NO halving, so its cycles aren't supply-driven the way Bitcoin's are.
Instead ETH broadly RIDES Bitcoin's cycle (they're ~0.7-0.9 correlated), and
its own story is largely about RELATIVE strength vs BTC (the ETH/BTC ratio),
which rises in late-cycle "alt seasons" and falls when Bitcoin dominates.

So this analyses three things, honestly:
  1. ETH's own long-run power-law trend (log price vs log age).
  2. ETH's behaviour across Bitcoin's halving cycles (it peaks alongside BTC).
  3. The ETH/BTC ratio - the key ETH-specific gauge.

Same health warning as the BTC version: tiny sample, structural changes
(the Merge, EIP-1559), curve fits that can break. Scenarios, not forecasts,
and not financial advice.

    python eth_cycles.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

GENESIS_ETH = pd.Timestamp("2015-07-30")
HALVINGS = [pd.Timestamp(d) for d in ["2016-07-09", "2020-05-11", "2024-04-20"]]


def load(sym, cache, start):
    import os
    p = f"data_cache/{cache}"
    if os.path.exists(p):
        return pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    import yfinance as yf
    raw = yf.download(sym, start=start, interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    s = pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()
    s.to_csv(p)
    return s


def power_law(s, genesis):
    age = np.array([(d - genesis).days for d in s.index], dtype=float)
    x, y = np.log10(age), np.log10(s.values)
    n, a = np.polyfit(x, y, 1)
    return a, n, float((y - (a + n * x)).std())


def cycle_stats(s):
    rows = []
    for h in HALVINGS:
        seg = s[s.index >= h]
        window = seg[seg.index <= h + pd.Timedelta(days=560)]
        if len(window) < 30 or (seg.index[0] - h).days > 30:
            continue
        p_h = float(seg.iloc[0])
        peak = float(window.max()); pd_ = window.idxmax()
        after = s[(s.index > pd_) & (s.index <= pd_ + pd.Timedelta(days=450))]
        low = float(after.min()) if len(after) else float("nan")
        rows.append(dict(halving=str(h.date()), peak=peak, peak_date=str(pd_.date()),
                         days_to_peak=(pd_ - h).days, gain_x=peak / p_h,
                         bear_dd=(low / peak - 1) * 100 if low == low else float("nan")))
    return rows


def main():
    eth = load("ETH-USD", "eth_daily.csv", "2017-11-01")
    btc = load("BTC-USD", "btc_daily.csv", "2014-09-01")
    a, n, sd = power_law(eth, GENESIS_ETH)
    price = float(eth.iloc[-1]); last = eth.index[-1]

    print("\n" + "=" * 70)
    print(f" ETHEREUM CYCLE ANALYSIS   (data {eth.index[0].date()} -> {last.date()})")
    print("=" * 70)
    print(f" Current price: ${price:,.0f}")

    def pl(days):
        return 10 ** (a + n * np.log10(days))
    age = (last - GENESIS_ETH).days
    fair = pl(age); band = 10 ** sd
    print(f" Power-law fair today: ${fair:,.0f}  (band ${fair/band:,.0f}-${fair*band:,.0f})")
    print(f" Price is {price/fair-1:+.0%} vs trend "
          f"({'above' if price > fair else 'below'}).  +1yr line ${pl(age+365):,.0f}")

    print("\n ETH across Bitcoin's halving cycles:")
    print(f"   {'halving':<12}{'ETH peak':>12}{'d->peak':>8}{'gain':>7}{'bear dd':>9}")
    for r in cycle_stats(eth):
        gx = f"{r['gain_x']:.1f}x"
        dd = f"{r['bear_dd']:.0f}%" if r['bear_dd'] == r['bear_dd'] else "n/a"
        print(f"   {r['halving']:<12}${r['peak']:>10,.0f}{r['days_to_peak']:>8}{gx:>7}{dd:>9}")

    # ETH/BTC ratio
    df = pd.concat([eth.rename("eth"), btc.rename("btc")], axis=1).dropna()
    ratio = (df["eth"] / df["btc"])
    r_now = float(ratio.iloc[-1])
    print(f"\n ETH/BTC ratio now: {r_now:.4f}   "
          f"(range {ratio.min():.4f}-{ratio.max():.4f}, "
          f"{'top' if r_now > ratio.quantile(0.66) else 'bottom' if r_now < ratio.quantile(0.33) else 'mid'} third of its history)")
    print(f"   ETH is {'OUTPERFORMING' if ratio.iloc[-1] > ratio.iloc[-180] else 'UNDERPERFORMING'} "
          f"BTC over the last ~6 months.")

    # ---- charts ----
    ages = np.array([(d - GENESIS_ETH).days for d in eth.index], dtype=float)
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.semilogy(eth.index, eth.values, color="#8b5cf6", lw=1.2, label="ETH price")
    ax.semilogy(eth.index, 10 ** (a + n * np.log10(ages)), color="#111", lw=1.4,
                ls="--", label="power-law trend")
    ax.fill_between(eth.index, 10 ** (a + n * np.log10(ages)) / band,
                    10 ** (a + n * np.log10(ages)) * band, color="#8b5cf6", alpha=0.1)
    for hd in HALVINGS:
        ax.axvline(hd, color="#ff7f0e", lw=0.8, alpha=0.6)
    ax.set_title("Ethereum vs power-law trend (log scale) - BTC halvings marked")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig("reports/eth_powerlaw.png", dpi=130); plt.close(fig)

    plt.figure(figsize=(11, 6))
    plt.plot(ratio.index, ratio.values, color="#8b5cf6", lw=1.3)
    plt.axhline(r_now, color="#d62728", ls=":", lw=1, label=f"now {r_now:.4f}")
    for hd in HALVINGS:
        plt.axvline(hd, color="#ff7f0e", lw=0.8, alpha=0.5)
    plt.title("ETH/BTC ratio (rises in alt-seasons, falls when BTC dominates)")
    plt.ylabel("ETH priced in BTC"); plt.legend(fontsize=8, frameon=False)
    plt.tight_layout(); plt.savefig("reports/eth_btc_ratio.png", dpi=130); plt.close()

    print("\n Charts: reports/eth_powerlaw.png, reports/eth_btc_ratio.png")
    print("=" * 70)
    print(" HEALTH WARNING: only ~2 full ETH cycles; the Merge (2022) changed")
    print(" ETH's economics; ratio and power-law can break. Scenarios, not")
    print(" forecasts. Not financial advice.\n")


if __name__ == "__main__":
    main()
