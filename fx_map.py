#!/usr/bin/env python3
"""
FX market map: majors + key crosses, same movement analysis as the crypto map
(7d/14d/28d/60d/6mo/12mo moves, trend, vol) so the FX tab mirrors crypto.
FX has no market cap or power-law cycle, so this is movers + trend + vol only.

    python fx_map.py   -> reports/fx_map.json (+ movers)
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

# label -> yfinance symbol (majors first, then key crosses)
PAIRS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCHF": "USDCHF=X", "USDCAD": "USDCAD=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "AUDJPY": "AUDJPY=X", "EURCHF": "EURCHF=X",
    "USDSEK": "USDSEK=X", "USDNOK": "USDNOK=X", "USDMXN": "USDMXN=X",
    "USDZAR": "USDZAR=X",
}
MOVER_HZ = [("7d", 7), ("14d", 14), ("28d", 28), ("60d", 60),
            ("6mo", 180), ("12mo", 365)]
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
    for name, sym in PAIRS.items():
        s = fetch(sym)
        if s is None or len(s) < 60:
            continue
        s90 = s.tail(DAYS)
        ma = s90.rolling(min(50, len(s90))).mean().iloc[-1]
        rows.append(dict(
            pair=name, price=float(s.iloc[-1]),
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
    for lbl, _ in MOVER_HZ:
        f = field[lbl]
        r = sorted((c for c in rows if c.get(f) is not None),
                   key=lambda c: c[f], reverse=True)
        movers[lbl] = [{"pair": c["pair"], "ret": round(c[f], 1)} for c in r[:3]]

    os.makedirs("reports", exist_ok=True)
    json.dump({"pairs": rows, "movers": movers,
               "updated": str(pd.Timestamp.utcnow().date())},
              open("reports/fx_map.json", "w"), indent=2)
    print(f"fx map: {len(rows)} pairs")
    if rows:
        print(f"  best 30d: {rows[0]['pair']} {rows[0].get('chg30',0):+.1f}%  "
              f"worst: {rows[-1]['pair']} {rows[-1].get('chg30',0):+.1f}%")


if __name__ == "__main__":
    main()
