#!/usr/bin/env python3
"""
Commodities market map: full set (metals, energy, ags, broad), same movement
analysis as crypto/FX so the Commodities tab mirrors them.

    python commodities_map.py  -> reports/commodities_map.json (+ movers)
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

ITEMS = {"GOLD": "GC=F", "SILVER": "SI=F", "PLATINUM": "PL=F", "PALLADIUM": "PA=F",
         "WTI OIL": "CL=F", "BRENT OIL": "BZ=F", "NAT GAS": "NG=F", "COPPER": "HG=F",
         "BROAD": "DBC", "AGRICULTURE": "DBA", "WHEAT": "ZW=F", "CORN": "ZC=F",
         # Expanded coverage: complete the grains trio, add the softs that move on
         # weather/supply, and the refined-energy leg beyond crude.
         "SOYBEANS": "ZS=F", "COFFEE": "KC=F", "SUGAR": "SB=F", "COTTON": "CT=F",
         "GASOLINE": "RB=F", "HEATING OIL": "HO=F"}
MOVER_HZ = ["7d", "14d", "28d", "60d", "6mo", "12mo"]
DAYS = 90


def fetch(sym):
    import yfinance as yf
    raw = yf.download(sym, period="400d", interval="1d", progress=False,
                      auto_adjust=True)["Close"]
    if raw is None or len(raw) == 0:
        return None
    if isinstance(raw, pd.DataFrame):
        raw = raw.iloc[:, 0]
    return pd.Series(np.asarray(raw).ravel(), index=raw.index).dropna()


def chg(s, n):
    past = s[s.index <= s.index[-1] - pd.Timedelta(days=n)]
    return float(s.iloc[-1] / past.iloc[-1] - 1) * 100 if len(past) else None


def main():
    rows = []
    for name, sym in ITEMS.items():
        s = fetch(sym)
        if s is None or len(s) < 60:
            continue
        s90 = s.tail(DAYS)
        ma = s90.rolling(min(50, len(s90))).mean().iloc[-1]
        rows.append(dict(
            name=name, price=float(s.iloc[-1]),
            chg1=chg(s, 1), chg7=chg(s, 7), chg14=chg(s, 14), chg28=chg(s, 28),
            chg30=chg(s, 30), chg60=chg(s, 60), chg180=chg(s, 180),
            chg365=chg(s, 365),
            ret=float(s90.iloc[-1] / s90.iloc[0] - 1) * 100,
            trend=("up" if s90.iloc[-1] > ma else "down"),
            spark=[round(float(v), 6) for v in s90.iloc[::3].tolist()],
            hist=[float(f"{v:.6g}") for v in s.tail(365).tolist()],
            vol=float(s90.pct_change().std() * np.sqrt(252) * 100)))
    rows.sort(key=lambda r: (r.get("chg30") or -999), reverse=True)

    field = {"7d": "chg7", "14d": "chg14", "28d": "chg28", "60d": "chg60",
             "6mo": "chg180", "12mo": "chg365"}
    movers = {}
    for lbl in MOVER_HZ:
        f = field[lbl]
        r = sorted((c for c in rows if c.get(f) is not None),
                   key=lambda c: c[f], reverse=True)
        movers[lbl] = [{"name": c["name"], "ret": round(c[f], 1)} for c in r[:3]]

    os.makedirs("reports", exist_ok=True)
    json.dump({"items": rows, "movers": movers,
               "updated": str(pd.Timestamp.utcnow().date())},
              open("reports/commodities_map.json", "w"), indent=2)
    print(f"commodities map: {len(rows)} items")
    if rows:
        print(f"  best 30d: {rows[0]['name']} {rows[0].get('chg30',0):+.1f}%  "
              f"worst: {rows[-1]['name']} {rows[-1].get('chg30',0):+.1f}%")


if __name__ == "__main__":
    main()
