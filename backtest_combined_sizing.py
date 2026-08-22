#!/usr/bin/env python3
"""
Combined sizing portfolio (honest test):
  * TRADITIONAL sleeve (SPX, GOLD, OIL, COPPER, SILVER) -> VOL-TARGETED
    (works there: vol spikes on crashes, so cutting size dodges declines).
  * CRYPTO sleeve (BTC, ETH, SOL) -> CYCLE-SIZED by cheapness vs its own
    power-law trend (size up below trend, down when frothy; point-in-time
    monthly refit, no lookahead). Vol-targeting hurt crypto, so we don't.

Compared, at ~equal average exposure and with costs, against:
  * plain equal-weight BUY-HOLD
  * an all-vol-targeted basket

    python backtest_combined_sizing.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from backtest_volsizing import fetch, metrics, vol_target

TRAD = {"SPX": "SPY", "GOLD": "GC=F", "OIL": "CL=F", "COPPER": "HG=F", "SILVER": "SI=F"}
CRYPTO = {"BTC": ("BTC-USD", pd.Timestamp("2009-01-03")),
          "ETH": ("ETH-USD", pd.Timestamp("2015-07-30")),
          "SOL": ("SOL-USD", pd.Timestamp("2020-03-16"))}
LEV_CAP = 2.5
COST_BPS = 5.0


def cycle_size(s, gen):
    """Point-in-time leverage from cheapness vs power-law (monthly refit)."""
    cps = []                                        # (trading_date, a, n)
    for m in s.resample("ME").last().dropna().index:
        su = s[s.index <= m]
        if len(su) < 260:
            continue
        age = np.array([(d - gen).days for d in su.index], float)
        nn, aa = np.polyfit(np.log10(age), np.log10(su.values), 1)
        cps.append((su.index[-1], aa, nn))
    if not cps:
        return pd.Series(1.0, index=s.index)
    cp = pd.DataFrame(cps, columns=["date", "a", "n"]).set_index("date")
    cp = cp[~cp.index.duplicated(keep="last")].sort_index()
    a = cp["a"].reindex(s.index, method="ffill")
    n = cp["n"].reindex(s.index, method="ffill")
    age_all = np.array([(d - gen).days for d in s.index], float)
    fair = 10 ** (a.values + n.values * np.log10(age_all))
    pv = s.values / fair - 1.0                      # >0 above trend, <0 cheap
    raw = np.clip(1.0 - pv / 0.5, 0.0, 2.0)         # cheap -> >1, frothy -> <1
    lev = pd.Series(raw, index=s.index)
    scale = lev.expanding(min_periods=120).mean()   # normalise avg ~1, point-in-time
    return (lev / scale).clip(0, LEV_CAP).fillna(1.0)


def sized_return(ret, lev):
    cost = lev.diff().abs().fillna(0) * (COST_BPS / 10000.0)
    return lev * ret - cost


def main():
    trad = {a: fetch(s) for a, s in TRAD.items()}
    trad = {a: s for a, s in trad.items() if s is not None and len(s) > 400}
    cry = {a: fetch(sym) for a, (sym, _) in CRYPTO.items()}
    cry = {a: s for a, s in cry.items() if s is not None and len(s) > 400}

    bh, allvt, comb = {}, {}, {}
    for a, s in {**trad, **cry}.items():
        ret = s.pct_change()
        bh[a] = ret
        allvt[a] = sized_return(ret, vol_target(ret))
    for a, s in trad.items():
        comb[a] = sized_return(s.pct_change(), vol_target(s.pct_change()))
    for a, s in cry.items():
        comb[a] = sized_return(s.pct_change(), cycle_size(s, CRYPTO[a][1]))

    idx = None
    for a in bh:
        di = bh[a].dropna().index
        idx = di if idx is None else idx.intersection(di)

    def basket(dct):
        return pd.concat([dct[a].reindex(idx) for a in bh], axis=1).mean(axis=1)

    strategies = {"Buy-hold (1x)": basket(bh),
                  "All vol-targeted": basket(allvt),
                  "Combined (vol-trad + cycle-crypto)": basket(comb)}

    print(f"\n COMBINED SIZING PORTFOLIO  (equal-weight {len(bh)} assets, "
          f"common {idx[0].date()} -> {idx[-1].date()}, ~equal exposure)\n")
    print(f" {'strategy':<38}{'Sharpe':>8}{'CAGR%':>7}{'vol%':>7}{'maxDD%':>8}")
    base = None
    for name, r in strategies.items():
        m = metrics(r)
        if base is None:
            base = m
        tag = ""
        if name != "Buy-hold (1x)":
            tag = f"   Sharpe {m['sharpe']-base['sharpe']:+.2f}, DD {m['dd']-base['dd']:+.0f}pt"
        print(f" {name:<38}{m['sharpe']:>8.2f}{m['cagr']:>7.0f}{m['vol']:>7.0f}"
              f"{m['dd']:>8.0f}{tag}")
    print("\n Point-in-time, costs included, average exposure ~1x per sleeve.")
    print(" Educational, not advice. Ignores borrow/financing on leverage.\n")


if __name__ == "__main__":
    main()
