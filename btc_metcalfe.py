#!/usr/bin/env python3
"""BTC network-value gauge (long-horizon adoption model).

WHAT THIS IS: a long-horizon VALUATION CONTEXT gauge, not a trading signal.

We tested two network-value ideas on free public data:

  1. Metcalfe's Law on active addresses (Timothy Peterson's 2018 model):
     market value proportional to active-addresses^k. This HELD until ~2018 but
     has since DECOUPLED. Fit on 2019-onward data gives a negative slope and
     ~zero R2: addresses stayed roughly flat while price multiplied (exchange
     batching, L2, and post-ETF custody remove real users from on-chain counts).
     We keep it only as a diagnostic and clearly flag that it no longer works.

  2. Power-law adoption model (price vs network age on log-log). This is the
     family Peterson's "Lowest Price Forward" floor belongs to. It still fits
     strongly (R2 ~0.96) and yields a defensible fair value and an adoption
     floor. This is the gauge we surface.

Honest caveats we always show: the power law is a curve fit to price over time
with no hard economic mechanism, a long-run log-log fit flatters R2, it cannot
call tops, and "the floor has always held" is not a guarantee. Educational,
not financial advice.

Data: blockchain.info public charts API (no key). Writes reports/btc_metcalfe.json
and reports/btc_metcalfe.png. Run standalone to print the current read.
"""
import json
import os
import math
import datetime as dt

import numpy as np
import requests

R = "reports"
BASE = "https://api.blockchain.info/charts"
UA = {"User-Agent": "Levanter/1.0 (market-intelligence)"}
GENESIS = dt.date(2009, 1, 3)


def _chart(name, timespan="16years"):
    url = f"{BASE}/{name}?timespan={timespan}&format=json&sampled=false"
    r = requests.get(url, headers=UA, timeout=90)
    r.raise_for_status()
    out = {}
    for p in r.json().get("values", []):
        d = dt.datetime.utcfromtimestamp(int(p["x"])).strftime("%Y-%m-%d")
        out[d] = float(p["y"])
    return out


def _loglog_fit(x, y):
    lx, ly = np.log(x), np.log(y)
    k, a = np.polyfit(lx, ly, 1)
    resid = ly - (a + k * lx)
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((ly - ly.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    return a, k, r2, resid


def main():
    print("Fetching blockchain.info charts (price, active addresses, market cap)...")
    price = _chart("market-price")
    addr = _chart("n-unique-addresses")
    cap = _chart("market-cap")

    # --- Power-law adoption model: price vs network age (the usable gauge) ---
    rows = []
    for d in sorted(price):
        if price[d] <= 0:
            continue
        age = (dt.datetime.strptime(d, "%Y-%m-%d").date() - GENESIS).days
        if age < 200:
            continue
        rows.append((d, age, price[d]))
    if len(rows) < 1000:
        raise SystemExit("not enough price history (%d)" % len(rows))
    ds = [r[0] for r in rows]
    AGE = np.array([r[1] for r in rows], float)
    P = np.array([r[2] for r in rows])
    a, k, r2, resid = _loglog_fit(AGE, P)
    q05, q95 = float(np.percentile(resid, 5)), float(np.percentile(resid, 95))

    d_now, age_now, p_now = rows[-1]
    fair = math.exp(a + k * math.log(age_now))
    floor = math.exp(a + k * math.log(age_now) + q05)
    top = math.exp(a + k * math.log(age_now) + q95)
    over_under = p_now / fair - 1.0
    lo, hi = math.log(floor), math.log(top)
    pos = max(0.0, min(100.0, (math.log(p_now) - lo) / (hi - lo) * 100)) if hi > lo else 50.0

    if over_under <= -0.20:
        read = "cheap vs its long-term adoption trend"
    elif over_under < 0.20:
        read = "near its long-term adoption trend"
    elif over_under < 0.75:
        read = "rich vs its long-term adoption trend"
    else:
        read = "stretched well above its long-term adoption trend"

    # --- Metcalfe diagnostic: has active-address value held? (recent window) ---
    mrows = []
    for d in sorted(set(addr) & set(cap)):
        if d >= "2019-01-01" and addr[d] > 0 and cap[d] > 0:
            mrows.append((addr[d], cap[d]))
    metcalfe = None
    if len(mrows) > 300:
        mA = np.array([r[0] for r in mrows])
        mC = np.array([r[1] for r in mrows])
        _, mk, mr2, _ = _loglog_fit(mA, mC)
        metcalfe = {
            "window_from": "2019-01-01",
            "exponent_k": round(float(mk), 2),
            "r2": round(float(mr2), 3),
            "status": ("decoupled: slope is negative / R2 near zero, so active "
                       "addresses no longer explain price. Not used as a gauge."),
        }

    out = {
        "as_of": d_now,
        "model": "power-law adoption (price vs network age); Peterson LPF family",
        "price": round(p_now, 2),
        "fair_value": round(fair, 2),
        "floor": round(floor, 2),
        "frothy_top": round(top, 2),
        "over_under_pct": round(over_under * 100, 1),
        "band_position": round(pos, 1),
        "read": read,
        "power_law_exponent_k": round(float(k), 2),
        "r2": round(float(r2), 3),
        "n_days": len(rows),
        "history_from": ds[0],
        "metcalfe_diagnostic": metcalfe,
        "caveat": ("Long-horizon valuation context, not a trading signal. The power "
                   "law is a fit to price over time with no hard economic mechanism, "
                   "log-log flatters the fit, it cannot call tops, and a floor that has "
                   "always held is not a guarantee. Educational, not advice."),
    }
    os.makedirs(R, exist_ok=True)
    with open(os.path.join(R, "btc_metcalfe.json"), "w") as f:
        json.dump(out, f, indent=2)

    # --- Chart: price vs fair value vs floor (log scale) ---
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fair_s = np.exp(a + k * np.log(AGE))
        floor_s = np.exp(a + k * np.log(AGE) + q05)
        xs = [dt.datetime.strptime(d, "%Y-%m-%d") for d in ds]
        fig, ax = plt.subplots(figsize=(11, 5.2))
        ax.set_yscale("log")
        ax.plot(xs, P, lw=1.4, color="#3b82f6", label="BTC price")
        ax.plot(xs, fair_s, lw=1.7, color="#f59e0b", label="Adoption fair value")
        ax.plot(xs, floor_s, lw=1.2, color="#10b981", ls="--", label="Adoption floor (95%)")
        ax.scatter([xs[-1]], [p_now], color="#3b82f6", zorder=5, s=28)
        ax.set_title("Bitcoin vs long-term adoption fair value (power law)",
                     fontsize=13, fontweight="bold")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
        ax.grid(True, which="both", alpha=0.15)
        fig.tight_layout()
        fig.savefig(os.path.join(R, "btc_metcalfe.png"), dpi=140)
        plt.close(fig)
    except Exception as e:
        print("chart skipped:", e)

    print("\n=== BTC network-value gauge (%s) ===" % d_now)
    print("Price:           $%s" % f"{p_now:,.0f}")
    print("Fair value:      $%s   (%+.0f%%, %s)" % (f"{fair:,.0f}", over_under * 100, read))
    print("Adoption floor:  $%s   (95%% of history above)" % f"{floor:,.0f}")
    print("Frothy top:      $%s" % f"{top:,.0f}")
    print("Band position:   %.0f / 100  (0=floor, 100=frothy)" % pos)
    print("Power law:       k=%.2f, R2=%.3f, %d days from %s" % (k, r2, len(rows), ds[0]))
    if metcalfe:
        print("Metcalfe check:  k=%.2f R2=%.3f since 2019 -> DECOUPLED, not used"
              % (metcalfe["exponent_k"], metcalfe["r2"]))
    return out


if __name__ == "__main__":
    main()
