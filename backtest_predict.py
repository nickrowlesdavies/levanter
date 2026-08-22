#!/usr/bin/env python3
"""
Backfill + backtest the educational prediction model across the full universe
(coins + commodities) over the last ~3 months, point-in-time (no lookahead):
at each past date the model's inputs are rebuilt from data up to that date
only, then scored against what actually happened `horizon` days later.

Non-overlapping per horizon so outcomes are independent. Results go into the
same prediction log the live model uses (source="backfill"). Small sample;
3 months is short. Not a forecast. Educational only.

    python backtest_predict.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from predict import COINS, COMMODITIES, make_prediction

GEN = {"BTC": pd.Timestamp("2009-01-03"), "ETH": pd.Timestamp("2015-07-30"),
       "SOL": pd.Timestamp("2020-03-16")}   # power-law value only for these
HALVING = pd.Timestamp("2024-04-20")
HORIZONS = [7, 30]
WINDOW_DAYS = 95
LOG = "reports/prediction_log.json"


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="max", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def phase(days):
    if days < 400:
        return "Pre-peak bull"
    if days < 620:
        return "Peak window"
    if days < 1000:
        return "Post-peak cooldown"
    return "Late cycle"


def pl_fair(s_upto, gen):
    age = np.array([(d - gen).days for d in s_upto.index], dtype=float)
    x, y = np.log10(age), np.log10(s_upto.values)
    n, a = np.polyfit(x, y, 1)
    return 10 ** (a + n * np.log10((s_upto.index[-1] - gen).days))


def ret_over(s_upto, ndays):
    past = s_upto[s_upto.index <= s_upto.index[-1] - pd.Timedelta(days=ndays)]
    return float(s_upto.iloc[-1] / past.iloc[-1] - 1) * 100 if len(past) else 0.0


def inputs_at(t, sym, s, is_c, btc, btc_ma):
    s_up = s[s.index <= t]
    if len(s_up) < 60:
        return None
    price = float(s_up.iloc[-1])
    ma50 = float(s_up.rolling(50).mean().iloc[-1])
    trend = "up" if price > ma50 else "down"
    value = ((price / pl_fair(s_up, GEN[sym]) - 1) * 100) if sym in GEN else 0.0
    if is_c:
        regime, ph = (trend == "up"), ""
    else:
        b_up = btc[btc.index <= t]
        regime = bool(b_up.iloc[-1] > btc_ma[btc_ma.index <= t].iloc[-1]) if len(b_up) else True
        ph = phase((t - HALVING).days)
    return dict(price=price, pct_vs_trend=value, phase=ph, trend=trend,
                chg7=ret_over(s_up, 7), chg30=ret_over(s_up, 30), regime=regime)


def main():
    universe = [(c, c + "-USD", False) for c in COINS] + \
               [(n, sym, True) for n, sym in COMMODITIES.items()]
    series = {}
    for name, sym, is_c in universe:
        s = fetch(sym)
        if s is not None and len(s) > 260:
            series[name] = (s, is_c)
    btc = series["BTC"][0]
    btc_ma = btc.rolling(70).mean()
    last = btc.index[-1]

    log = json.load(open(LOG)) if os.path.exists(LOG) else {"predictions": []}
    preds = log["predictions"]
    existing = {(p["date"], p["asset"], p["horizon"], p.get("source", "live"))
                for p in preds}

    added = 0
    scored = {h: [] for h in HORIZONS}
    for name, (s, is_c) in series.items():
        for h in HORIZONS:
            k = 1
            while True:
                t_target = last - pd.Timedelta(days=h + (k - 1) * h)
                if (last - t_target).days > WINDOW_DAYS:
                    break
                k += 1
                idx = s.index[s.index <= t_target]
                if len(idx) == 0:
                    continue
                t = idx[-1]
                inp = inputs_at(t, name, s, is_c, btc, btc_ma)
                if inp is None:
                    continue
                after = s[s.index >= t + pd.Timedelta(days=h)]
                if len(after) == 0:
                    continue
                price1 = float(after.iloc[0])
                prob = make_prediction(inp, h)
                predicted = "up" if prob >= 0.5 else "down"
                actual = "up" if price1 >= inp["price"] else "down"
                scored[h].append((name, is_c, actual == predicted))
                key = (str(t.date()), name, h, "backfill")
                if key in existing:
                    continue
                preds.append(dict(date=str(t.date()), asset=name, horizon=h,
                                  cls="commodity" if is_c else "crypto",
                                  price0=inp["price"], prob_up=round(prob, 3),
                                  predicted=predicted,
                                  resolve_date=str((t + pd.Timedelta(days=h)).date()),
                                  resolved=True, actual=actual, price1=price1,
                                  correct=(actual == predicted), source="backfill"))
                added += 1

    json.dump({"predictions": preds}, open(LOG, "w"), indent=2)

    def a(items):
        return sum(1 for *_, c in items if c) / len(items) * 100 if items else 0
    allc = [x for h in HORIZONS for x in scored[h]]
    print(f"\nBackfilled {added} non-overlapping predictions across "
          f"{len(series)} assets (~3 months).\n")
    for h in HORIZONS:
        print(f"  {str(h)+'d':<5} n={len(scored[h]):<4} acc {a(scored[h]):.0f}%")
    print(f"  ALL   n={len(allc):<4} acc {a(allc):.0f}%")
    cr = [x for x in allc if not x[1]]
    co = [x for x in allc if x[1]]
    print(f"    crypto   {a(cr):.0f}% ({len(cr)})   commodities {a(co):.0f}% ({len(co)})")
    print("\n Small sample. Not a forecast. Educational only.\n")


if __name__ == "__main__":
    main()
