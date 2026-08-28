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
                  "PALLADIUM": "PA=F", "BRENT OIL": "BZ=F", "WHEAT": "ZW=F",
                  "CORN": "ZC=F", "SOYBEANS": "ZS=F", "COFFEE": "KC=F",
                  "SUGAR": "SB=F", "COTTON": "CT=F", "GASOLINE": "RB=F",
                  "HEATING OIL": "HO=F"},
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


def _bootstrap_ci(hits, n_boot=2000, seed=0):
    """95% percentile-bootstrap CI on accuracy (%) from a 0/1 hit array."""
    hits = np.asarray(hits, dtype=float)
    if len(hits) < 20:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(hits), size=(n_boot, len(hits)))
    accs = hits[idx].mean(axis=1) * 100.0
    return [round(float(np.percentile(accs, 2.5))), round(float(np.percentile(accs, 97.5)))]


def _brier(pred, act, seed=0):
    """Honest Brier: calibrate P(HIGH) on half the points, score on the other half,
    so the probability is not fitted to the points it is graded on. Reports the
    Brier score, the climatology (base-rate) Brier, and the skill score
    1 - brier/base (positive = the regime signal carries information)."""
    pred = np.asarray(pred, dtype=int)
    act = np.asarray(act, dtype=float)
    cal = (np.arange(len(pred)) % 2 == 0)     # deterministic 50/50 split
    ev = ~cal
    if cal.sum() < 30 or ev.sum() < 30:
        return None
    pc, ac = pred[cal], act[cal]
    base = float(ac.mean())
    pH = float(ac[pc == 1].mean()) if (pc == 1).any() else base
    pL = float(ac[pc == 0].mean()) if (pc == 0).any() else base
    pe, ae = pred[ev], act[ev]
    p = np.where(pe == 1, pH, pL)
    brier = float(np.mean((p - ae) ** 2))
    brier_base = float(np.mean((base - ae) ** 2))
    skill = (1 - brier / brier_base) if brier_base > 0 else None
    return dict(brier=round(brier, 3), brier_base=round(brier_base, 3),
                skill=round(skill, 3) if skill is not None else None,
                n_eval=int(ev.sum()))


def main():
    live = "--live" in sys.argv
    series = {a: fetch(s) for a, s in ASSETS.items()}
    series = {a: s for a, s in series.items() if s is not None and len(s) > 500}

    agg_hits = defaultdict(int); agg_tot = defaultdict(int); agg_up = defaultdict(int)
    agg_pred = defaultdict(list); agg_act = defaultdict(list)   # for CIs + Brier
    corrs = defaultdict(list)
    live_out = {}
    ood_out = {}

    for a, s in series.items():
        live_out[a] = {}
        # Out-of-distribution flag: is today's 30-day vol outside the range the
        # backtest ever saw for this asset? If so the model is extrapolating and
        # its regime call is less trustworthy. Flag the tails of its own history.
        rv30 = realized_vol(s, 30).dropna()
        if len(rv30) > 252:
            cur = float(rv30.values[-1])
            pct = float((rv30.values < cur).mean() * 100.0)
            ood_out[a] = dict(vol_pctile=round(pct, 1),
                              out_of_range=bool(pct >= 97.5 or pct <= 2.5))
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
                    agg_pred[lbl].append(int(pred_high))
                    agg_act[lbl].append(int(act_high))
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
    # Metrics per horizon: accuracy, baseline, edge, bootstrap CI, Brier skill.
    metrics = {}
    for lbl, H in HLABEL:
        if not agg_tot[lbl]:
            continue
        acc = agg_hits[lbl] / agg_tot[lbl] * 100
        base = max(agg_up[lbl], agg_tot[lbl] - agg_up[lbl]) / agg_tot[lbl] * 100
        hits = (np.asarray(agg_pred[lbl]) == np.asarray(agg_act[lbl])).astype(int)
        metrics[lbl] = dict(acc=round(acc), base=round(base), edge=round(acc - base),
                            n=agg_tot[lbl], ci=_bootstrap_ci(hits),
                            brier=_brier(agg_pred[lbl], agg_act[lbl]),
                            r=(round(float(np.mean(corrs[lbl])), 2) if corrs[lbl] else None))

    print(f" {'horizon':<8}{'n':>6}{'accuracy':>10}{'95% CI':>12}{'edge':>7}"
          f"{'Brier skill':>13}{'vol r':>7}")
    for lbl, _ in HLABEL:
        m = metrics.get(lbl)
        if not m:
            continue
        ci = f"{m['ci'][0]}-{m['ci'][1]}%" if m['ci'] else "-"
        bs = f"{m['brier']['skill']:+.2f}" if m['brier'] and m['brier']['skill'] is not None else "-"
        rv = f"{m['r']:.2f}" if m['r'] is not None else "-"
        print(f" {lbl:<8}{m['n']:>6}{m['acc']:>9}%{ci:>12}{m['edge']:>+6}{bs:>13}{rv:>7}")

    if live:
        backtest = {lbl: dict(acc=m["acc"], edge=m["edge"], n=m["n"], ci=m["ci"],
                              brier=m["brier"]) for lbl, m in metrics.items()}
        os.makedirs("reports", exist_ok=True)
        json.dump({"assets": live_out, "backtest": backtest, "ood": ood_out,
                   "classes": {a: CLASS.get(a, "other") for a in live_out},
                   "horizons": [l for l, _ in HLABEL]},
                  open("reports/vol_regime.json", "w"), indent=2)
        print("\n Wrote reports/vol_regime.json (current regime calls + backtest).")
    print("\n Median split => baseline ~50%; accuracy above it is real skill.")
    print(" Not a forecast of price direction; predicts turbulence, not level. "
          "Educational.\n")


if __name__ == "__main__":
    main()
