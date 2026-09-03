#!/usr/bin/env python3
"""
Fill the gaps in the LIVE prediction window, point-in-time.

predict.py only logged calls on the days it actually ran: 8 of the 13 calendar
days since the live start on 22 Aug 2026. The old scheduled task never invoked
it, so the missing days have no logged call at all. This rebuilds what the
model WOULD have said on those days from data available up to that date only
(no lookahead), and writes them with source="reconstructed" so they are never
confused with calls that were actually published live.

Two horizons behave differently and it matters:
  * h=7  uses only chg7 / trend / regime / chg30, all of which are exactly
         reproducible from the price series. Reconstruction is exact.
  * h=30 also uses pct_vs_trend and cycle phase. Live reads those from
         cycle_gauge.json (a snapshot); here they are rebuilt point-in-time
         from the power-law fit and the halving date. Over this window both
         bases give the same phase ("Post-peak cooldown") and cover the same
         three assets (BTC/ETH/SOL), so the two agree closely but not to the
         digit. No h=30 call has matured yet, so nothing published depends on
         it today. Flagged per row as feat_basis.

Also self-validates: it recomputes the days that DID run and reports how often
the reconstruction reproduces the call that was logged live.

    python reconstruct_live.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

from predict import COINS, COMMODITIES, PAIRS, HORIZONS, LOG, make_prediction

GEN = {"BTC": pd.Timestamp("2009-01-03"), "ETH": pd.Timestamp("2015-07-30"),
       "SOL": pd.Timestamp("2020-03-16")}
HALVING = pd.Timestamp("2024-04-20")


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="max", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    s = pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()
    return s[s.index < pd.Timestamp(date.today())]   # settled closes only


def phase_at(t):
    days = (t - HALVING).days
    if days < 400:
        return "Pre-peak bull"
    if days < 620:
        return "Peak window"
    if days < 1000:
        return "Post-peak cooldown"
    return "Late cycle"


def pl_fair(s_upto, gen):
    age = np.array([(d - gen).days for d in s_upto.index], dtype=float)
    ok = age > 0
    x, y = np.log10(age[ok]), np.log10(s_upto.values[ok])
    n, a = np.polyfit(x, y, 1)
    return 10 ** (a + n * np.log10((s_upto.index[-1] - gen).days))


def ret_over(s_upto, ndays):
    past = s_upto[s_upto.index <= s_upto.index[-1] - pd.Timedelta(days=ndays)]
    return float(s_upto.iloc[-1] / past.iloc[-1] - 1) * 100 if len(past) else 0.0


def inputs_at(t, sym, s, cls, btc, btc_ma):
    """Mirror of predict.build_inputs, but using data up to t only."""
    s_up = s[s.index <= t]
    if len(s_up) < 60:
        return None
    price = float(s_up.iloc[-1])
    ma50 = float(s_up.rolling(50).mean().iloc[-1])
    trend = "up" if price > ma50 else "down"
    if cls == "crypto":
        b_up, bm_up = btc[btc.index <= t], btc_ma[btc_ma.index <= t]
        if len(b_up) == 0 or len(bm_up) == 0 or pd.isna(bm_up.iloc[-1]):
            return None
        regime = bool(b_up.iloc[-1] > bm_up.iloc[-1])
        ph = phase_at(t)
        value = ((price / pl_fair(s_up, GEN[sym]) - 1) * 100) if sym in GEN else 0.0
    else:
        regime, ph, value = (trend == "up"), "", 0.0
    return dict(price=price, pct_vs_trend=value, phase=ph, chg7=ret_over(s_up, 7),
                chg30=ret_over(s_up, 30), trend=trend, regime=regime)


def main():
    dry = "--dry-run" in sys.argv
    log = json.load(open(LOG)) if os.path.exists(LOG) else {"predictions": []}
    preds = log["predictions"]

    live_dates = sorted({p["date"] for p in preds if p.get("source") == "live"})
    if not live_dates:
        print("reconstruct: no live predictions yet, nothing to fill")
        return
    start = date.fromisoformat(live_dates[0])
    today = date.today()
    window = [start + timedelta(days=i) for i in range((today - start).days + 1)]
    print(f"Live window: {start} to {today} ({len(window)} calendar days)")
    print(f"  logged live on {len(live_dates)} days, "
          f"never ran on {len(window) - len(live_dates)} days")
    print("  rebuilding all %d days on one settled-close basis\n" % len(window))

    universe = ([(c, c + "-USD", "crypto") for c in COINS] +
                [(n, sym, "commodity") for n, sym in COMMODITIES.items()] +
                [(n, sym, "fx") for n, sym in PAIRS.items()])
    series = {}
    for name, sym, cls in universe:
        s = fetch(sym)
        if s is not None and len(s) > 260:
            series[name] = (s, cls)
    if "BTC" not in series:
        print("reconstruct: no BTC data")
        return
    btc = series["BTC"][0]
    btc_ma = btc.rolling(70).mean()
    print(f"Fetched {len(series)} assets "
          f"({sum(1 for _, c in series.values() if c == 'crypto')} crypto, "
          f"{sum(1 for _, c in series.values() if c == 'commodity')} commodity, "
          f"{sum(1 for _, c in series.values() if c == 'fx')} fx)\n")

    # Reconstructed rows deliberately share (date, asset, horizon) with the live
    # rows where the job did run. They are a parallel record on a consistent
    # settled-close basis, not a replacement, so the key carries the source.
    have = {(p["date"], p["asset"], p["horizon"]) for p in preds
            if p.get("source") == "reconstructed"}
    live_by_key = {(p["date"], p["asset"], p["horizon"]): p
                   for p in preds if p.get("source") == "live"}

    # ---- validation: reproduce the days that DID run ----
    checked = match = prob_close = 0
    for (dstr, asset, h), lp in live_by_key.items():
        if asset not in series:
            continue
        s, cls = series[asset]
        inp = inputs_at(pd.Timestamp(dstr), asset, s, cls, btc, btc_ma)
        if inp is None:
            continue
        prob = make_prediction(inp, h)
        checked += 1
        if ("up" if prob >= 0.5 else "down") == lp["predicted"]:
            match += 1
        if abs(round(prob, 3) - lp["prob_up"]) <= 0.01:
            prob_close += 1
    if checked:
        print(f"VALIDATION against {checked} live calls that were actually logged:")
        print(f"  direction reproduced : {match}/{checked} ({100*match/checked:.1f}%)")
        print(f"  prob within 0.01     : {prob_close}/{checked} "
              f"({100*prob_close/checked:.1f}%)\n")

    # ---- fill the missing days ----
    added = 0
    for d in window:
        dstr = str(d)
        for asset, (s, cls) in series.items():
            for h in HORIZONS:
                if (dstr, asset, h) in have:
                    continue
                inp = inputs_at(pd.Timestamp(dstr), asset, s, cls, btc, btc_ma)
                if inp is None:
                    continue
                prob = make_prediction(inp, h)
                s_up = s[s.index <= pd.Timestamp(dstr)]
                preds.append(dict(
                    date=dstr, asset=asset, horizon=h, cls=cls,
                    price0=inp["price"],
                    price_date=str(s_up.index[-1].date()),
                    prob_up=round(prob, 3),
                    predicted="up" if prob >= 0.5 else "down",
                    resolve_date=str(d + timedelta(days=h)),
                    resolved=False, actual=None, correct=None,
                    source="reconstructed",
                    feat_basis="pit-exact" if h <= 7 else "pit-approx"))
                added += 1

    # ---- resolve everything matured, same rule predict.py uses ----
    newly = 0
    for p in preds:
        if p.get("resolved") or p["asset"] not in series:
            continue
        s = series[p["asset"]][0]
        after = s[s.index >= pd.Timestamp(p["resolve_date"])]
        if len(after) == 0:
            continue
        price1 = float(after.iloc[0])
        actual = "up" if price1 >= p["price0"] else "down"
        p.update(resolved=True, actual=actual, price1=price1,
                 correct=(actual == p["predicted"]))
        newly += 1

    print(f"Reconstructed {added} calls across the full window; resolved {newly} rows.")
    if dry:
        print("(dry run, log not written)")
        return
    json.dump({"predictions": preds}, open(LOG, "w"), indent=2)
    print(f"Wrote {LOG}")


if __name__ == "__main__":
    main()
