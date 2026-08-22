#!/usr/bin/env python3
"""
Wide crypto market map on CoinGecko data (accurate prices + real market caps,
proper stablecoin coverage). Builds:
  * market-cap treemap (box = cap, colour = 90-day return)
  * ranked 90-day returns for the top coins by market cap
  * a stablecoin peg monitor (CoinGecko's stablecoin category, ranked by cap)
  * a return-correlation heatmap
  * cap-weighted vs equal-weight market return, BTC dominance, total cap
and writes reports/crypto_map.json + charts for the dashboard.

CoinGecko's free API is rate-limited, so results are CACHED for 12h; pass
--force to refetch now.

    python crypto_map.py [--force]
"""
from __future__ import annotations

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
# Non-crypto-native tokens to exclude from the coin universe: tokenized
# commodities, RWA/yield dollar tokens, and wrapped/staked BTC/ETH duplicates.
# They ride in the top-by-market-cap list but aren't momentum plays.
EXCLUDE = {"PAXG", "XAUT", "USDY", "USYC", "USDS", "USD0", "OUSG", "BUIDL",
           "WBTC", "WETH", "STETH", "WSTETH", "WEETH", "RETH", "WBETH",
           "CBBTC", "LBTC", "SOLVBTC", "WBT", "BSC-USD", "WBNB", "BGB"}
# Commodity proxies (yfinance). Added to the list only when "hot" (see HOT_30D).
COMMODITIES = {"GOLD": ("GC=F", "Gold"), "SILVER": ("SI=F", "Silver"),
               "OIL": ("CL=F", "Crude Oil (WTI)"), "COPPER": ("HG=F", "Copper"),
               "NATGAS": ("NG=F", "Natural Gas"), "PLAT": ("PL=F", "Platinum"),
               "CMDTY": ("DBC", "Broad Commodities"), "AGRI": ("DBA", "Agriculture")}
HOT_30D = 5.0            # a commodity qualifies as "hot" if its 30-day move >= this %
DAYS = 90                # display window for signals/sparkline/vol/dd
FETCH_DAYS = 365         # history pulled, so 6- and 12-month movers are possible
# Movement horizons for the "top movers" leaderboard: (label, days).
MOVER_HZ = [("7d", 7), ("14d", 14), ("28d", 28), ("60d", 60),
            ("6mo", 180), ("12mo", 365)]
N_COINS = 35             # top non-stable coins by market cap
N_STABLES = 16           # top stablecoins by market cap
CACHE_TTL = 12 * 3600    # seconds
JSON_PATH = "reports/crypto_map.json"
SLEEP = 2.4              # between calls, to respect the free rate limit


def cg_get(path, params, tries=5):
    for i in range(tries):
        try:
            r = requests.get(CG + path, params=params, timeout=30)
        except Exception:
            time.sleep(3); continue
        if r.status_code == 429:              # rate limited -> back off
            time.sleep(20 * (i + 1)); continue
        if r.status_code == 200:
            return r.json()
        time.sleep(3)
    return None


def history(cid) -> pd.Series | None:
    d = cg_get(f"/coins/{cid}/market_chart", {"vs_currency": "usd", "days": FETCH_DAYS})
    if not d or "prices" not in d or not d["prices"]:
        return None
    px = pd.DataFrame(d["prices"], columns=["ms", "price"])
    px["date"] = pd.to_datetime(px["ms"], unit="ms")
    s = px.set_index("date")["price"].resample("1D").last().dropna()
    return s.tail(FETCH_DAYS)


def chg(s, n):
    """Percent change over the last n days, or None if not enough history."""
    return float(s.iloc[-1] / s.iloc[-(n + 1)] - 1) * 100 if len(s) > n else None


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
            if c30 is None or c30 < HOT_30D:          # only include hot ones
                continue
            s90 = s.tail(DAYS)
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
    """Transparent 0-100 risk score (higher = riskier), from volatility,
    90-day drawdown, market cap (liquidity/fragility) and trend direction."""
    vol_s = min((vol or 75) / 150.0, 1.0)              # 150% ann. vol = max
    dd_s = min(abs(dd or 35) / 70.0, 1.0)              # -70% drawdown = max
    cap_s = 0.5
    if mcap and mcap > 0:
        cap_s = min(max((11 - math.log10(mcap)) / 3.0, 0.0), 1.0)  # <$100M=1, >$100B=0
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


def fetch_all():
    top = cg_get("/coins/markets", {"vs_currency": "usd",
                 "order": "market_cap_desc", "per_page": 80, "page": 1,
                 "price_change_percentage": "200d,1y"}) or []
    stab = cg_get("/coins/markets", {"vs_currency": "usd", "category": "stablecoins",
                  "order": "market_cap_desc", "per_page": N_STABLES, "page": 1}) or []
    stable_ids = {x["id"] for x in stab}

    coin_meta = [x for x in top if x["id"] not in stable_ids
                 and x["symbol"].upper() not in EXCLUDE][:N_COINS]

    coins_series, coin_rows = {}, []
    for x in coin_meta:
        s_full = history(x["id"]); time.sleep(SLEEP)
        if s_full is None or len(s_full) < 10:
            continue
        s = s_full.tail(DAYS)              # 90-day window for signals/stats
        # Skip non-tradeable dollar/yield/RWA tokens (e.g. USDY, USYC) that
        # CoinGecko doesn't file under stablecoins. They barely move, so in a
        # down market their steady drift fakes a top-momentum "buy". Real coins
        # are far more volatile; annualised vol < 12% means "not a momentum coin".
        if float(s.pct_change().std() * np.sqrt(365) * 100) < 12:
            continue
        sym = x["symbol"].upper()
        coins_series[sym] = s
        ma = s.rolling(min(50, len(s))).mean().iloc[-1]
        row = dict(
            coin=sym, ret=float(s.iloc[-1] / s.iloc[0] - 1) * 100,
            chg1=chg(s_full, 1), chg7=chg(s_full, 7), chg14=chg(s_full, 14), chg28=chg(s_full, 28),
            chg30=chg(s_full, 30), chg60=chg(s_full, 60),
            chg180=chg(s_full, 180), chg365=chg(s_full, 365),
            trend=("up" if s.iloc[-1] > ma else "down"),
            spark=[round(float(v), 6) for v in s.iloc[::3].tolist()],
            hist=[float(f"{v:.6g}") for v in s_full.tail(365).tolist()],
            vol=float(s.pct_change().std() * np.sqrt(365) * 100),
            dd=float(((s - s.cummax()) / s.cummax()).min() * 100),
            price=float(x.get("current_price") or s.iloc[-1]),
            market_cap=float(x.get("market_cap") or 0))
        # Long horizons: prefer CoinGecko's markets change fields (free history
        # only spans ~6 months, so 12mo can't be computed from candles).
        m200 = x.get("price_change_percentage_200d_in_currency")
        m1y = x.get("price_change_percentage_1y_in_currency")
        if m200 is not None:
            row["chg180"] = float(m200)
        if m1y is not None:
            row["chg365"] = float(m1y)
        row["risk"], row["risk_band"] = risk_score(
            row["vol"], row["dd"], row["market_cap"], row["trend"])
        coin_rows.append(row)

    stable_rows, stable_series = [], {}
    for x in stab:
        s = history(x["id"]); time.sleep(SLEEP)
        if s is None or len(s) < 10:
            continue
        if not (0.90 <= float(s.median()) <= 1.10):    # must actually track $1
            continue
        sym = x["symbol"].upper()
        low = float(s.quantile(0.02))                  # robust low (ignore bad ticks)
        stable_series[sym] = s
        stable_rows.append(dict(
            coin=sym, ret=float(s.iloc[-1] / s.iloc[0] - 1) * 100,
            minp=low, maxp=float(s.quantile(0.98)),
            price=float(x.get("current_price") or s.iloc[-1]),
            mcap_b=float(x.get("market_cap") or 0) / 1e9,
            status=peg_status(low)))
    stable_rows.sort(key=lambda r: r["minp"])
    return coins_series, coin_rows, stable_series, stable_rows


def build(coins_series, coin_rows, stable_series, stable_rows):
    coin_rows.sort(key=lambda r: r["ret"], reverse=True)
    capped = [r for r in coin_rows if r["market_cap"]]
    total_mcap = sum(r["market_cap"] for r in capped) or 1
    cap_w = sum(r["ret"] * r["market_cap"] for r in capped) / total_mcap
    eq_w = float(np.mean([r["ret"] for r in coin_rows])) if coin_rows else 0.0
    btc_mcap = next((r["market_cap"] for r in coin_rows if r["coin"] == "BTC"), 0)
    btc_dom = btc_mcap / total_mcap * 100 if capped else 0.0

    df = pd.DataFrame(coins_series).sort_index()
    start, end = str(df.index[0].date()), str(df.index[-1].date())
    order = [r["coin"] for r in coin_rows if r["coin"] in df.columns]
    corr = df[order].pct_change().dropna().corr()
    avg_corr = float(corr.values[np.triu_indices_from(corr.values, k=1)].mean()) \
        if len(order) > 1 else 0.0

    # Market regime from BTC vs its ~10-week (70d) moving average.
    regime_on = True
    if "BTC" in df.columns:
        b = df["BTC"].dropna()
        if len(b) >= 40:
            regime_on = bool(b.iloc[-1] > b.rolling(min(70, len(b))).mean().iloc[-1])

    # Per-coin systematic signal (model output, NOT personal advice):
    #   risk-off -> everything to cash; else top-momentum uptrends = buy,
    #   other uptrends = hold, downtrends = avoid.
    K = 8
    for i, r in enumerate(coin_rows):      # coin_rows already sorted by 90d return
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

    # Top-3 movers per timeframe (7d/14d/28d/60d/6mo/12mo).
    field = {"7d": "chg7", "14d": "chg14", "28d": "chg28", "60d": "chg60",
             "6mo": "chg180", "12mo": "chg365"}
    movers = {}
    for label, _ in MOVER_HZ:
        f = field[label]
        ranked = sorted((c for c in coin_rows if c.get(f) is not None),
                        key=lambda c: c[f], reverse=True)
        movers[label] = [{"coin": c["coin"], "ret": round(c[f], 1)} for c in ranked[:3]]

    commodity_rows = fetch_commodities()      # gold + commodities, hot only

    os.makedirs("reports", exist_ok=True)
    with open(JSON_PATH, "w") as f:
        json.dump(dict(window_days=len(df), start=start, end=end, coins=coin_rows,
                       commodities=commodity_rows,
                       stables=stable_rows, avg_corr=avg_corr, cap_weighted_ret=cap_w,
                       equal_weighted_ret=eq_w, btc_dominance=btc_dom,
                       total_mcap_b=total_mcap / 1e9, regime_on=regime_on,
                       recommendation=recommendation, movers=movers,
                       source="coingecko"), f, indent=2)

    # Treemap
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
        plt.title(f"Crypto market map - box size = market cap, colour = {DAYS}-day return")
        plt.tight_layout(); plt.savefig("reports/crypto_map_treemap.png", dpi=130); plt.close()

    # Ranked returns
    plt.figure(figsize=(10, max(6, len(coin_rows) * 0.28)))
    names = [r["coin"] for r in coin_rows][::-1]
    vals = [r["ret"] for r in coin_rows][::-1]
    plt.barh(names, vals, color=["#16a34a" if v >= 0 else "#dc2626" for v in vals])
    plt.axvline(0, color="#888", lw=0.8)
    plt.title(f"Top coins by market cap - {DAYS}-day return %")
    plt.xlabel("Return %"); plt.tick_params(labelsize=8)
    plt.tight_layout(); plt.savefig("reports/crypto_map_returns.png", dpi=130); plt.close()

    # Stablecoin peg
    plt.figure(figsize=(11, 5))
    for c, s in stable_series.items():
        plt.plot(s.index, s, label=c, linewidth=1.4)
    plt.axhline(1.0, color="#111", ls="--", lw=0.9)
    plt.axhline(0.995, color="#d97706", ls=":", lw=0.9)
    plt.ylim(0.98, 1.012)
    plt.title(f"Stablecoin peg monitor - last {DAYS} days ($1.00 = peg)")
    plt.ylabel("Price (USD)"); plt.legend(ncol=6, fontsize=8, frameon=False)
    plt.tight_layout(); plt.savefig("reports/crypto_map_stablecoins.png", dpi=130); plt.close()

    # Correlation heatmap (top 24)
    sub = order[:24]
    if len(sub) > 1:
        cmat = df[sub].pct_change().dropna().corr()
        plt.figure(figsize=(9, 8))
        im = plt.imshow(cmat, cmap="RdYlGn", vmin=-1, vmax=1)
        plt.colorbar(im, fraction=0.046, pad=0.04, label="correlation")
        plt.xticks(range(len(sub)), sub, rotation=90, fontsize=7)
        plt.yticks(range(len(sub)), sub, fontsize=7)
        plt.title(f"Return correlations - last {DAYS} days (top {len(sub)})")
        plt.tight_layout(); plt.savefig("reports/crypto_map_correlation.png", dpi=130); plt.close()

    return dict(start=start, end=end, best=coin_rows[0], worst=coin_rows[-1],
                cap_w=cap_w, eq_w=eq_w, btc_dom=btc_dom, total=total_mcap / 1e9,
                avg_corr=avg_corr, n_coins=len(coin_rows), n_stables=len(stable_rows),
                watch=[r for r in stable_rows if r["status"] != "ok"])


def main():
    force = "--force" in sys.argv
    if not force and os.path.exists(JSON_PATH) and \
            time.time() - os.path.getmtime(JSON_PATH) < CACHE_TTL:
        print("crypto_map: cached data is fresh (<12h); use --force to refetch.")
        return

    print("crypto_map: fetching from CoinGecko (rate-limited, ~2 min)...")
    coins_series, coin_rows, stable_series, stable_rows = fetch_all()
    if not coin_rows:
        print("crypto_map: no data returned (rate limited?). Keeping previous cache.")
        return
    s = build(coins_series, coin_rows, stable_series, stable_rows)
    print(f"\nCoinGecko · {s['n_coins']} coins, {s['n_stables']} stablecoins · "
          f"{s['start']} -> {s['end']}")
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
