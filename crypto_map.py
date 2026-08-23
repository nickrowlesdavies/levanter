#!/usr/bin/env python3
"""
Wide crypto market map on CoinGecko data (accurate prices + real market caps,
proper stablecoin coverage). Builds:
  * market-cap treemap (box = cap, colour = 30-day return)
  * ranked 30-day returns for the top coins by market cap
  * a stablecoin peg monitor (CoinGecko's stablecoin category, ranked by cap)
  * a return-correlation heatmap (7-day)
  * cap-weighted vs equal-weight market return, BTC dominance, total cap

BULK FETCH: everything comes from CoinGecko's /coins/markets endpoint in just
two calls (top coins + stablecoins), using its built-in percentage-change fields
and the 7-day sparkline. This is fast and reliable on rate-limited CI runners,
unlike the old per-coin /market_chart approach (~60 calls) which timed out and
left the crypto tab blank. Returns are 30-day (consistent with the FX and
commodities tabs); series-based stats (correlation, volatility, drawdown) use
the 7-day sparkline. Longer horizons come from CoinGecko's 200d and 1y fields.

Results are CACHED for 12h; pass --force to refetch now.

    python crypto_map.py [--force]
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import squarify
import warnings
warnings.filterwarnings("ignore")

CG = "https://api.coingecko.com/api/v3"
# Non-crypto-native tokens to exclude: tokenized commodities, RWA/yield dollar
# tokens, and wrapped/staked BTC/ETH duplicates. They ride in the top-by-cap
# list but aren't momentum plays.
EXCLUDE = {"PAXG", "XAUT", "USDY", "USYC", "USDS", "USD0", "OUSG", "BUIDL",
           "WBTC", "WETH", "STETH", "WSTETH", "WEETH", "RETH", "WBETH",
           "CBBTC", "LBTC", "SOLVBTC", "WBT", "BSC-USD", "WBNB", "BGB"}
COMMODITIES = {"GOLD": ("GC=F", "Gold"), "SILVER": ("SI=F", "Silver"),
               "OIL": ("CL=F", "Crude Oil (WTI)"), "COPPER": ("HG=F", "Copper"),
               "NATGAS": ("NG=F", "Natural Gas"), "PLAT": ("PL=F", "Platinum"),
               "CMDTY": ("DBC", "Broad Commodities"), "AGRI": ("DBA", "Agriculture")}
HOT_30D = 5.0            # a commodity qualifies as "hot" if its 30-day move >= this %
RET_HZ = 30              # headline return window (days), matches FX/commodities
# Movement horizons for the "top movers" leaderboard, from CoinGecko's fields.
MOVER_HZ = [("7d", "chg7"), ("14d", "chg14"), ("30d", "chg30"),
            ("6mo", "chg180"), ("12mo", "chg365")]
N_COINS = 35             # top non-stable coins by market cap
N_STABLES = 16           # top stablecoins by market cap
CACHE_TTL = 12 * 3600    # seconds
JSON_PATH = "reports/crypto_map.json"


def cg_get(path, params, tries=4):
    """GET with fast-ish backoff. Gives up cleanly rather than hanging, so a
    rate-limited CI run falls back to the committed cache instead of timing out."""
    for i in range(tries):
        try:
            r = requests.get(CG + path, params=params, timeout=30)
        except Exception:
            time.sleep(2); continue
        if r.status_code == 429:
            time.sleep(8 * (i + 1)); continue
        if r.status_code == 200:
            return r.json()
        time.sleep(2)
    return None


def chg(s, n):
    """Percent change over the last n days (for the yfinance commodity series)."""
    return float(s.iloc[-1] / s.iloc[-(n + 1)] - 1) * 100 if len(s) > n else None


def _spark(x):
    """7-day hourly price sparkline as a numpy array (or None)."""
    sp = (x.get("sparkline_in_7d") or {}).get("price") or []
    arr = np.array([float(v) for v in sp if v is not None], dtype=float)
    return arr if arr.size >= 12 else None


def _pc(x, key):
    v = x.get(key)
    return float(v) if v is not None else None


def fetch_commodities():
    """Gold + commodities via yfinance. Returns rows only for the ones that are
    'hot' (30-day move >= HOT_30D), tagged kind='commodity'."""
    import yfinance as yf
    rows = []
    for code, (sym, label) in COMMODITIES.items():
        try:
            raw = yf.download(sym, period="400d", interval="1d",
                              progress=False, auto_adjust=True)
            if raw is None or "Close" not in raw:
                continue
            s = raw["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = pd.Series(np.asarray(s).ravel(), index=raw.index).dropna()
            if len(s) < 40:
                continue
            c30 = chg(s, 30)
            if c30 is None or c30 < HOT_30D:
                continue
            s90 = s.tail(90)
            ma = s90.rolling(min(50, len(s90))).mean().iloc[-1]
            row = dict(
                coin=code, label=label, kind="commodity", signal="hot",
                ret=float(s90.iloc[-1] / s90.iloc[0] - 1) * 100,
                chg1=chg(s, 1), chg7=chg(s, 7), chg14=chg(s, 14), chg28=chg(s, 28),
                chg30=chg(s, 30), chg60=chg(s, 60), chg180=chg(s, 180),
                chg365=chg(s, 365),
                trend=("up" if s90.iloc[-1] > ma else "down"),
                spark=[round(float(v), 6) for v in s90.iloc[::3].tolist()],
                hist=[float(f"{v:.6g}") for v in s.tail(365).tolist()],
                vol=float(s90.pct_change().std() * np.sqrt(252) * 100),
                dd=float(((s90 - s90.cummax()) / s90.cummax()).min() * 100),
                price=float(s.iloc[-1]), market_cap=0)
            row["risk"], row["risk_band"] = risk_score(
                row["vol"], row["dd"], None, row["trend"])
            rows.append(row)
        except Exception:
            pass
    rows.sort(key=lambda r: r.get("chg30") or -999, reverse=True)
    return rows


def risk_score(vol, dd, mcap, trend):
    """Transparent 0-100 risk score (higher = riskier)."""
    vol_s = min((vol or 75) / 150.0, 1.0)
    dd_s = min(abs(dd or 35) / 70.0, 1.0)
    cap_s = 0.5
    if mcap and mcap > 0:
        cap_s = min(max((11 - math.log10(mcap)) / 3.0, 0.0), 1.0)
    base = 0.45 * vol_s + 0.30 * dd_s + 0.25 * cap_s
    if trend == "down":
        base += 0.10
    score = int(round(100 * min(base, 1.0)))
    band = ("low" if score < 30 else "medium" if score < 55
            else "high" if score < 75 else "extreme")
    return score, band


def peg_status(low: float) -> str:
    if low >= 0.995:
        return "ok"
    if low >= 0.98:
        return "watch"
    return "alert"


def _coin_row(x):
    """Build one coin row from a /coins/markets entry (with sparkline + % fields)."""
    arr = _spark(x)
    if arr is None:
        return None, None
    sym = x["symbol"].upper()
    price = float(x.get("current_price") or arr[-1])
    mcap = float(x.get("market_cap") or 0)
    # 7-day series stats from the sparkline (hourly).
    rets = np.diff(arr) / arr[:-1]
    vol = float(np.std(rets) * math.sqrt(24 * 365) * 100)   # annualised, from 7d hourly
    cummax = np.maximum.accumulate(arr)
    dd = float(((arr - cummax) / cummax).min() * 100)
    chg30 = _pc(x, "price_change_percentage_30d_in_currency")
    chg7 = _pc(x, "price_change_percentage_7d_in_currency")
    ret = chg30 if chg30 is not None else (chg7 if chg7 is not None else 0.0)
    trend_ref = chg30 if chg30 is not None else chg7
    row = dict(
        coin=sym, price=price, market_cap=mcap, ret=ret,
        chg1=_pc(x, "price_change_percentage_24h_in_currency"),
        chg7=chg7, chg14=_pc(x, "price_change_percentage_14d_in_currency"),
        chg28=None, chg30=chg30, chg60=None,
        chg180=_pc(x, "price_change_percentage_200d_in_currency"),
        chg365=_pc(x, "price_change_percentage_1y_in_currency"),
        trend=("up" if (trend_ref or 0) >= 0 else "down"),
        spark=[round(float(v), 6) for v in arr[::6].tolist()],   # ~28 pts for inline
        hist=[float(f"{v:.6g}") for v in arr.tolist()],          # full 7d for modal chart
        vol=vol, dd=dd)
    row["risk"], row["risk_band"] = risk_score(vol, dd, mcap, row["trend"])
    return row, arr


def fetch_all():
    top = cg_get("/coins/markets", {
        "vs_currency": "usd", "order": "market_cap_desc", "per_page": 80, "page": 1,
        "sparkline": "true",
        "price_change_percentage": "24h,7d,14d,30d,200d,1y"}) or []
    stab = cg_get("/coins/markets", {
        "vs_currency": "usd", "category": "stablecoins", "order": "market_cap_desc",
        "per_page": N_STABLES, "page": 1, "sparkline": "true"}) or []
    if not top:
        return {}, [], {}, []
    stable_ids = {x["id"] for x in stab}

    coin_meta = [x for x in top if x["id"] not in stable_ids
                 and x["symbol"].upper() not in EXCLUDE][:N_COINS]
    coins_series, coin_rows = {}, []
    for x in coin_meta:
        row, arr = _coin_row(x)
        if row is None:
            continue
        # Skip non-tradeable dollar/yield/RWA tokens that barely move (a steady
        # drift fakes momentum). Real coins are far more volatile.
        if row["vol"] < 12:
            continue
        coins_series[row["coin"]] = arr
        coin_rows.append(row)

    stable_rows, stable_series = [], {}
    for x in stab:
        arr = _spark(x)
        if arr is None:
            continue
        med = float(np.median(arr))
        if not (0.90 <= med <= 1.10):
            continue
        sym = x["symbol"].upper()
        low = float(np.percentile(arr, 2))
        stable_series[sym] = arr
        stable_rows.append(dict(
            coin=sym, ret=float(arr[-1] / arr[0] - 1) * 100,
            minp=low, maxp=float(np.percentile(arr, 98)),
            price=float(x.get("current_price") or arr[-1]),
            mcap_b=float(x.get("market_cap") or 0) / 1e9,
            status=peg_status(low)))
    stable_rows.sort(key=lambda r: r["minp"])
    return coins_series, coin_rows, stable_series, stable_rows


def _corr_df(series_map):
    """Align sparkline arrays by position (all ~7d hourly) into a DataFrame."""
    if not series_map:
        return pd.DataFrame()
    n = min(len(v) for v in series_map.values())
    return pd.DataFrame({k: v[-n:] for k, v in series_map.items()})


def build(coins_series, coin_rows, stable_series, stable_rows):
    coin_rows.sort(key=lambda r: r["ret"], reverse=True)
    capped = [r for r in coin_rows if r["market_cap"]]
    total_mcap = sum(r["market_cap"] for r in capped) or 1
    cap_w = sum(r["ret"] * r["market_cap"] for r in capped) / total_mcap
    eq_w = float(np.mean([r["ret"] for r in coin_rows])) if coin_rows else 0.0
    btc_mcap = next((r["market_cap"] for r in coin_rows if r["coin"] == "BTC"), 0)
    btc_dom = btc_mcap / total_mcap * 100 if capped else 0.0

    df = _corr_df(coins_series)
    order = [r["coin"] for r in coin_rows if r["coin"] in df.columns]
    if len(order) > 1:
        corr = df[order].pct_change().dropna().corr()
        avg_corr = float(corr.values[np.triu_indices_from(corr.values, k=1)].mean())
    else:
        avg_corr = 0.0

    # Return window is 30 days (headline ret); label it accordingly.
    end = dt.date.today()
    start = end - dt.timedelta(days=RET_HZ)

    # Market regime: risk-on when BTC's 30-day trend is up (proxy for the old
    # "BTC above its 10-week average"; the bulk feed has no long daily series).
    btc_chg30 = next((r.get("chg30") for r in coin_rows if r["coin"] == "BTC"), None)
    regime_on = bool(btc_chg30 is None or btc_chg30 >= 0)

    # Per-coin systematic signal (model output, NOT advice).
    K = 8
    for i, r in enumerate(coin_rows):
        r["rank"] = i + 1
        if not regime_on:
            r["signal"] = "risk-off"
        elif i < K and r.get("trend") == "up":
            r["signal"] = "buy"
        elif r.get("trend") == "up":
            r["signal"] = "hold"
        else:
            r["signal"] = "avoid"
    recommendation = ([r["coin"] for r in coin_rows if r["signal"] == "buy"]
                      if regime_on else [])

    movers = {}
    for label, f in MOVER_HZ:
        ranked = sorted((c for c in coin_rows if c.get(f) is not None),
                        key=lambda c: c[f], reverse=True)
        movers[label] = [{"coin": c["coin"], "ret": round(c[f], 1)} for c in ranked[:3]]

    commodity_rows = fetch_commodities()

    os.makedirs("reports", exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(dict(window_days=RET_HZ, start=str(start), end=str(end),
                       coins=coin_rows, commodities=commodity_rows,
                       stables=stable_rows, avg_corr=avg_corr, cap_weighted_ret=cap_w,
                       equal_weighted_ret=eq_w, btc_dominance=btc_dom,
                       total_mcap_b=total_mcap / 1e9, regime_on=regime_on,
                       recommendation=recommendation, movers=movers,
                       source="coingecko"), f, indent=2)

    # Treemap (colour = 30-day return)
    tm = sorted(capped, key=lambda r: r["market_cap"], reverse=True)
    if tm:
        norm = mcolors.Normalize(vmin=-40, vmax=40)
        cmap = plt.get_cmap("RdYlGn")
        plt.figure(figsize=(12, 7))
        squarify.plot(sizes=[r["market_cap"] for r in tm],
                      label=[f"{r['coin']}\n{r['ret']:+.0f}%" for r in tm],
                      color=[cmap(norm(r["ret"])) for r in tm], pad=True,
                      text_kwargs={"fontsize": 8})
        plt.axis("off")
        plt.title(f"Crypto market map - box size = market cap, colour = {RET_HZ}-day return")
        plt.tight_layout(); plt.savefig("reports/crypto_map_treemap.png", dpi=130); plt.close()

    # Ranked returns
    plt.figure(figsize=(10, max(6, len(coin_rows) * 0.28)))
    names = [r["coin"] for r in coin_rows][::-1]
    vals = [r["ret"] for r in coin_rows][::-1]
    plt.barh(names, vals, color=["#16a34a" if v >= 0 else "#dc2626" for v in vals])
    plt.axvline(0, color="#888", lw=0.8)
    plt.title(f"Top coins by market cap - {RET_HZ}-day return %")
    plt.xlabel("Return %"); plt.tick_params(labelsize=8)
    plt.tight_layout(); plt.savefig("reports/crypto_map_returns.png", dpi=130); plt.close()

    # Stablecoin peg (7-day sparklines)
    plt.figure(figsize=(11, 5))
    for c, arr in stable_series.items():
        plt.plot(range(len(arr)), arr, label=c, linewidth=1.4)
    plt.axhline(1.0, color="#111", ls="--", lw=0.9)
    plt.axhline(0.995, color="#d97706", ls=":", lw=0.9)
    plt.ylim(0.98, 1.012)
    plt.title("Stablecoin peg monitor - last 7 days ($1.00 = peg)")
    plt.ylabel("Price (USD)"); plt.legend(ncol=6, fontsize=8, frameon=False)
    plt.tight_layout(); plt.savefig("reports/crypto_map_stablecoins.png", dpi=130); plt.close()

    # Correlation heatmap (top 24, 7-day)
    sub = order[:24]
    if len(sub) > 1:
        cmat = df[sub].pct_change().dropna().corr()
        plt.figure(figsize=(9, 8))
        im = plt.imshow(cmat, cmap="RdYlGn", vmin=-1, vmax=1)
        plt.colorbar(im, fraction=0.046, pad=0.04, label="correlation")
        plt.xticks(range(len(sub)), sub, rotation=90, fontsize=7)
        plt.yticks(range(len(sub)), sub, fontsize=7)
        plt.title(f"Return correlations - last 7 days (top {len(sub)})")
        plt.tight_layout(); plt.savefig("reports/crypto_map_correlation.png", dpi=130); plt.close()

    return dict(start=str(start), end=str(end), best=coin_rows[0], worst=coin_rows[-1],
                cap_w=cap_w, eq_w=eq_w, btc_dom=btc_dom, total=total_mcap / 1e9,
                avg_corr=avg_corr, n_coins=len(coin_rows), n_stables=len(stable_rows),
                watch=[r for r in stable_rows if r["status"] != "ok"])


def main():
    force = "--force" in sys.argv
    if not force and os.path.exists(JSON_PATH) and \
            time.time() - os.path.getmtime(JSON_PATH) < CACHE_TTL:
        print("crypto_map: cached data is fresh (<12h); use --force to refetch.")
        return

    print("crypto_map: fetching from CoinGecko (bulk, 2 calls)...")
    coins_series, coin_rows, stable_series, stable_rows = fetch_all()
    if not coin_rows:
        print("crypto_map: no data returned (rate limited?). Keeping previous cache.")
        return
    s = build(coins_series, coin_rows, stable_series, stable_rows)
    print(f"\nCoinGecko · {s['n_coins']} coins, {s['n_stables']} stablecoins · "
          f"{s['start']} -> {s['end']} ({RET_HZ}d returns)")
    print(f"Best {s['best']['coin']} {s['best']['ret']:+.0f}%  "
          f"Worst {s['worst']['coin']} {s['worst']['ret']:+.0f}%  "
          f"Avg corr {s['avg_corr']:.2f}")
    print(f"Market cap-weighted {s['cap_w']:+.1f}% vs equal-weight {s['eq_w']:+.1f}%  |  "
          f"BTC dominance {s['btc_dom']:.0f}%  |  total cap ${s['total']:,.0f}B")
    if s["watch"]:
        print("PEG WATCH: " + ", ".join(f"{r['coin']}({r['minp']:.4f})" for r in s["watch"]))
    else:
        print("All stablecoins holding peg.")
    print("Wrote reports/crypto_map.json + charts.\n")


if __name__ == "__main__":
    main()
