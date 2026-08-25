#!/usr/bin/env python3
"""
Live market-cycle gauge -> reports/cycle_gauge.json, read by the dashboard.
Recomputes on each run for a set of assets:

  * BTC / ETH / SOL - crypto, judged against a power-law trend + the shared
    Bitcoin halving cycle phase (they move together).
  * GOLD - a macro asset (no halving / power-law): distance from all-time high
    and long-term trend instead.
  * HYPE - flagged TOO NEW for cycle analysis (< 1 year of data): trend only.

Plus the ETH/BTC ratio percentile. Descriptive analogy only, tiny samples,
curve fits that can break. Not financial advice.

    python cycle_gauge.py
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

GEN = {"BTC": pd.Timestamp("2009-01-03"), "ETH": pd.Timestamp("2015-07-30"),
       "SOL": pd.Timestamp("2020-03-16")}
CRYPTO = {"BTC": ("BTC-USD", "2014-09-01"), "ETH": ("ETH-USD", "2017-11-01"),
          "SOL": ("SOL-USD", "2020-05-01")}
HALVING = pd.Timestamp("2024-04-20")
NEXT_HALVING = pd.Timestamp("2028-04-17")
# Hyperliquid: auto-graduates from "too new" to a (provisional) power-law once
# it has this much history. yfinance disambiguates it from an older HYPE ticker.
HYPE_SYM = "HYPE32196-USD"
HYPE_MIN_DAYS = 730


def fetch(sym, start):
    import yfinance as yf
    raw = yf.download(sym, start=start, interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def chg(s, ndays):
    return float(s.iloc[-1] / s.iloc[-(ndays + 1)] - 1) * 100 if len(s) > ndays else None


def power_law(s, gen):
    age = np.array([(d - gen).days for d in s.index], dtype=float)
    x, y = np.log10(age), np.log10(s.values)
    n, a = np.polyfit(x, y, 1)
    return float(a), float(n), float((y - (a + n * x)).std())


def project(a, n, sd, gen, last):
    """Forward power-law scenarios at +1yr and +2yr (base / low / high band)."""
    age = (last - gen).days
    band = 10 ** sd
    out = {}
    for yrs in (1, 2):
        base = 10 ** (a + n * np.log10(age + 365 * yrs))
        out[f"{yrs}y"] = dict(base=float(base), low=float(base / band),
                              high=float(base * band))
    return out


def proj_chart(name, s, gen, a, n, sd, color, path):
    age = np.array([(d - gen).days for d in s.index], dtype=float)
    band = 10 ** sd
    fut = np.arange(age[-1], age[-1] + 760)
    futd = [gen + pd.Timedelta(days=int(d)) for d in fut]
    trend = 10 ** (a + n * np.log10(fut))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.semilogy(s.index, s.values, color=color, lw=1.2, label=f"{name} price")
    ax.semilogy(s.index, 10 ** (a + n * np.log10(age)), color="#111", lw=1.1,
                ls="--", label="cycle-gauge trend")
    ax.semilogy(futd, trend, color="#111", lw=1.1, ls=":")
    ax.fill_between(futd, trend / band, trend * band, color=color, alpha=0.13,
                    label="scenario band (+/-1 sd)")
    ax.set_title(f"{name}: cycle-gauge scenario projection (log scale, ~2yr ahead)")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def phase(days):
    if days < 400:
        return "Pre-peak bull"
    if days < 620:
        return "Peak window"
    if days < 1000:
        return "Post-peak cooldown"
    return "Late cycle"


def bandpos(price, fair, sd):
    return float(min(max((np.log10(price) - np.log10(fair) + sd) / (2 * sd), 0), 1))


def main():
    dsl = None
    ph = None
    assets = []
    series = {}

    colors = {"BTC": "#1f77b4", "ETH": "#8b5cf6", "SOL": "#10b981"}
    for name, (sym, start) in CRYPTO.items():
        s = fetch(sym, start)
        if s is None or len(s) < 200:
            continue
        series[name] = s
        a, n, sd = power_law(s, GEN[name])
        age_now = (s.index[-1] - GEN[name]).days
        fair = 10 ** (a + n * np.log10(age_now))
        price = float(s.iloc[-1])
        if name == "BTC":
            dsl = (s.index[-1] - HALVING).days
            ph = phase(dsl)
        row = dict(
            sym=name, name={"BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana"}[name],
            kind="crypto", price=price, pct_vs_trend=(price / fair - 1) * 100,
            fair=fair, bandpos=bandpos(price, fair, sd))
        if name in ("BTC", "ETH", "SOL"):
            row["proj"] = project(a, n, sd, GEN[name], s.index[-1])
            row["proj_chart"] = f"cycle_proj_{name.lower()}.png"
            proj_chart(name, s, GEN[name], a, n, sd, colors[name],
                       f"reports/cycle_proj_{name.lower()}.png")
        assets.append(row)

    # Shared cycle phase for all crypto (they ride BTC's cycle).
    for a in assets:
        a["phase"] = ph
        a["days_since_halving"] = dsl

    # Gold (macro): distance from all-time high + long-term trend.
    g = fetch("GC=F", "2005-01-01")
    if g is not None and len(g) > 300:
        gp = float(g.iloc[-1]); ath = float(g.max())
        ma = float(g.rolling(250).mean().iloc[-1])
        assets.append(dict(sym="GOLD", name="Gold", kind="macro", price=gp,
                           pct_from_ath=(gp / ath - 1) * 100,
                           trend=("up" if gp > ma else "down"),
                           chg12m=float(gp / g.iloc[-252] - 1) * 100 if len(g) > 252 else None))

    # Hyperliquid: full power-law once it has >= HYPE_MIN_DAYS, else "too new".
    hs = fetch(HYPE_SYM, "2024-11-01")
    if hs is not None and len(hs) >= HYPE_MIN_DAYS:
        gen = hs.index[0]
        a, n, sd = power_law(hs, gen)
        age_now = (hs.index[-1] - gen).days
        fair = 10 ** (a + n * np.log10(age_now))
        price = float(hs.iloc[-1])
        proj_chart("HYPE", hs, gen, a, n, sd, "#ec4899", "reports/cycle_proj_hype.png")
        assets.append(dict(sym="HYPE", name="Hyperliquid", kind="crypto", price=price,
                           pct_vs_trend=(price / fair - 1) * 100, fair=fair,
                           bandpos=bandpos(price, fair, sd), phase=ph,
                           days_since_halving=dsl, provisional=True,
                           proj=project(a, n, sd, gen, hs.index[-1]),
                           proj_chart="cycle_proj_hype.png"))
    elif hs is not None and len(hs) >= 30:
        months = len(hs) // 30
        assets.append(dict(sym="HYPE", name="Hyperliquid", kind="too_new",
                           price=float(hs.iloc[-1]), chg30=chg(hs, 30),
                           note=f"~{months} months of data (needs ~2yr for cycle analysis)"))
    elif os.path.exists("reports/crypto_map.json"):
        cm = json.load(open("reports/crypto_map.json"))
        h = next((c for c in cm.get("coins", []) if c["coin"] == "HYPE"), None)
        if h:
            assets.append(dict(sym="HYPE", name="Hyperliquid", kind="too_new",
                               price=h["price"], chg30=h.get("chg30"),
                               note="too little history for cycle analysis"))

    # ETH/BTC ratio percentile.
    ethbtc = None
    if "ETH" in series and "BTC" in series:
        df = pd.concat([series["ETH"].rename("e"), series["BTC"].rename("b")],
                       axis=1).dropna()
        r = df["e"] / df["b"]
        rn = float(r.iloc[-1])
        ethbtc = dict(ratio=rn, percentile=float((r < rn).mean() * 100),
                      chg6m=float(rn / r.iloc[-180] - 1) * 100 if len(r) > 180 else 0.0)

    out = dict(assets=assets, ethbtc=ethbtc,
               days_since_halving=dsl, phase=ph,
               next_halving=str(NEXT_HALVING.date()),
               updated=str(series["BTC"].index[-1].date()) if "BTC" in series else "")
    os.makedirs("reports", exist_ok=True)
    json.dump(out, open("reports/cycle_gauge.json", "w"), indent=2)

    for a in assets:
        if a["kind"] == "crypto":
            print(f"{a['sym']:<5} ${a['price']:>10,.0f}  {a['pct_vs_trend']:+5.0f}% vs trend  [{a['phase']}]")
        elif a["kind"] == "macro":
            print(f"{a['sym']:<5} ${a['price']:>10,.0f}  {a['pct_from_ath']:+.0f}% from ATH, trend {a['trend']}")
        else:
            print(f"{a['sym']:<5} ${a['price']:>10,.4f}  TOO NEW ({a['note']}), 30d {a.get('chg30',0):+.0f}%")
    if ethbtc:
        print(f"ETH/BTC {ethbtc['ratio']:.4f} ({ethbtc['percentile']:.0f}th pctile), 6m {ethbtc['chg6m']:+.0f}%")


if __name__ == "__main__":
    main()
