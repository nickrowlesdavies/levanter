#!/usr/bin/env python3
"""
Longer, honest backtest of the model's COMMODITY edge (~5 years, point-in-time,
non-overlapping). The 3-month read was 62% on a small sample; this checks
whether it holds up - AND whether it beats the naive baseline.

Key honesty control: commodities trend up, so "always predict UP" is already a
high baseline. The model only has real SKILL if it beats max(up-rate, down-rate).
We report model accuracy, the naive baseline, and the edge over it, per horizon,
per commodity, and per year.

    python backtest_commodities.py
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from predict import make_prediction
from backtest_predict import inputs_at   # point-in-time input builder

COMMODITIES = {"GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F", "COPPER": "HG=F",
               "PLAT": "PL=F", "NATGAS": "NG=F", "BROAD": "DBC", "AGRI": "DBA"}
HORIZONS = [7, 30]
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


def main():
    series = {n: fetch(s) for n, s in COMMODITIES.items()}
    series = {n: s for n, s in series.items() if s is not None and len(s) > 400}
    last = max(s.index[-1] for s in series.values())
    window = YEARS * 365

    hits = defaultdict(int); tot = defaultdict(int)
    ups = defaultdict(int)                    # actual up-moves (for baseline)
    by_asset = defaultdict(lambda: [0, 0])
    by_year = defaultdict(lambda: [0, 0])

    for name, s in series.items():
        for h in HORIZONS:
            k = 1
            while True:
                t_target = last - pd.Timedelta(days=h + (k - 1) * h)
                if (last - t_target).days > window:
                    break
                k += 1
                idx = s.index[s.index <= t_target]
                if len(idx) == 0:
                    continue
                t = idx[-1]
                inp = inputs_at(t, name, s, True, None, None)
                if inp is None:
                    continue
                after = s[s.index >= t + pd.Timedelta(days=h)]
                if len(after) == 0:
                    continue
                actual = "up" if float(after.iloc[0]) >= inp["price"] else "down"
                pred = "up" if make_prediction(inp, h) >= 0.5 else "down"
                ok = pred == actual
                hits[h] += ok; tot[h] += 1
                ups[h] += (actual == "up")
                by_asset[name][0] += ok; by_asset[name][1] += 1
                by_year[t.year][0] += ok; by_year[t.year][1] += 1

    print(f"\n COMMODITY MODEL - {YEARS}-YEAR BACKTEST "
          f"({len(series)} markets, non-overlapping, point-in-time)\n")
    print(f" {'horizon':<8}{'n':>6}{'model':>8}{'always-up':>11}{'edge':>7}")
    TH = TN = 0
    for h in HORIZONS:
        if not tot[h]:
            continue
        acc = hits[h] / tot[h] * 100
        base = max(ups[h], tot[h] - ups[h]) / tot[h] * 100   # naive majority class
        print(f" {str(h)+'d':<8}{tot[h]:>6}{acc:>7.0f}%{base:>10.0f}%{acc-base:>+6.0f}")
        TH += hits[h]; TN += tot[h]
    tot_up = sum(ups.values()); tot_all = sum(tot.values())
    base_all = max(tot_up, tot_all - tot_up) / tot_all * 100
    print(f" {'ALL':<8}{TN:>6}{TH/TN*100:>7.0f}%{base_all:>10.0f}%{TH/TN*100-base_all:>+6.0f}")

    print("\n Per commodity (model accuracy):")
    for a in sorted(by_asset, key=lambda x: -by_asset[x][0] / max(by_asset[x][1], 1)):
        ok, tt = by_asset[a]
        print(f"   {a:<8}{ok/tt*100:>4.0f}%  ({tt})")
    print("\n Per year (model accuracy):")
    for y in sorted(by_year):
        ok, tt = by_year[y]
        print(f"   {y}: {ok/tt*100:>4.0f}%  ({tt})")
    print("\n Verdict: the model has SKILL only if 'edge' over always-up is "
          "clearly positive.\n Small-ish sample, futures roll effects ignored. "
          "Not a forecast. Educational.\n")


if __name__ == "__main__":
    main()
