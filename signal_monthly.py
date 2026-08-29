#!/usr/bin/env python3
"""Levanter monthly Signal generator (premium note).

The monthly counterpart to signal_note.py. Where the free monthly review on the
site is a trailing-30-day read written on the 28th, this is the accountable
subscriber note published on the 1st, covering the month that has just closed:
what actually changed month on month, the thirty-day volatility map, the levels
worth watching, and a claim we score in the next issue.

PREMIUM. Written to reports/signals/ and never copied to the public site.

    python signal_monthly.py [--force] [--month YYYY-MM]

A note on the month figures. The maps store a usable daily history for FX and
commodities, but the crypto `hist` array is CoinGecko's 7-day hourly sparkline,
so a true month-end-to-month-end crypto return cannot be reconstructed from the
stored data. Rather than label a trailing-30-day number as the calendar month,
this script snapshots every close price each time it runs and computes exact
month-on-month returns from those snapshots. The first issue has no prior
snapshot, so it falls back to the trailing window and says so in the text.

Voice rules: no em dashes, no AI kill-words. Educational, not advice.
"""
import datetime as dt
import json
import os
import sys

import signal_note as sn

OUT = sn.OUT
SIGNAL_FREE = sn.SIGNAL_FREE
STATE = "signal_monthly_history.json"   # not *_state.json, which .gitignore excludes


def _load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save_state(d):
    json.dump(d, open(STATE, "w"), indent=2)


def _snapshot_is_fresh(snap, month, tol_days=5):
    """A snapshot is only usable for exact month maths if it was captured at the
    boundary it claims. If a monthly run is missed, the previous snapshot is weeks
    stale and differencing against it would span the wrong period while still
    reading as exact. Rather than quietly mislabel, fall back to the trailing
    window when the capture date is not close to the start of `month`."""
    cap = (snap or {}).get("captured")
    if not cap:
        return False
    try:
        d = dt.date.fromisoformat(cap[:10])
    except ValueError:
        return False
    boundary = dt.date(int(month[:4]), int(month[5:]), 1)
    return abs((d - boundary).days) <= tol_days


def _prev_month(m):
    y, mm = int(m[:4]), int(m[5:])
    return f"{y - 1}-12" if mm == 1 else f"{y}-{mm - 1:02d}"


def _month_name(m):
    return dt.date(int(m[:4]), int(m[5:]), 1).strftime("%B %Y")


METALS = ("gold", "silver", "platinum", "palladium", "copper")


def _pretty(sym):
    """NAMES where we have one, otherwise the symbol lowercased, so prose never
    mixes 'gold, silver' with 'COFFEE, GASOLINE'."""
    nm = sn._name(sym)
    return nm if nm != sym else sym.lower()


def _turb_txt(items, limit=4):
    """The turbulent roster runs to a dozen names in a broad month. Naming them
    all three times reads as padding, so name a few and count the rest."""
    if not items:
        return ""
    if len(items) <= limit:
        return sn._join(items)
    # Plain commas here: sn._join would add its own "and" before the last name and
    # the sentence would read "palladium and Brent crude and 5 others".
    return ", ".join(items[:limit]) + f" and {len(items) - limit} others"


def _vol_groups(vr, horizon="30d"):
    """{class: (turbulent, calm)} at the given horizon. The weekly Signal's helper
    is hard-wired to 7d; the monthly note reads the thirty-day classification."""
    cls, assets = vr.get("classes", {}), vr.get("assets", {})
    out = {"crypto": ([], []), "fx": ([], []), "commodity": ([], [])}
    for sym, c in cls.items():
        if c not in out:
            continue
        r = assets.get(sym, {}).get(horizon, {})
        if not r:
            continue
        nm = sym if c == "fx" else _pretty(sym)
        (out[c][0] if r.get("regime") == "HIGH" else out[c][1]).append(nm)
    return out


def _prices(cm, fxm, com):
    """Current close price per symbol, by class."""
    return {
        "crypto": {r["coin"]: r.get("price") for r in cm.get("coins", []) if r.get("price")},
        "fx": {r["pair"]: r.get("price") for r in fxm.get("pairs", []) if r.get("price")},
        "comd": {r["name"]: r.get("price") for r in com.get("items", []) if r.get("price")},
    }


def _returns(cur_px, prev_px, cm, fxm, com):
    """Month returns per class as [(symbol, pct)], plus the basis actually used.

    Exact month-on-month wherever a prior month-end snapshot exists for that
    symbol. Otherwise the map's trailing-30-day field, and the basis says so, so
    the copy can never call a trailing window a calendar month.
    """
    fallback = {
        "crypto": {r["coin"]: r.get("chg30") for r in cm.get("coins", [])},
        "fx": {r["pair"]: r.get("chg30") for r in fxm.get("pairs", [])},
        "comd": {r["name"]: r.get("chg30") for r in com.get("items", [])},
    }
    out, exact_any, fell_back_any = {}, False, False
    for cls, cur in cur_px.items():
        prev = (prev_px or {}).get(cls, {})
        rows = []
        for sym, px in cur.items():
            p0 = prev.get(sym)
            if p0 and px:
                rows.append((sym, (px / p0 - 1.0) * 100.0))
                exact_any = True
            else:
                v = fallback.get(cls, {}).get(sym)
                if v is not None:
                    rows.append((sym, float(v)))
                    fell_back_any = True
        out[cls] = sorted(rows, key=lambda kv: kv[1], reverse=True)
    basis = "exact" if (exact_any and not fell_back_any) else ("mixed" if exact_any else "trailing")
    return out, basis


def _stats(rows):
    if not rows:
        return None
    vals = [v for _, v in rows]
    return {"n": len(rows), "up": sum(1 for v in vals if v > 0),
            "avg": sum(vals) / len(vals), "top": rows[:3], "bot": rows[-3:][::-1]}


def _moves(rows):
    return sn._join([f"{s} {v:+.1f} percent" for s, v in rows])


def compose(launch, month, rets, basis, cur_state, prev_state):
    cm, fxm = sn._read("crypto_map.json"), sn._read("fx_map.json")
    com, vr = sn._read("commodities_map.json"), sn._read("vol_regime.json")
    cg, nv = sn._read("cycle_gauge.json"), sn._read("btc_metcalfe.json")
    dbt = sn._read_root("direction_backtest.json")

    price, fair, floor = nv.get("price"), nv.get("fair_value"), nv.get("floor")
    ou = nv.get("pct_vs_fair")
    if ou is None and price and fair:
        ou = (price / fair - 1.0) * 100.0
    cyc_b = next((round(a.get("pct_vs_trend", 0)) for a in cg.get("assets", [])
                  if a.get("sym") == "BTC"), None)
    phase = next((a.get("phase", "") for a in cg.get("assets", [])
                  if a.get("sym") == "BTC"), "")
    dom = cm.get("btc_dominance")
    corr = cm.get("avg_corr")

    g = _vol_groups(vr, "30d")
    turbulent = list(g["crypto"][0]) + list(g["commodity"][0]) + list(g["fx"][0])
    bt = vr.get("backtest", {}) or {}
    b30, b90 = bt.get("30d", {}) or {}, bt.get("90d", {}) or {}
    mname = _month_name(month)
    now = sn._now_gst()
    stamp = now.strftime("%H:%M GST on %-d %B %Y")

    # How the month's figures were actually derived, said plainly rather than implied.
    if basis == "exact":
        span = (f"**{mname}**, measured from the last day of the prior month to the last day of "
                f"this one")
    elif basis == "mixed":
        span = (f"**{mname}**, measured last day to last day where we hold a prior close and on a "
                f"trailing thirty-day window otherwise")
    else:
        span = (f"the **thirty days to {now:%-d %B %Y}**, which is close to {mname} but is not the "
                f"calendar month")

    P = ["# Levanter monthly Signal", ""]
    if launch:
        P += ["> **The Levanter monthly Signal.** A deeper monthly read of volatility, valuation and "
              "positioning across crypto, FX and commodities. This is the subscriber tier, and it is "
              "free while we build the list. We will tell you before that changes. Subscribe at "
              "read.levantermarkets.com.", ""]
    P += [f"*Data captured at {stamp}. Figures cover {span}. This is the accountable read behind the "
          f"free monthly review: what changed since the last issue, the levels to watch, and a claim "
          f"we score next month.*", "", "---", ""]
    P += ["> **Editor's line (add before publishing, then delete this prompt):** one sentence of your "
          "own read of the month. What it changes about how you are positioned, or the single thing "
          "you would tell a friend who asked. This is the line the model cannot write.", ""]

    if basis == "trailing":
        P += ["## A note on this first issue", "",
              "We compute month figures by comparing the close we stored on the last day of last month "
              "with the close we store today. This is the first issue, so there is no stored prior "
              "close and the numbers below use a trailing thirty-day window instead. From next month "
              "the figures are exact month on month, and this section disappears.", ""]

    # ===== The month behind =====
    P += [f"## {mname}, by asset class", ""]
    label = {"crypto": "Crypto", "fx": "Foreign exchange", "comd": "Commodities"}
    for cls in ("crypto", "fx", "comd"):
        st = _stats(rets.get(cls, []))
        if not st:
            P.append(f"{label[cls]} data did not return from the feed for this issue, so the class is "
                     f"not covered here. It resumes in the next issue.")
            P.append("")
            continue
        P.append(
            f"**{label[cls]}.** {st['up']} of {st['n']} higher, average {st['avg']:+.1f} percent. "
            f"Strongest: {_moves(st['top'])}. Weakest: {_moves(st['bot'])}.")
        P.append("")

    # ===== Valuation =====
    if fair:
        P += ["## The one chart: bitcoin against its long-run trend", ""]
        P.append(
            f"Bitcoin is near {sn._kfmt(price)} dollars. The **valuation fit** models price against "
            f"how long the network has existed, on a log-log scale. Fair value on that fit lands near "
            f"{sn._kfmt(fair)}, about {abs(ou):.0f} percent "
            f"{'below' if ou < 0 else 'above'} the line, and the fitted floor sits near "
            f"{sn._kfmt(floor)}. Bitcoin has closed above that floor for roughly 95 percent of the "
            f"historical sample. That is an in-sample observation, not a tested probability and not a "
            f"guaranteed level of support.")
        P.append("")
        if cyc_b is not None:
            P.append(
                f"Our **cycle gauge** reports a second number. It fits the same shape of curve, price "
                f"against network age, but on a different price history and with a different band, "
                f"then adds halving timing to classify the phase. It reads bitcoin as {phase.lower()}, "
                f"about {abs(cyc_b):.0f} percent below its own trend line. Do not read the two figures "
                f"as confirming each other. They are the same kind of fit run over overlapping data, "
                f"so close agreement is close to guaranteed and tells you nothing the first number did "
                f"not. On a monthly horizon this is the number that matters most, because valuation "
                f"says far more about a year than about a week.")
            P.append("")

    P += ["## What the model can and cannot do", ""]
    P.append(
        "It is a statistical fit of price to time. It has no hard economic mechanism behind it, cannot "
        "call tops, and may fail outside the historical sample. It is a valuation anchor rather than a "
        "timing tool. Treat the fair value and the floor as distant reference points, never as targets "
        "and never as a reason to size up.")
    P.append("")

    # ===== Volatility =====
    P += ["## The thirty-day volatility map", ""]
    if b30.get("acc"):
        ci = b30.get("ci") or sn._wilson_ci(b30.get("acc"), b30.get("n"))
        ci_txt = f", 95 percent interval {ci[0]} to {ci[1]}" if ci else ""
        P.append(
            f"This is the part with measurable skill. The model tags each market turbulent or calm for "
            f"the month ahead. In the point-in-time backtest it classified the thirty-day regime "
            f"correctly about {b30['acc']} percent of the time across {b30.get('n')} calls"
            f"{ci_txt}, {b30.get('edge')} points above its naive baseline"
            + (f", and {b90['acc']} percent at ninety days." if b90.get("acc") else ".")
            + " That is a backtest rather than a live forward record, and the live scoreboard is only "
              "now filling.")
        P.append("")
    if vr.get("ood"):
        P.append("The model also flags that current conditions sit outside the range it was fitted on, "
                 "so treat this month's classifications with more caution than usual.")
        P.append("")
    P.append(
        (f"For the month ahead it reads {_turb_txt(turbulent, 6)} as turbulent and the rest of the "
         f"board as calm." if turbulent else
         "For the month ahead it reads the whole board as calm, which is itself worth noting.")
        + (f" Average cross-asset correlation is near {corr:.2f}, so diversification is "
           f"{'thin' if corr > 0.5 else 'doing real work'}." if corr else ""))
    P.append("")

    # ===== What changed =====
    P += ["## What changed since the last monthly Signal", ""]
    if prev_state:
        prev_high = set(prev_state.get("high", []))
        flips = [h for h in turbulent if h not in prev_high]
        calmed = [h for h in prev_high if h not in turbulent]
        d_ou = (round(ou) - prev_state["btc_ou"]) if (ou is not None
                                                      and prev_state.get("btc_ou") is not None) else None
        bits = []
        if flips:
            bits.append(f"newly turbulent, {sn._join(flips)}")
        if calmed:
            bits.append(f"calmed back to normal, {sn._join(calmed)}")
        if not flips and not calmed:
            bits.append("the volatility roster is unchanged from last month")
        if d_ou:
            bits.append(f"bitcoin is about {abs(d_ou)} points "
                        f"{'cheaper' if d_ou < 0 else 'richer'} against its fitted value")
        P.append("Month on month: " + sn._sentences([sn._cap(b) for b in bits]) + ".")
    else:
        P.append(
            "From next month this section flags which markets newly flipped turbulent or calm and how "
            "far bitcoin moved against its fitted value, so you can see what changed rather than only "
            "the latest state.")
    P.append("")

    # ===== Watchlist =====
    P += ["## Subscriber watchlist, with levels", ""]
    ve = sn._voldetail(vr, "ETH")
    bullets = [
        (f"- **Bitcoin.** Fitted floor near {sn._kfmt(floor)}, fair value near {sn._kfmt(fair)}. A "
         f"monthly close below the fitted floor would be historically unusual and would challenge the "
         f"model, rather than automatically creating a buying opportunity.") if fair else "",
        (f"- **Ether volatility.** Annualised volatility is near {ve['now']} percent against a "
         f"historical median around {ve['med']}. The thirty-day classification currently reads "
         f"{str(ve['reg30']).lower()}.") if ve else "",
        (f"- **The metals.** Whether the turbulent bid broadens beyond "
         f"{sn._join([m for m in g['commodity'][0] if m in METALS])} or fades back to calm."
         ) if [m for m in g["commodity"][0] if m in METALS] else "",
        (f"- **Pegs and dominance.** Bitcoin dominance is near {dom:.0f} percent and the stablecoins "
         f"we track are holding. A tracked peg below 0.995 would trigger Levanter's wobble alert."
         ) if dom else "",
    ]
    P += [b for b in bullets if b]
    P.append("")
    P.append(
        (f"To score next month: the model calls {_turb_txt(turbulent, 4)} turbulent and the rest calm. In "
         f"the next issue we score each call the way the model does, whether realised volatility over "
         f"the month came in above or below the asset's running-median volatility, and show the hits "
         f"and the misses. That is the claim you can hold this Signal to."
         ) if turbulent else
        "To score next month: the model calls the whole board calm. We score that the same way in the "
        "next issue and show where it was wrong.")
    P.append("")

    n, dacc = dbt.get("n"), dbt.get("accuracy")
    if dacc:
        P.append(
            f"One honesty line to close. Across {n} scored direction calls our accuracy is about "
            f"{dacc} percent, which is close to a coin flip and exactly what the research says to "
            f"expect. We publish it because the number is the point. Volatility is forecastable and we "
            f"forecast it. Direction is not, so we do not sell it.")
        P.append("")

    P += ["---", ""]
    if launch:
        P.append("*This is the Levanter monthly Signal, the subscriber note, free for now while we "
                 "build the list. We will tell you before that changes. Subscribe at "
                 "read.levantermarkets.com. The daily, weekly and monthly reviews stay free at "
                 "levantermarkets.com. Educational market analysis, not financial advice.*")
    else:
        P.append("*This is the Levanter monthly Signal, the subscriber note. Subscribe at "
                 "read.levantermarkets.com. The daily, weekly and monthly reviews stay free at "
                 "levantermarkets.com. Educational market analysis, not financial advice.*")

    meta = {"month": month, "mname": mname, "turbulent": turbulent, "rets": rets,
            "basis": basis, "ou": ou, "dom": dom, "acc30": b30.get("acc"), "dacc": dacc}
    return "\n".join(P).rstrip() + "\n", meta


def teaser(meta, hashtags=True):
    m = meta
    T = [f"Levanter monthly Signal, {m['mname']}.", ""]
    st = _stats(m["rets"].get("crypto", []))
    if st:
        T += [f"Crypto: {st['up']} of {st['n']} higher, average {st['avg']:+.1f} percent. "
              f"Strongest {_moves(st['top'][:1])}.", ""]
    if m["turbulent"]:
        T += [f"For the month ahead the model reads {_turb_txt(m['turbulent'], 5)} as turbulent and "
              f"the rest of the board as calm. We score every one of those calls in the next issue.", ""]
    if m.get("acc30"):
        T += [f"The thirty-day volatility classifier runs about {m['acc30']} percent in backtest. Our "
              f"direction calls run near a coin flip, and we publish that too.", ""]
    T += ["The full monthly Signal, with the levels and the month-on-month changes, is for "
          "subscribers: read.levantermarkets.com", ""]
    T += ["Educational, not advice."]
    if hashtags:
        T += ["", "#markets #crypto #volatility #macro"]
    return "\n".join(T).rstrip() + "\n"


def main():
    argv = sys.argv[1:]
    force = "--force" in argv
    now = sn._now_gst()
    # Runs on the last day of the month, so the month being covered is this one.
    month = now.strftime("%Y-%m")
    if "--month" in argv:
        month = argv[argv.index("--month") + 1]

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "docx"), exist_ok=True)
    note_path = os.path.join(OUT, f"levanter-signal-monthly-{month}.md")
    li_path = os.path.join(OUT, f"levanter-signal-monthly-teaser-{month}.md")
    sub_path = os.path.join(OUT, f"levanter-signal-monthly-teaser-substack-{month}.md")

    if not force:
        if os.path.exists(note_path):
            print(f"signal_monthly: {month} Signal already prepared; skipping.")
            return
        tomorrow = (now + dt.timedelta(days=1)).date()
        if tomorrow.day != 1:
            print(f"signal_monthly: {now:%-d %B} is not the last day of the month; skipping.")
            return

    cm, fxm = sn._read("crypto_map.json"), sn._read("fx_map.json")
    com, vr = sn._read("commodities_map.json"), sn._read("vol_regime.json")
    nv = sn._read("btc_metcalfe.json")
    if not (cm.get("coins") or fxm.get("pairs") or com.get("items")):
        print("signal_monthly: no market data available; nothing written.")
        return

    state = _load_state()
    prev_state = state.get(_prev_month(month))
    if prev_state and not _snapshot_is_fresh(prev_state, month):
        print(f"signal_monthly: prior snapshot for {_prev_month(month)} was captured "
              f"{prev_state.get('captured', 'unknown')}, too far from the {month} boundary to "
              f"difference against; using the trailing window instead.")
        prev_state = None
    cur_px = _prices(cm, fxm, com)
    rets, basis = _returns(cur_px, (prev_state or {}).get("px"), cm, fxm, com)

    ou = nv.get("pct_vs_fair")
    if ou is None and nv.get("price") and nv.get("fair_value"):
        ou = (nv["price"] / nv["fair_value"] - 1.0) * 100.0
    g = _vol_groups(vr, "30d")
    turbulent = list(g["crypto"][0]) + list(g["commodity"][0]) + list(g["fx"][0])
    cur_state = {"captured": now.isoformat(timespec="seconds"), "px": cur_px,
                 "high": sorted(turbulent), "btc_ou": round(ou) if ou is not None else None,
                 "btc_price": round(nv["price"]) if nv.get("price") else None}

    body, meta = compose(SIGNAL_FREE, month, rets, basis, cur_state, prev_state)
    body = body.replace("# Levanter monthly Signal\n",
                        f"# Levanter monthly Signal · {_month_name(month)}\n", 1)
    open(note_path, "w").write(body)
    open(li_path, "w").write(teaser(meta, hashtags=True))
    open(sub_path, "w").write(teaser(meta, hashtags=False))

    state[month] = cur_state
    _save_state(state)

    try:
        import md2docx
        for p in (note_path, li_path, sub_path):
            md2docx.convert(p, os.path.join(OUT, "docx",
                                            os.path.basename(p).replace(".md", ".docx")))
    except Exception as e:
        print("signal_monthly: docx skipped:", e)
    print(f"signal_monthly: prepared {month} Signal ({basis} basis) + teasers in {OUT}/")


if __name__ == "__main__":
    main()
