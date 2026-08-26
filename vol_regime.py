#!/usr/bin/env python3
"""
Volatility-REGIME predictor + 5-year backtest across horizons 7/30/60/90d,
6mo, 12mo. Unlike direction, volatility CLUSTERS (calm follows calm, storm
follows storm), so this should genuinely beat a coin flip.

Target (point-in-time, no lookahead): will realized volatility over the NEXT H
days be HIGH (above the asset's running median vol) or LOW (below)? The median
split makes the naive baseline exactly ~50%, so accuracy above 50% is real
skill. Predictor: persistence - if current trailing vol is above the running
median, predict HIGH; else LOW.

Also reports the correlation between current and forward vol (how strongly vol
persists) per horizon - expect it to fade at longer horizons as vol mean-reverts.

    python vol_regime.py            # backtest
    python vol_regime.py --live     # also write reports/vol_regime.json (current calls)
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

# Universe grouped by asset class so each dashboard tab can show its own
# volatility-regime panel. The predictor itself is class-agnostic.
UNIVERSE = {
    "crypto": {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"},
    "commodity": {"GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F",
                  "COPPER": "HG=F", "NAT GAS": "NG=F", "PLATINUM": "PL=F",
                  "SOYBEANS": "ZS=F", "COFFEE": "KC=F", "SUGAR": "SB=F",
                  "COTTON": "CT=F", "GASOLINE": "RB=F", "HEATING OIL": "HO=F"},
    "fx": {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
           "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X", "USDCAD": "USDCAD=X",
           "NZDUSD": "NZDUSD=X"},
    "equity": {"SPX": "SPY"},
}
ASSETS = {a: s for d in UNIVERSE.values() for a, s in d.items()}
CLASS = {a: cls for cls, d in UNIVERSE.items() for a in d}
HLABEL = [("7d", 7), ("30d", 30), ("60d", 60), ("90d", 90),
          ("6mo", 180), ("12mo", 365)]
YEARS = 5


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="max", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def realized_vol(s, H):
    r = np.log(s / s.shift(1))
    return r.rolling(H).std() * np.sqrt(252)   # trailing annualised vol


def main():
    live = "--live" in sys.argv
    series = {a: fetch(s) for a, s in ASSETS.items()}
    series = {a: s for a, s in series.items() if s is not None and len(s) > 500}

    agg_hits = defaultdict(int); agg_tot = defaultdict(int); agg_up = defaultdict(int)
    corrs = defaultdict(list)
    live_out = {}

    for a, s in series.items():
        live_out[a] = {}
        for lbl, H in HLABEL:
            RV = realized_vol(s, H)
            thr = RV.expanding(min_periods=252).median()
            rv, th = RV.values, thr.values
            n = len(s)
            window = YEARS * 365
            cutoff = s.index[-1] - pd.Timedelta(days=window)
            # non-overlapping backtest points, stepping by H
            i = n - 1 - H
            xs, ys = [], []
            while i - H >= 0 and s.index[i] >= cutoff:
                if not (np.isnan(rv[i]) or np.isnan(th[i]) or np.isnan(rv[i + H])):
                    pred_high = rv[i] > th[i]
                    act_high = rv[i + H] > th[i]
                    agg_hits[lbl] += (pred_high == act_high)
                    agg_tot[lbl] += 1
                    agg_up[lbl] += act_high
                    xs.append(rv[i]); ys.append(rv[i + H])
                i -= H
            if len(xs) > 5:
                corrs[lbl].append(np.corrcoef(xs, ys)[0, 1])
            # live call for this asset+horizon
            if not np.isnan(rv[-1]) and not np.isnan(th[-1]):
                live_out[a][lbl] = dict(
                    regime="HIGH" if rv[-1] > th[-1] else "LOW",
                    vol_now=round(float(rv[-1]) * 100, 1),
                    vol_median=round(float(th[-1]) * 100, 1))

    print(f"\n VOLATILITY-REGIME MODEL - {YEARS}-YEAR BACKTEST "
          f"({len(series)} assets, non-overlapping, point-in-time)\n")
    print(f" {'horizon':<8}{'n':>6}{'accuracy':>10}{'baseline':>10}{'edge':>7}{'vol persist r':>15}")
    for lbl, H in HLABEL:
        if not agg_tot[lbl]:
            continue
        acc = agg_hits[lbl] / agg_tot[lbl] * 100
        base = max(agg_up[lbl], agg_tot[lbl] - agg_up[lbl]) / agg_tot[lbl] * 100
        r = np.mean(corrs[lbl]) if corrs[lbl] else float("nan")
        print(f" {lbl:<8}{agg_tot[lbl]:>6}{acc:>9.0f}%{base:>9.0f}%{acc-base:>+6.0f}{r:>14.2f}")

    if live:
        backtest = {}
        for lbl, H in HLABEL:
            if agg_tot[lbl]:
                acc = agg_hits[lbl] / agg_tot[lbl] * 100
                base = max(agg_up[lbl], agg_tot[lbl] - agg_up[lbl]) / agg_tot[lbl] * 100
                backtest[lbl] = dict(acc=round(acc), edge=round(acc - base), n=agg_tot[lbl])
        os.makedirs("reports", exist_ok=True)
        json.dump({"assets": live_out, "backtest": backtest,
                   "classes": {a: CLASS.get(a, "other") for a in live_out},
                   "horizons": [l for l, _ in HLABEL]},
                  open("reports/vol_regime.json", "w"), indent=2)
        print("\n Wrote reports/vol_regime.json (current regime calls + backtest).")
    print("\n Median split => baseline ~50%; accuracy above it is real skill.")
    print(" Not a forecast of price direction; predicts turbulence, not level. "
          "Educational.\n")


if __name__ == "__main__":
    main()
