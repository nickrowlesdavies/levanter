#!/usr/bin/env python3
"""
Bitcoin cycle analysis.

Bitcoin has two structural features worth analysing honestly:
  1. The ~4-year HALVING cycle (supply issuance halves every ~210k blocks:
     2012, 2016, 2020, 2024), historically followed by a bull run into a
     peak ~12-18 months later, then a deep bear.
  2. A long-run POWER-LAW trend: log(price) has tracked log(age) fairly well
     over Bitcoin's life, giving a rising log-log channel.

This script characterises past cycles and projects SCENARIO ranges. Read the
health warning: there are only ~3 completed cycles, each weaker than the last
(diminishing returns), and any regime (regulation, macro, adoption) can break
the pattern. This is descriptive analogy, NOT a reliable forecast.

    python btc_cycles.py
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

GENESIS = pd.Timestamp("2009-01-03")
HALVINGS = [pd.Timestamp(d) for d in
            ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]]
CACHE = "data_cache/btc_daily.csv"


def load_btc() -> pd.Series:
    import os
    if os.path.exists(CACHE):
        s = pd.read_csv(CACHE, index_col=0, parse_dates=True).iloc[:, 0]
        return s.dropna()
    import yfinance as yf
    raw = yf.download("BTC-USD", start="2014-09-01", interval="1d",
                      progress=False, auto_adjust=True)["Close"]
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    s = pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()
    s.name = "BTC"
    s.to_csv(CACHE)
    return s


def power_law(s: pd.Series):
    """Fit log10(price) = a + n*log10(age_days). Return fit + residual std."""
    age = np.array([(d - GENESIS).days for d in s.index], dtype=float)
    x, y = np.log10(age), np.log10(s.values)
    n, a = np.polyfit(x, y, 1)
    resid = y - (a + n * x)
    return a, n, float(resid.std())


def cycle_stats(s: pd.Series):
    """For each halving: price at halving, subsequent peak + timing + gain,
    then the following bear low + drawdown."""
    rows = []
    for h in HALVINGS:
        seg = s[(s.index >= h)]
        if len(seg) < 30:
            continue
        p_h = float(seg.iloc[0])
        window = seg[seg.index <= h + pd.Timedelta(days=560)]
        if len(window) < 30 or (seg.index[0] - h).days > 30:
            continue          # data doesn't cover this halving's window (e.g. 2012)
        peak = float(window.max())
        peak_date = window.idxmax()
        days_to_peak = (peak_date - h).days
        # bear low after the peak
        after = s[(s.index > peak_date) & (s.index <= peak_date + pd.Timedelta(days=450))]
        low = float(after.min()) if len(after) else float("nan")
        dd = (low / peak - 1) * 100 if low == low else float("nan")
        rows.append(dict(halving=str(h.date()), price_at_halving=p_h, peak=peak,
                         peak_date=str(peak_date.date()), days_to_peak=days_to_peak,
                         gain_x=peak / p_h, bear_low=low, bear_dd_pct=dd))
    return rows


def main():
    s = load_btc()
    a, n, sd = power_law(s)
    last_price = float(s.iloc[-1])
    last_date = s.index[-1]
    print("\n" + "=" * 70)
    print(f" BITCOIN CYCLE ANALYSIS   (data {s.index[0].date()} -> {last_date.date()})")
    print("=" * 70)
    print(f" Current price: ${last_price:,.0f}")
    print(f" Power-law fit: log10(price) = {a:.2f} + {n:.2f}*log10(age)  "
          f"(residual sd {sd:.2f} in log10)")

    # Where the power-law model sits today, and a 1-year-ahead band.
    def pl(days):
        return 10 ** (a + n * np.log10(days))
    age_now = (last_date - GENESIS).days
    fair_now = pl(age_now)
    fair_1y = pl(age_now + 365)
    band = 10 ** sd
    print(f" Model 'fair' today: ${fair_now:,.0f}  "
          f"(band ${fair_now/band:,.0f} - ${fair_now*band:,.0f})")
    print(f" Price is {last_price/fair_now-1:+.0%} vs the power-law line "
          f"({'above' if last_price>fair_now else 'below'} trend).")
    print(f" Model line +1yr: ${fair_1y:,.0f}  "
          f"(band ${fair_1y/band:,.0f} - ${fair_1y*band:,.0f})")

    print("\n Completed halving cycles:")
    print(f"   {'halving':<12}{'peak':>12}{'d->peak':>8}{'gain':>7}{'bear dd':>9}")
    stats = cycle_stats(s)
    for r in stats:
        gx = f"{r['gain_x']:.1f}x"
        dd = f"{r['bear_dd_pct']:.0f}%" if r['bear_dd_pct'] == r['bear_dd_pct'] else "n/a"
        print(f"   {r['halving']:<12}${r['peak']:>10,.0f}{r['days_to_peak']:>8}"
              f"{gx:>7}{dd:>9}")

    # Where we are in the current (2024) cycle.
    h = HALVINGS[-1]
    dsl = (last_date - h).days
    prior_peaks = [r["days_to_peak"] for r in stats if r["halving"] < "2024"]
    avg_peak_day = int(np.mean(prior_peaks)) if prior_peaks else 520
    print(f"\n Current cycle: {dsl} days since the {h.date()} halving.")
    print(f"   Prior cycles peaked ~{avg_peak_day} days post-halving "
          f"({', '.join(str(p) for p in prior_peaks)} days).")

    # ---- Charts ----
    # 1) Power-law channel (log-log).
    age = np.array([(d - GENESIS).days for d in s.index], dtype=float)
    fut_days = np.arange(age[-1], age[-1] + 730)
    fut_dates = [GENESIS + pd.Timedelta(days=int(d)) for d in fut_days]
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.semilogy(s.index, s.values, color="#1f77b4", lw=1.2, label="BTC price")
    ax.semilogy(s.index, 10 ** (a + n * np.log10(age)), color="#111", lw=1.4,
                ls="--", label="power-law trend")
    for k, al in [(band, 0.5), (band ** 2, 0.25)]:
        ax.fill_between(s.index, 10 ** (a + n * np.log10(age)) / k,
                        10 ** (a + n * np.log10(age)) * k, color="#1f77b4", alpha=0.08)
    ax.semilogy(fut_dates, pl(fut_days), color="#111", lw=1.2, ls=":")
    for hd in HALVINGS:
        ax.axvline(hd, color="#ff7f0e", lw=0.8, alpha=0.6)
    ax.set_title("Bitcoin vs power-law trend (log scale) - halvings marked")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig("reports/btc_powerlaw.png", dpi=130); plt.close(fig)

    # 2) Halving-cycle overlay (price indexed to halving day = 100).
    plt.figure(figsize=(11, 6))
    for hd in HALVINGS:
        seg = s[(s.index >= hd) & (s.index <= hd + pd.Timedelta(days=1000))]
        if len(seg) < 30:
            continue
        days = [(d - hd).days for d in seg.index]
        norm = seg.values / seg.values[0] * 100
        lbl = f"{hd.year} halving" + (" (current)" if hd == HALVINGS[-1] else "")
        plt.plot(days, norm, lw=1.8 if hd == HALVINGS[-1] else 1.2, label=lbl)
    plt.axhline(100, color="#999", ls="--", lw=0.8)
    plt.axvline(avg_peak_day, color="#d62728", ls=":", lw=1, label=f"avg prior peak ~{avg_peak_day}d")
    plt.yscale("log")
    plt.xlabel("days since halving"); plt.ylabel("price indexed to halving = 100 (log)")
    plt.title("Bitcoin halving-cycle overlay (each cycle from its halving day)")
    plt.legend(fontsize=8, frameon=False)
    plt.tight_layout(); plt.savefig("reports/btc_halving_overlay.png", dpi=130); plt.close()

    print("\n Charts saved: reports/btc_powerlaw.png, reports/btc_halving_overlay.png")
    print("=" * 70)
    print(" HEALTH WARNING: ~3 cycles = tiny sample; each cycle's gains have")
    print(" shrunk; power-law is a curve fit that can break. Scenarios, not")
    print(" forecasts. Not financial advice.\n")


if __name__ == "__main__":
    main()
