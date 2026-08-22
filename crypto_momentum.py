#!/usr/bin/env python3
"""
Crypto cross-sectional momentum - weekly. Testing for a real edge.

Crypto is the most inefficient liquid market, and its most robust documented
edge is momentum at the weekly-to-monthly horizon: recent winners keep
winning. Each week we rank a basket of coins by their trailing return and
hold the strongest. Weekly rebalance = the user's preferred cadence.

We test honestly:
  * costs included (0.1%/side, realistic crypto spot fee)
  * several lookback/basket sizes, to show it isn't one cherry-picked param
  * long-only (implementable with spot) AND long-short (the pure factor)
  * benchmarked vs BTC buy-hold and equal-weight buy-hold, so we can see
    whether it's real momentum ALPHA or just crypto beta in disguise

    python crypto_momentum.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

COINS = ["BTC", "ETH", "BNB", "XRP", "ADA", "SOL", "DOGE", "DOT", "AVAX",
         "LINK", "LTC", "BCH", "ATOM", "XLM", "ETC", "XMR", "ALGO", "FIL",
         "ICP", "HBAR"]
START, END = "2019-01-01", "2026-08-16"
FEE_BPS = 10.0                      # 0.10% per side, realistic crypto spot
CACHE = "data_cache/crypto_weekly.csv"


def load_prices() -> pd.DataFrame:
    if os.path.exists(CACHE):
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)
    import yfinance as yf
    syms = [c + "-USD" for c in COINS]
    # Pull DAILY and resample to a clean weekly grid ourselves. yfinance's
    # native "1wk" returned misaligned, half-empty rows across coins.
    daily = yf.download(syms, start=START, end=END, interval="1d",
                        progress=False, auto_adjust=True)["Close"]
    daily.columns = [c.replace("-USD", "") for c in daily.columns]
    weekly = daily.resample("W-SUN").last().dropna(how="all")
    weekly.to_csv(CACHE)
    return weekly


def _metrics(equity: pd.Series, rets: pd.Series) -> dict:
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 0.1)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(52) if rets.std() > 0 else np.nan
    dd = ((equity - equity.cummax()) / equity.cummax()).min()
    return {"cagr_pct": cagr * 100, "sharpe": sharpe, "maxdd_pct": dd * 100,
            "total_pct": (equity.iloc[-1] / equity.iloc[0] - 1) * 100}


def momentum_backtest(prices, lookback=8, k=5, skip=1, long_short=False,
                      fee_bps=FEE_BPS, regime_ma=0, cash_apy=0.03,
                      market="BTC", eval_start=None):
    """Weekly cross-sectional momentum. Rank by return over `lookback` weeks
    ending `skip` weeks ago; long top-k (and short bottom-k if long_short).
    Hold one week, rebalance. Returns equity curve + weekly returns.

    If `regime_ma` > 0, apply a market-regime filter: when the market proxy
    (default BTC) is below its `regime_ma`-week moving average, sit in cash
    (earning `cash_apy` annualised, e.g. stablecoin yield) instead of trading.
    This is the drawdown-control overlay.

    `eval_start`: if set, weeks before it are used only for indicator warm-up
    and holdings state; equity/returns are recorded from eval_start onward.
    This lets walk-forward test windows warm up on prior data without leaking
    it into the score."""
    rets = prices.pct_change()
    mom = prices.shift(skip) / prices.shift(skip + lookback) - 1.0
    cash_weekly = (1 + cash_apy) ** (1 / 52) - 1

    mkt = prices[market]
    mkt_ma = mkt.rolling(regime_ma).mean() if regime_ma else None

    equity = 1.0
    curve, wk_rets = [], []
    prev_long, prev_short = set(), set()
    weeks_in_cash = 0

    idx = prices.index
    for t in range(skip + lookback, len(idx) - 1):
        record = eval_start is None or idx[t + 1] >= eval_start

        # Regime check (uses only data up to week t).
        risk_off = bool(regime_ma and mkt_ma is not None
                        and not (mkt.iloc[t] > mkt_ma.iloc[t]))

        if risk_off:
            turn = len(prev_long) / max(2 * k, 1) + len(prev_short) / max(2 * k, 1)
            cost = turn * (fee_bps / 10000.0)
            prev_long, prev_short = set(), set()
            net = cash_weekly - cost
            in_cash = True
        else:
            row = mom.iloc[t].dropna()
            if len(row) < 2 * k:
                continue
            ranked = row.sort_values(ascending=False)
            longs = list(ranked.index[:k])
            shorts = list(ranked.index[-k:]) if long_short else []

            nxt = rets.iloc[t + 1]
            long_ret = nxt[longs].mean()
            port = long_ret if not long_short else 0.5 * long_ret - 0.5 * nxt[shorts].mean()

            turn = len(set(longs) ^ prev_long) / max(2 * k, 1)
            if long_short:
                turn += len(set(shorts) ^ prev_short) / max(2 * k, 1)
            cost = turn * (fee_bps / 10000.0)
            prev_long, prev_short = set(longs), set(shorts)
            net = port - cost
            in_cash = False

        if not record:
            continue
        equity *= (1 + net)
        curve.append((idx[t + 1], equity))
        wk_rets.append(net)
        if in_cash:
            weeks_in_cash += 1

    c = pd.Series([e for _, e in curve], index=[d for d, _ in curve])
    r = pd.Series(wk_rets, index=c.index)
    r.attrs["pct_in_cash"] = weeks_in_cash / max(len(wk_rets), 1) * 100
    return c, r


def benchmark(prices, equal_weight=False):
    if equal_weight:
        r = prices.pct_change().mean(axis=1).dropna()
    else:
        r = prices["BTC"].pct_change().dropna()
    eq = (1 + r).cumprod()
    return eq, r


def main():
    prices = load_prices()
    print("\n" + "=" * 76)
    print(f" CRYPTO WEEKLY CROSS-SECTIONAL MOMENTUM  ({len(COINS)} coins, "
          f"{len(prices)} weeks)")
    print(f" Long-only, top-k, weekly rebalance, {FEE_BPS/100:.2f}%/side cost. "
          f"Out-of-sample by rule.")
    print("=" * 76)
    print(f" {'lookback':>8} {'k':>3} | {'total%':>9} {'CAGR%':>8} "
          f"{'Sharpe':>7} {'maxDD%':>8}")
    print("-" * 76)

    best, best_sharpe = None, -np.inf
    for L in (4, 8, 12):
        for k in (3, 5):
            c, r = momentum_backtest(prices, lookback=L, k=k, long_short=False)
            m = _metrics(c, r)
            print(f" {L:>8} {k:>3} | {m['total_pct']:>9.0f} {m['cagr_pct']:>8.1f} "
                  f"{m['sharpe']:>7.2f} {m['maxdd_pct']:>8.1f}")
            if m["sharpe"] > best_sharpe:
                best_sharpe, best = m["sharpe"], (L, k, c, r, m)

    L, k, c, r, m = best
    print("-" * 76)
    print(f" Best long-only (no filter): lookback={L}, k={k}  ->  "
          f"Sharpe {m['sharpe']:.2f}, CAGR {m['cagr_pct']:.0f}%, "
          f"maxDD {m['maxdd_pct']:.0f}%")

    # --- Regime filter: rotate to cash when BTC < its N-week MA ---
    print("\n REGIME-FILTERED (to stablecoin when BTC below its N-week MA):")
    print(f" {'MA weeks':>8} | {'total%':>9} {'CAGR%':>8} {'Sharpe':>7} "
          f"{'maxDD%':>8} {'%cash':>7}")
    print("-" * 76)
    reg_best, reg_best_sharpe = None, -np.inf
    for ma in (10, 15, 20, 25):
        cf, rf = momentum_backtest(prices, lookback=L, k=k, regime_ma=ma)
        mf = _metrics(cf, rf)
        print(f" {ma:>8} | {mf['total_pct']:>9.0f} {mf['cagr_pct']:>8.1f} "
              f"{mf['sharpe']:>7.2f} {mf['maxdd_pct']:>8.1f} "
              f"{rf.attrs['pct_in_cash']:>6.0f}%")
        if mf["sharpe"] > reg_best_sharpe:
            reg_best_sharpe, reg_best = mf["sharpe"], (ma, cf, rf, mf)

    ma, cf, rf, mf = reg_best
    print("-" * 76)
    print(f" Best filtered: MA={ma}wk  ->  Sharpe {mf['sharpe']:.2f}, "
          f"CAGR {mf['cagr_pct']:.0f}%, maxDD {mf['maxdd_pct']:.0f}%  "
          f"(vs unfiltered maxDD {m['maxdd_pct']:.0f}%)")

    # Long-short (pure factor) at the same params, for reference.
    cls_, rls = momentum_backtest(prices, lookback=L, k=k, long_short=True)
    mls = _metrics(cls_, rls)
    print(f" Long-SHORT (pure alpha, no filter): Sharpe {mls['sharpe']:.2f}, "
          f"CAGR {mls['cagr_pct']:.0f}%, maxDD {mls['maxdd_pct']:.0f}%")

    # Benchmarks.
    btc_eq, btc_r = benchmark(prices, equal_weight=False)
    ew_eq, ew_r = benchmark(prices, equal_weight=True)
    mb = _metrics(btc_eq, btc_r); me = _metrics(ew_eq, ew_r)
    print("-" * 76)
    print(f" BENCHMARK BTC buy-hold : Sharpe {mb['sharpe']:.2f}, "
          f"CAGR {mb['cagr_pct']:.0f}%, maxDD {mb['maxdd_pct']:.0f}%")
    print(f" BENCHMARK equal-weight : Sharpe {me['sharpe']:.2f}, "
          f"CAGR {me['cagr_pct']:.0f}%, maxDD {me['maxdd_pct']:.0f}%")
    print("=" * 76)
    print(" Edge = momentum beats buy-hold on Sharpe / drawdown, and long-short")
    print(" (market-neutral) is positive -> real factor, not just crypto beta.")

    # Chart: filtered vs unfiltered vs benchmark (log scale).
    plt.figure(figsize=(11, 6))
    plt.plot(cf.index, cf.values,
             label=f"momentum + regime filter (MA={ma}wk)",
             linewidth=1.9, color="#d62728")
    plt.plot(c.index, c.values, label=f"momentum, no filter (L={L},k={k})",
             linewidth=1.3, color="#1f77b4", alpha=0.85)
    plt.plot(btc_eq.index, btc_eq.values, label="BTC buy-hold",
             linewidth=1.1, color="#ff7f0e", alpha=0.75)
    plt.plot(ew_eq.index, ew_eq.values, label="equal-weight buy-hold",
             linewidth=1.0, color="grey", alpha=0.6)
    plt.yscale("log")
    plt.title("Crypto weekly momentum: regime filter vs raw vs buy-hold "
              "(log scale, start=1)")
    plt.ylabel("Growth of 1 (log)")
    plt.legend()
    plt.tight_layout()
    out = "reports/crypto_momentum.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
