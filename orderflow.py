#!/usr/bin/env python3
"""
Crypto ORDER-FLOW features from Binance futures (free, historical, so it can
be backtested point-in-time). Two genuinely-new-information signals per coin:

  * taker_ratio - fraction of each day's volume that was AGGRESSIVE BUYING
    (taker buy base volume / total volume). >0.5 = net buyers lifting offers.
  * funding      - perpetual funding rate (positive = longs pay shorts =
    crowded/leveraged long; extreme levels flag positioning).

Returns a daily DataFrame indexed by date with columns [taker_ratio, funding],
cached to CSV (refreshed every ~12h).

    python orderflow.py        # prints a quick BTC/ETH/SOL read
"""
from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd
import requests
import warnings
warnings.filterwarnings("ignore")

FAPI = "https://fapi.binance.com/fapi/v1"
# coin -> Binance USDT-perp symbol (only coins with a liquid perp)
PERP = {c: c + "USDT" for c in
        ["BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "AVAX",
         "LINK", "TRX", "LTC", "BCH", "XLM", "ATOM", "ICP", "ETC", "FIL"]}
CACHE_TTL = 12 * 3600


def _get(path, params):
    r = requests.get(f"{FAPI}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def orderflow(coin: str, cache_dir="data_cache") -> pd.DataFrame | None:
    sym = PERP.get(coin)
    if sym is None:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"of_{coin}.csv")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < CACHE_TTL:
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    try:
        # daily klines -> taker buy ratio (field 9 = taker buy base vol, 5 = vol)
        kl = _get("klines", {"symbol": sym, "interval": "1d", "limit": 300})
        krows = [(pd.to_datetime(k[0], unit="ms").normalize(),
                  float(k[9]) / float(k[5]) if float(k[5]) else np.nan) for k in kl]
        taker = pd.Series({d: r for d, r in krows}, name="taker_ratio")
        # funding history (8h) -> daily mean
        fr = _get("fundingRate", {"symbol": sym, "limit": 1000})
        frows = [(pd.to_datetime(f["fundingTime"], unit="ms").normalize(),
                  float(f["fundingRate"])) for f in fr]
        fund = pd.Series({d: v for d, v in frows}).groupby(level=0).mean()
        fund.name = "funding"
        df = pd.concat([taker, fund], axis=1).sort_index().dropna(how="all")
        df["funding"] = df["funding"].ffill()
        df.to_csv(cache)
        return df
    except Exception:
        return None


def write_summary(path="reports/orderflow.json"):
    """Per-coin order-flow readout for the dashboard (context, not a predictor)."""
    import json
    rows = []
    for c in PERP:
        df = orderflow(c)
        if df is None or df.empty or len(df.dropna()) < 7:
            continue
        t7 = float(df["taker_ratio"].tail(7).mean())
        f3 = float(df["funding"].tail(3).mean())
        rows.append(dict(coin=c, buy_pct=round(t7 * 100, 1),
                         flow="buying" if t7 > 0.5 else "selling",
                         funding_pct=round(f3 * 100, 4),
                         fund_state="longs pay" if f3 > 0 else "shorts pay"))
    rows.sort(key=lambda r: r["buy_pct"], reverse=True)
    os.makedirs("reports", exist_ok=True)
    json.dump({"coins": rows}, open(path, "w"), indent=2)
    return rows


def main():
    rows = write_summary()
    print(f"order flow: {len(rows)} coins")
    for r in rows[:6]:
        print(f"  {r['coin']:<5} taker-buy {r['buy_pct']:.0f}% ({r['flow']}) | "
              f"funding {r['funding_pct']:+.4f}% ({r['fund_state']})")


if __name__ == "__main__":
    main()
