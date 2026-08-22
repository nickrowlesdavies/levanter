#!/usr/bin/env python3
"""
=====================================================================
 EDUCATIONAL / EXPERIMENTAL PREDICTION MODEL - ZERO LIABILITY
=====================================================================
A toy mechanical model that makes dated calls across a broad universe and
auto-scores them against reality, to MEASURE honestly whether it can beat a
coin flip. NOT a forecast, NOT advice, NO liability. Expect ~50% accuracy.

  * Coins + commodities/gold -> DIRECTIONAL (up/down) calls, scored on the
    actual move over the horizon.
  * Stablecoins -> a separate PEG-HOLD outlook (direction is meaningless on a
    $1 peg). Kept out of the directional accuracy so it can't flatter it.

Blend: value (vs power-law trend, majors only), 7d/30d momentum, trend
filter, cycle phase, market regime -> probability via a logistic squash.

    python predict.py
Outputs: reports/prediction_log.json + reports/prediction_state.json
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "AVAX",
         "LINK", "TRX", "LTC", "BCH", "XLM", "ATOM", "HBAR", "ICP", "XMR",
         "ETC", "FIL"]
COMMODITIES = {"GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F",
               "COPPER": "HG=F", "PLAT": "PL=F", "NATGAS": "NG=F"}
PAIRS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
         "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X", "USDCAD": "USDCAD=X",
         "NZDUSD": "NZDUSD=X"}
CLASSES = ("crypto", "commodity", "fx")
HORIZONS = [7, 30]
LOG = "reports/prediction_log.json"
STATE = "reports/prediction_state.json"


def _read(p):
    return json.load(open(p)) if os.path.exists(p) else {}


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="200d", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def _logistic(x):
    return 1.0 / (1.0 + math.exp(-x))


def _clip(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def ret_over(s, ndays):
    past = s[s.index <= s.index[-1] - pd.Timedelta(days=ndays)]
    return float(s.iloc[-1] / past.iloc[-1] - 1) * 100 if len(past) else 0.0


def make_prediction(s, horizon):
    """s: dict(price, pct_vs_trend, phase, chg7, chg30, trend, regime)."""
    v = _clip(-(s.get("pct_vs_trend", 0.0)) / 40.0)
    m7 = _clip(s.get("chg7", 0.0) / 15.0)
    m30 = _clip(s.get("chg30", 0.0) / 40.0)
    tr = 0.6 if s.get("trend") == "up" else -0.6
    cyc = {"Pre-peak bull": 0.4, "Peak window": -0.1,
           "Post-peak cooldown": -0.4, "Late cycle": -0.2}.get(s.get("phase"), 0.0)
    reg = 0.4 if s.get("regime") else -0.4
    if horizon <= 7:
        bull = 0.50 * m7 + 0.25 * tr + 0.15 * reg + 0.10 * m30
    else:
        bull = 0.40 * v + 0.25 * cyc + 0.20 * tr + 0.15 * m30
    return _logistic(2.0 * bull)


def build_inputs(sym, s, cls, btc, btc_ma, cg_val, shared_phase):
    price = float(s.iloc[-1])
    ma50 = float(s.rolling(50).mean().iloc[-1])
    trend = "up" if price > ma50 else "down"
    if cls == "crypto":
        regime = bool(btc.iloc[-1] > btc_ma.iloc[-1])   # crypto: BTC regime + cycle
        phase = shared_phase
    else:
        regime, phase = (trend == "up"), ""      # fx/commodities: own trend, no cycle
    return dict(price=price, pct_vs_trend=cg_val.get(sym, 0.0), phase=phase,
                chg7=ret_over(s, 7), chg30=ret_over(s, 30), trend=trend,
                regime=regime)


def main():
    today = datetime.utcnow().date()
    cg = _read("reports/cycle_gauge.json")
    cg_val = {a["sym"]: a.get("pct_vs_trend", 0.0) for a in cg.get("assets", [])
              if a.get("kind") == "crypto"}
    shared_phase = cg.get("phase", "")

    series = {}   # name -> (price series, class)
    for c in COINS:
        s = fetch(c + "-USD")
        if s is not None and len(s) > 60:
            series[c] = (s, "crypto")
    for name, sym in COMMODITIES.items():
        s = fetch(sym)
        if s is not None and len(s) > 60:
            series[name] = (s, "commodity")
    for name, sym in PAIRS.items():
        s = fetch(sym)
        if s is not None and len(s) > 60:
            series[name] = (s, "fx")
    if "BTC" not in series:
        print("predict: no BTC data")
        return
    btc = series["BTC"][0]
    btc_ma = btc.rolling(70).mean()

    log = _read(LOG) if os.path.exists(LOG) else {"predictions": []}
    preds = log["predictions"]
    existing = {(p["date"], p["asset"], p["horizon"]) for p in preds}

    for sym, (s, cls) in series.items():
        inp = build_inputs(sym, s, cls, btc, btc_ma, cg_val, shared_phase)
        for h in HORIZONS:
            if (str(today), sym, h) in existing:
                continue
            prob = make_prediction(inp, h)
            preds.append(dict(date=str(today), asset=sym, horizon=h,
                              cls=cls,
                              price0=inp["price"], prob_up=round(prob, 3),
                              predicted="up" if prob >= 0.5 else "down",
                              resolve_date=str(today + timedelta(days=h)),
                              resolved=False, actual=None, correct=None,
                              source="live"))

    # Resolve matured directional predictions from the fetched daily series.
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

    json.dump({"predictions": preds}, open(LOG, "w"), indent=2)

    # ---- scorecard ----
    res = [p for p in preds if p["resolved"]]
    def acc(items):
        return (sum(1 for p in items if p["correct"]) / len(items) * 100) if items else None
    open_latest = {}
    for p in preds:
        if not p["resolved"]:
            open_latest[(p["asset"], p["horizon"])] = p
    openc = list(open_latest.values())
    ups = sum(1 for p in openc if p["predicted"] == "up")

    # stablecoin peg-hold outlook (from the crypto map; not scored here)
    cm = _read("reports/crypto_map.json")
    stables = cm.get("stables", [])
    at_risk = [s["coin"] for s in stables if s.get("status") != "ok"]

    # Per-class scorecards so each dashboard tab shows only its own class.
    cls_of = {name: cl for name, (_, cl) in series.items()}
    by_class = {}
    for cl in CLASSES:
        cres = [p for p in res if p.get("cls") == cl]
        copen = [p for p in openc if p.get("cls") == cl]
        cups = sum(1 for p in copen if p["predicted"] == "up")
        by_class[cl] = dict(
            resolved_count=len(cres), accuracy=acc(cres),
            accuracy_by_horizon={h: acc([p for p in cres if p["horizon"] == h])
                                 for h in HORIZONS},
            n_assets=sum(1 for c in cls_of.values() if c == cl),
            open_up=cups, open_down=len(copen) - cups,
            top_calls=sorted(copen, key=lambda p: abs(p["prob_up"] - 0.5),
                             reverse=True)[:6])

    state = dict(
        updated=str(today),
        resolved_count=len(res), accuracy=acc(res),
        accuracy_by_horizon={h: acc([p for p in res if p["horizon"] == h]) for h in HORIZONS},
        accuracy_by_class={cl: acc([p for p in res if p.get("cls") == cl])
                           for cl in CLASSES},
        by_class=by_class,
        n_assets=len(series), open_up=ups, open_down=len(openc) - ups,
        top_calls=sorted(openc, key=lambda p: abs(p["prob_up"] - 0.5), reverse=True)[:6],
        pegs=dict(tracked=len(stables), at_risk=at_risk),
        recent_resolved=sorted(res, key=lambda p: p["resolve_date"])[-8:])
    json.dump(state, open(STATE, "w"), indent=2)

    a = state["accuracy"]
    print(f"predict: {len(preds)} logged across {len(series)} assets, "
          f"{len(res)} resolved, accuracy " +
          (f"{a:.0f}%" if a is not None else "n/a (building)"))
    print(f"  open calls: {ups} UP / {len(openc)-ups} DOWN  |  "
          f"stablecoins tracked {len(stables)}, at-risk {at_risk or 'none'}")


if __name__ == "__main__":
    main()
