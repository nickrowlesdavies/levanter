#!/usr/bin/env python3
"""
Cross-sectional carry BASKET - the proper, textbook form of the carry trade.

Per-pair carry (tested earlier) is a diluted version. The real carry factor
is a portfolio: each month rank currencies by their interest rate, go long a
basket of the highest-yielders and short a basket of the lowest-yielders,
then rebalance. Diversifying across the whole cross-section is what gives
carry its historical risk-adjusted edge.

Our tradeable universe is 5 non-USD currencies, each expressed against USD:
    EUR, GBP, AUD  (direct: EURUSD etc = USD per unit)
    JPY, CHF       (inverse: 1 / USDJPY etc)
Each month we rank them by yield spread vs USD, long the top `k`, short the
bottom `k`, hold to the next month. P&L per leg = price move + carry roll,
minus a turnover cost. Fixed economic rule (rank by yield) - almost nothing
to overfit, so the full-sample result is already a fair test.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.data.loader import Instrument, load_candles
from src.data.rates import fetch_rate

START, END = "2010-01-01", "2024-12-31"
START_EQUITY = 10000.0
K = 3                       # long top-3, short bottom-3 of the 9 currencies
COST_BPS = 3.0              # per unit of turnover, round-trip (wider on NOK/SEK)

# currency -> (pair, inverse?) to build "value of 1 unit of ccy in USD".
# Expanded universe (9 non-USD currencies) for a wider carry cross-section.
CCY_PAIRS = {
    "EUR": ("EURUSD=X", False),
    "GBP": ("GBPUSD=X", False),
    "AUD": ("AUDUSD=X", False),
    "NZD": ("NZDUSD=X", False),
    "JPY": ("USDJPY=X", True),
    "CHF": ("USDCHF=X", True),
    "CAD": ("USDCAD=X", True),
    "NOK": ("USDNOK=X", True),
    "SEK": ("USDSEK=X", True),
}


def build_usd_values() -> pd.DataFrame:
    cols = {}
    for ccy, (sym, inv) in CCY_PAIRS.items():
        inst = Instrument(ccy, sym, 0.01 if "JPY" in sym else 0.0001, 1.0)
        px = load_candles(inst, START, END, "1d", source="yfinance")["close"]
        cols[ccy] = 1.0 / px if inv else px
    df = pd.DataFrame(cols).dropna()
    return df


def build_spreads(index) -> pd.DataFrame:
    usd = fetch_rate("USD")
    out = {}
    for ccy in CCY_PAIRS:
        r = fetch_rate(ccy)
        both = pd.concat([r.rename("c"), usd.rename("u")], axis=1).sort_index().ffill()
        out[ccy] = (both["c"] - both["u"]).dropna()
    spreads = pd.DataFrame(out).sort_index().ffill()
    idx = pd.DatetimeIndex(index)
    return spreads.reindex(spreads.index.union(idx)).ffill().reindex(idx)


def run_basket(k: int = K, cost_bps: float = COST_BPS) -> dict:
    usd_val = build_usd_values()
    spreads = build_spreads(usd_val.index)

    equity = START_EQUITY
    curve = [(usd_val.index[0], equity)]
    prev_w = pd.Series(0.0, index=list(CCY_PAIRS))
    monthly_returns = []

    # Rebalance on the last actual trading date of each month.
    reb_dates = pd.DatetimeIndex(
        usd_val.index.to_series().resample("ME").last().dropna().values
    )

    for i in range(len(reb_dates) - 1):
        t0, t1 = reb_dates[i], reb_dates[i + 1]
        s = spreads.loc[t0].dropna()
        if len(s) < 2 * k:
            continue
        ranked = s.sort_values(ascending=False)
        longs = ranked.index[:k]
        shorts = ranked.index[-k:]

        w = pd.Series(0.0, index=list(CCY_PAIRS))
        w[longs] = 1.0 / k
        w[shorts] = -1.0 / k

        # Turnover cost when weights change.
        turnover = (w - prev_w).abs().sum()
        cost = turnover * (cost_bps / 10000.0)
        prev_w = w

        days = max((t1 - t0).days, 1)
        leg_ret = 0.0
        for ccy in CCY_PAIRS:
            if w[ccy] == 0:
                continue
            price_ret = usd_val.loc[t1, ccy] / usd_val.loc[t0, ccy] - 1.0
            carry = (spreads.loc[t0, ccy] / 100.0) * (days / 365.25)
            leg_ret += w[ccy] * (price_ret + carry)

        period_ret = leg_ret - cost
        equity *= (1 + period_ret)
        monthly_returns.append(period_ret)
        curve.append((t1, equity))

    curve = pd.Series([e for _, e in curve],
                      index=pd.DatetimeIndex([d for d, _ in curve]))
    r = pd.Series(monthly_returns)

    years = (curve.index[-1] - curve.index[0]).days / 365.25
    total_ret = curve.iloc[-1] / START_EQUITY - 1
    cagr = (curve.iloc[-1] / START_EQUITY) ** (1 / years) - 1
    sharpe = (r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else np.nan
    dd = ((curve - curve.cummax()) / curve.cummax()).min()
    win = (r > 0).mean() * 100

    return {"curve": curve, "total_return_pct": total_ret * 100,
            "cagr_pct": cagr * 100, "sharpe": sharpe,
            "max_drawdown_pct": dd * 100, "monthly_win_pct": win,
            "months": len(r)}


def sub_period(curve: pd.Series, start: str) -> str:
    seg = curve[curve.index >= start]
    if len(seg) < 3:
        return "n/a"
    r = seg.pct_change().dropna()
    sh = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else float("nan")
    ret = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
    return f"return {ret:+.1f}%  Sharpe {sh:.2f}"


def main():
    print("\n" + "=" * 70)
    print(f" CROSS-SECTIONAL CARRY BASKET  (long top-{K} / short bottom-{K}, "
          f"monthly)")
    print(f" {len(CCY_PAIRS)} currencies vs USD, 2010-2024, roll + {COST_BPS}bps "
          f"turnover cost")
    print("=" * 70)
    res = run_basket()
    print(f" Total return : {res['total_return_pct']:+.1f}%   "
          f"CAGR {res['cagr_pct']:+.2f}%")
    print(f" Sharpe       : {res['sharpe']:.2f}")
    print(f" Max drawdown : {res['max_drawdown_pct']:.1f}%")
    print(f" Monthly win  : {res['monthly_win_pct']:.0f}%   over "
          f"{res['months']} months")
    print("-" * 70)
    print(f" 2018+ sub-period: {sub_period(res['curve'], '2018-01-01')}")
    print(f" 2022+ sub-period: {sub_period(res['curve'], '2022-01-01')}")
    print("=" * 70)

    plt.figure(figsize=(11, 6))
    norm = res["curve"] / res["curve"].iloc[0] * 100
    plt.plot(norm.index, norm.values, linewidth=1.5, color="#1f77b4",
             label=f"carry basket (k={K})")
    plt.axhline(100, color="grey", linestyle="--", linewidth=0.8)
    plt.title("Cross-sectional carry basket - equity (start=100)")
    plt.ylabel("Equity (indexed to 100)")
    plt.legend()
    plt.tight_layout()
    out = "reports/carry_basket.png"
    plt.savefig(out, dpi=130)
    print(f"\n Chart saved: {out}\n")


if __name__ == "__main__":
    main()
