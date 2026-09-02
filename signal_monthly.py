#!/usr/bin/env python3
"""Levanter monthly Signal generator (premium note).

The monthly counterpart to signal_note.py. Where the free monthly review on the
site is a trailing-30-day read written on the 28th, this is the accountable
subscriber note published on the 1st, covering the month that has just closed:
what actually changed month on month, the thirty-day volatility map, the levels
worth watching, and a claim we score in the next issue.

PREMIUM. Written to reports/signals/ and never copied to the public site.

    python signal_monthly.py [--force] [--month YYYY-MM] [--as-of ISO8601]

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
import statistics
import sys

import signal_note as sn
import repo_lock
from source_guard import SourceError, SIGNAL_SOURCES, check_sources

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


# Pinned capture time, set by --as-of. A published issue has to be
# reproducible: regenerating August in September must stamp and difference
# as August, not as today. None means use the real clock.
_AS_OF = None


def _now():
    return _AS_OF or sn._now_gst()


def _d(iso):
    """2026-08-24 -> 24 August."""
    try:
        return dt.date.fromisoformat(str(iso)).strftime("%-d %B")
    except (ValueError, TypeError):
        return str(iso)


def _num_word(n):
    return {2: "two", 3: "three", 4: "four", 5: "five"}.get(n, str(n))


def _weekly_in_month(month):
    """Weekly Signal snapshots captured inside the covered month, oldest first.
    Used only for the first monthly issue, when no prior month-end snapshot
    exists to difference against. These are SEVEN-day classifications, so
    anything built from them has to say so."""
    h = sn._read_root("signal_history.json") or {}
    return [(k, h[k]) for k in sorted(k for k in h if str(k).startswith(month))]


def _voldetail30(vr, sym):
    """Thirty-day volatility detail. signal_note._voldetail is hard-wired to the 7d
    horizon, which is the wrong window to quote in a monthly note."""
    a30 = vr.get("assets", {}).get(sym, {}).get("30d", {})
    if not a30:
        return None
    return {"now": round(a30.get("vol_now", 0)), "med": round(a30.get("vol_median", 0)),
            "reg30": a30.get("regime")}


def _regime_word(reg):
    """The note's vocabulary is turbulent/calm; the model's is HIGH/LOW."""
    return {"HIGH": "turbulent", "LOW": "calm"}.get(str(reg).upper(), str(reg).lower())


CLS_LABEL = {"crypto": "Crypto", "fx": "FX", "commodity": "Commodities"}


def _vol_table(vr, horizon="30d"):
    """Every tracked market with its own volatility numbers, not just the call.
    The classification alone is the free tier's level of detail; a subscriber
    should see the reading, the market's own median, and where it sits."""
    cls, assets = vr.get("classes", {}), vr.get("assets", {})
    ood = vr.get("ood", {}) or {}
    rows = []
    for sym, c in sorted(cls.items()):
        a = (assets.get(sym, {}) or {}).get(horizon, {}) or {}
        if not a or a.get("vol_now") is None:
            continue
        now, med = a.get("vol_now"), a.get("vol_median")
        pct = (ood.get(sym, {}) or {}).get("vol_pctile")
        rows.append({"sym": sym, "cls": c, "now": now, "med": med,
                     "ratio": (now / med) if med else None,
                     "pctile": pct, "call": _regime_word(a.get("regime"))})
    return rows


def _horizon_medians(rows_map):
    """Median 30d / 180d / 365d move for a class, so the month can be read against
    the year rather than in isolation."""
    out = {}
    for key, field in (("m1", "chg30"), ("m6", "chg180"), ("m12", "chg365")):
        vals = sorted(v for v in (r.get(field) for r in rows_map) if isinstance(v, (int, float)))
        out[key] = statistics.median(vals) if vals else None
        out[key + "_n"] = len(vals)
    return out


def _pct(v, dp=1):
    return "n/a" if v is None else f"{v:+.{dp}f}%"


def _lvl(v):
    """Exact price for a levels table. signal_note._kfmt rounds to the nearest
    thousand, which is fine for bitcoin prose and wrong for ether: it renders
    2,437 as 2,000. A table of levels has to be precise."""
    if v is None:
        return "n/a"
    if v >= 100:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:,.4f}"


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
    now = _now()
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
        # Calling a +0.6 percent move "weakest" reads as an error. When the tail is
        # still positive the honest word is laggards, not weakest.
        tail_word = "Weakest" if all(v < 0 for _, v in st["bot"]) else "Laggards"
        P.append(
            f"**{label[cls]}.** {st['up']} of {st['n']} higher, average {st['avg']:+.1f} percent. "
            f"Strongest: {_moves(st['top'])}. {tail_word}: {_moves(st['bot'])}.")
        P.append("")

    # ===== The month against the year =====
    # The free tier reports the month. A subscriber should be able to see whether
    # the month was ordinary or unusual, which needs the longer horizons alongside it.
    hz = {"crypto": _horizon_medians(cm.get("coins") or []),
          "fx": _horizon_medians(fxm.get("pairs") or []),
          "comd": _horizon_medians(com.get("items") or [])}
    if any(v.get("m12") is not None for v in hz.values()):
        P += ["## The month against the year", ""]
        P.append("One month tells you almost nothing on its own. The table sets the median market in "
                 "each class against its own six and twelve month record, so you can see whether this "
                 "month was ordinary, or the outlier the headline number makes it look.")
        P.append("")
        P.append("| Class | Median this month | Median 6 months | Median 12 months |")
        P.append("| --- | --- | --- | --- |")
        for cls, lab in (("crypto", "Crypto"), ("fx", "FX"), ("comd", "Commodities")):
            h = hz.get(cls, {})
            P.append(f"| {lab} | {_pct(h.get('m1'))} | {_pct(h.get('m6'))} | {_pct(h.get('m12'))} |")
        P.append("")
        P.append("Medians, not averages, so a single runaway name cannot carry the row. Where a "
                 "market has too little history for a horizon it is left out of that column rather "
                 "than padded.")
        P.append("")
        # The month-against-year gap is usually the most useful thing on this page,
        # and it is the read the free monthly cannot give because it has no table.
        ch = hz.get("crypto", {})
        if ch.get("m1") is not None and ch.get("m12") is not None and ch["m1"] > 0 > ch["m12"]:
            P.append(
                f"That crypto row is the number to sit with. The median coin rose "
                f"{ch['m1']:.1f} percent this month and is still down {abs(ch['m12']):.0f} percent "
                f"over twelve months, across the {ch.get('m12_n', 0)} coins with a full year of "
                f"history. A strong month inside a bad year is a different thing from a recovery, and "
                f"the monthly number on its own cannot tell you which one you are looking at. This is "
                f"the gap between a good month and a good year, and it is where position sizing is "
                f"decided rather than where it is celebrated.")
            P.append("")

    # How far the board sits below its own highs. A strong month can still leave
    # every name well under water, and that gap is the one that decides sizing.
    _dd = sorted(c["dd"] for c in (cm.get("coins") or [])
                 if isinstance(c.get("dd"), (int, float)))
    if _dd:
        _med = statistics.median(_dd)
        _bands = {}
        for c in (cm.get("coins") or []):
            _bands[c.get("risk_band")] = _bands.get(c.get("risk_band"), 0) + 1
        _hi = _bands.get("high", 0)
        P.append(
            f"Drawdown is the other half of that picture. The median coin sits {abs(_med):.0f} percent "
            f"below its own recent high and the deepest is {abs(_dd[0]):.0f} percent under, across "
            f"{len(_dd)} names. Our risk banding puts {_bands.get('low', 0)} of them in the low band, "
            f"{_bands.get('medium', 0)} in the medium and {_hi} in the high. A month can be green and "
            f"still leave the whole board under water, which is why we quote the distance from the "
            f"high next to the return rather than instead of it.")
        P.append("")

    # Breadth: whether the move was broad or carried by the heavyweights.
    capw, eqw = cm.get("cap_weighted_ret"), cm.get("equal_weighted_ret")
    if capw is not None and eqw is not None:
        broad = eqw > capw
        P.append(
            f"Breadth inside crypto. The equal-weighted basket returned {eqw:+.1f} percent against "
            f"{capw:+.1f} percent cap-weighted. "
            + (f"The average coin beat the heavyweights, so the move broadened into smaller names. "
               f"That is the signature of healthy appetite and also of the later stage of a run, when "
               f"the quality bar quietly drops."
               if broad else
               f"The heavyweights carried the move and the average coin lagged them, so the rally is "
               f"narrower than the index return suggests.")
            + f" Bitcoin dominance is near {dom:.0f} percent."
            if dom else "")
        P.append("")

    # ===== Valuation =====
    if fair:
        P += ["## The one chart: bitcoin against its long-run trend", ""]
        P.append(
            f"Bitcoin is near {sn._kfmt(price)} dollars. The **valuation fit** models price against "
            f"how long the network has existed, on a log-log scale. Fair value on that fit lands near "
            f"{sn._kfmt(fair)}, with bitcoin about {abs(ou):.0f} percent "
            f"{'below' if ou < 0 else 'above'} it, and the fitted floor sits near "
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
                f"so close agreement is near enough guaranteed and tells you nothing the first number did "
                f"not. On a monthly horizon this is the number that matters most, because valuation "
                f"says far more about a year than about a week.")
            P.append("")

    # ===== Cycle detail: the majors against their own trend, not just bitcoin =====
    cyc_rows = [a for a in (cg.get("assets") or [])
                if a.get("kind") == "crypto" and a.get("pct_vs_trend") is not None]
    if cyc_rows:
        P += ["## The majors against their own trend lines", ""]
        P.append("Bitcoin is not the whole of crypto and the majors do not sit at the same point on "
                 "their own curves. Each row below is fitted separately, against that asset's own "
                 "history, so the comparison is like for like.")
        P.append("")
        P.append("| Asset | Price | Cycle gauge fair value | Against trend |")
        P.append("| --- | --- | --- | --- |")
        for a in cyc_rows:
            P.append(f"| {a.get('name', a.get('sym'))} | {_lvl(a.get('price'))} | "
                     f"{_lvl(a.get('fair'))} | {a['pct_vs_trend']:+.0f}% |")
        P.append("")
        if fair:
            P.append(f"The bitcoin fair value in this table is the cycle gauge's, which is why it "
                     f"differs from the {sn._kfmt(fair)} quoted above. Two fits, two price histories, "
                     f"two answers. We show both rather than picking the one that reads better.")
            P.append("")
        eb = cg.get("ethbtc") or {}
        halv = cg.get("days_since_halving")
        bits = []
        if eb.get("ratio") is not None:
            bits.append(f"The ether to bitcoin ratio is {eb['ratio']:.4f}"
                        + (f", around the {eb['percentile']:.0f}th percentile of its own range"
                           if eb.get("percentile") is not None else "")
                        + (f", {eb['chg6m']:+.0f} percent over six months" if eb.get("chg6m") is not None else "")
                        + ". Leadership inside crypto rotates, which is why a single crypto number "
                          "hides more than it shows.")
        if halv:
            nh = ""
            if cg.get("next_halving"):
                try:
                    nh = (f", with the next due in "
                          f"{dt.date.fromisoformat(cg['next_halving']):%B %Y}")
                except (ValueError, TypeError):
                    nh = f", with the next due {cg['next_halving']}"
            bits.append(f"We are {halv:,} days past the 2024 halving{nh}, and the gauge reads the "
                        f"phase as {str(phase).lower()}.")
        for b in bits:
            P.append(b)
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
    br = (b30 or {}).get("brier") or {}
    if br.get("brier") is not None and br.get("brier_base") is not None:
        P.append(
            f"Accuracy on its own flatters a model that never commits, so we also score the "
            f"confidence behind each call. The Brier score is {br['brier']:.3f} against "
            f"{br['brier_base']:.3f} for always guessing the base rate, a skill score of "
            f"{br.get('skill', 0):.3f} over {br.get('n_eval', 0):,} scored calls. Positive but small. "
            f"Read the calls as a lean rather than a conviction, and size accordingly.")
        P.append("")
    ood_hits = sorted(s for s, v in (vr.get("ood") or {}).items() if v.get("out_of_range"))
    if ood_hits:
        P.append(f"The model also flags {sn._join(ood_hits)} as sitting outside the volatility range it "
                 f"was fitted on, so treat those classifications with more caution than the rest.")
        P.append("")
    P.append(
        (f"For the month ahead it reads {_turb_txt(turbulent, 6)} as turbulent and the rest of the "
         f"board as calm." if turbulent else
         "For the month ahead it reads the whole board as calm, which is itself worth noting.")
        + (f" Average cross-asset correlation is near {corr:.2f}, so diversification is "
           f"{'thin' if corr > 0.5 else 'doing real work'}." if corr else ""))
    P.append("")

    # When every turbulent market sits inside one asset class, that concentration is
    # the month's real story and is worth stating outright rather than leaving the
    # reader to count the names.
    _ONE = {"crypto": "a crypto market", "fx": "a currency pair", "commodity": "a commodity"}
    _MANY = {"crypto": "crypto", "fx": "foreign exchange", "commodity": "commodities"}
    hot = [k for k, v in g.items() if v[0]]
    if turbulent and len(hot) == 1:
        calm_cls = [_MANY[k] for k in g if k != hot[0] and (g[k][0] or g[k][1])]
        P.append(
            f"Worth naming: every market the model calls turbulent this month is {_ONE[hot[0]]}. It "
            f"reads the whole of {sn._join(calm_cls)} as calm. Turbulence is sitting in one corner of "
            f"the board rather than spread across it, which is a different picture from a market that "
            f"is simply nervous everywhere.")
        P.append("")

    # ===== The full volatility board =====
    # The free tier gets the conclusion. The subscriber gets the working: every
    # tracked market's own reading against its own median, which is what the call
    # is actually made from.
    vt = _vol_table(vr, "30d")
    if vt:
        P += ["### The full board, market by market", ""]
        P.append("This is the model's working rather than its conclusion. Volatility is annualised. "
                 "The median column is each market's own long-run median, so every row is judged "
                 "against itself and not against a common threshold. Percentile is where the current "
                 "reading sits in that market's own history.")
        P.append("")
        P.append("| Market | Class | 30d vol | Its median | vs median | Percentile | Call |")
        P.append("| --- | --- | --- | --- | --- | --- | --- |")
        for r in sorted(vt, key=lambda x: (x["cls"], -(x["ratio"] or 0))):
            ratio = f"{r['ratio']:.2f}x" if r.get("ratio") else "n/a"
            pct = f"{r['pctile']:.0f}" if r.get("pctile") is not None else "n/a"
            med = f"{r['med']:.0f}" if r.get("med") is not None else "n/a"
            P.append(f"| {r['sym']} | {CLS_LABEL.get(r['cls'], str(r['cls']).title())} | "
                     f"{r['now']:.0f} | {med} | {ratio} | {pct} | {r['call']} |")
        P.append("")
        hi = [r for r in vt if r["call"] == "turbulent"]
        if hi:
            top = max(hi, key=lambda x: x.get("ratio") or 0)
            P.append(f"The most stretched reading on the board is {top['sym']}, running "
                     f"{top['ratio']:.2f} times its own median. A market can be called turbulent while "
                     f"still sitting below another market's calm reading, which is the point of judging "
                     f"each one against itself.")
            P.append("")
        # A call sitting on the median is a coin flip dressed as a classification.
        # Say so rather than letting the table imply equal confidence in every row.
        edge = sorted((r for r in vt if r.get("ratio") and 0.9 <= r["ratio"] <= 1.1),
                      key=lambda x: abs(x["ratio"] - 1))
        if edge:
            names = sn._join([f"{r['sym']} at {r['ratio']:.2f}x" for r in edge[:4]])
            P.append(f"Treat the rows near the line with less confidence than the rest. {names} are "
                     f"close enough to their own medians that the call could go either way, and we "
                     f"would rather flag that than present every row as equally settled. The ones "
                     f"worth acting on are the stretched readings at the top and the quiet ones at "
                     f"the bottom.")
            P.append("")

    # ===== What changed =====
    P += ["## What changed since the last monthly Signal", ""]
    if prev_state:
        # Iterate the stored LIST, not the set, or the "calmed" order varies
        # between runs on identical data and the issue is not reproducible.
        prev_high_list = prev_state.get("high", []) or []
        prev_high = set(prev_high_list)
        flips = [h for h in turbulent if h not in prev_high]
        calmed = [h for h in prev_high_list if h not in turbulent]
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
        # No prior month end to difference against on a first issue. Rather than
        # promise value next month, use our own weekly record from inside this
        # one: it shows the rotation happening rather than only its end state.
        wk = _weekly_in_month(month)
        if len(wk) >= 2:
            (k0, w0), (k1, w1) = wk[0], wk[-1]
            a_list = w0.get("high", []) or []
            b_list = w1.get("high", []) or []
            a_set, b_set = set(a_list), set(b_list)
            gained = [x for x in b_list if x not in a_set]
            lost = [x for x in a_list if x not in b_set]
            P.append(
                f"This is the first monthly Signal, so there is no prior month end to difference "
                f"against. We do have our own weekly record from inside the month, and it shows the "
                f"month had a direction rather than just an end state.")
            P.append("")
            P.append(
                f"Between our weekly Signal for the week of {_d(k0)} and the one for the week of "
                f"{_d(k1)}, the number of markets the model called turbulent went "
                f"from {len(a_list)} to {len(b_list)}."
                + (f" Newly turbulent: {sn._join(gained)}." if gained else "")
                + (f" Calmed back to normal: {sn._join(lost)}." if lost else ""))
            P.append("")
            if gained and lost:
                P.append(
                    "Read those two lists together rather than separately. Turbulence did not simply "
                    "increase, it moved: out of the names that calmed and into the ones that flipped. "
                    "That is the same rotation the thirty-day board shows at month end, caught while "
                    "it was happening rather than inferred from the finish.")
                P.append("")
            o0, o1 = w0.get("btc_ou"), w1.get("btc_ou")
            p0, p1 = w0.get("btc_price"), w1.get("btc_price")
            if o0 is not None and o1 is not None:
                moved = o1 - o0
                P.append(
                    f"Bitcoin went from {abs(o0):.0f} to {abs(o1):.0f} percent below its fitted value "
                    f"over the same stretch"
                    + (f", with price easing from {p0:,.0f} to {p1:,.0f} dollars"
                       if p0 and p1 and p1 < p0 else
                       f", with price moving from {p0:,.0f} to {p1:,.0f} dollars" if p0 and p1 else "")
                    + ". "
                    + ("A wider discount on a lower price is the fit doing what it should, not a "
                       "signal in itself." if moved < 0 else
                       "The gap narrowed, which on a monthly horizon is context rather than a trigger."))
                P.append("")
            P.append(
                f"Two caveats worth stating. These are seven-day classifications from the weekly "
                f"Signal, not the thirty-day calls used above, they are keyed to the week they cover "
                f"rather than the day they were drawn, and {_num_word(len(wk))} snapshots is a "
                f"short record. From next month this section compares month end against month end "
                f"directly, on the same horizon as the rest of the note.")
        else:
            P.append(
                "From next month this section flags which markets newly flipped turbulent or calm and "
                "how far bitcoin moved against its fitted value, so you can see what changed rather "
                "than only the latest state.")
    P.append("")

    # ===== Watchlist =====
    P += ["## Subscriber watchlist, with levels", ""]
    _stb = [x for x in (cm.get("stables") or []) if isinstance(x.get("minp"), (int, float))]
    _wk = min(_stb, key=lambda x: x["minp"]) if _stb else {}
    _off = ("still above" if _wk.get("minp", 0) >= 0.995 else "below")
    ve = _voldetail30(vr, "ETH")
    bullets = [
        (f"- **Bitcoin.** Fitted floor near {sn._kfmt(floor)}, fair value near {sn._kfmt(fair)}. A "
         f"monthly close below the fitted floor would be historically unusual and would challenge the "
         f"model, rather than automatically creating a buying opportunity.") if fair else "",
        (f"- **Ether volatility.** Thirty-day annualised volatility is near {ve['now']} percent against "
         f"a historical median around {ve['med']}. The thirty-day classification currently reads "
         f"{_regime_word(ve['reg30'])}.") if ve else "",
        (f"- **The metals.** Whether the turbulent bid broadens beyond "
         f"{sn._join([m for m in g['commodity'][0] if m in METALS])} or fades back to calm."
         ) if [m for m in g["commodity"][0] if m in METALS] else "",
        (f"- **Pegs and dominance.** Bitcoin dominance is near {dom:.0f} percent. "
         + (f"Of the {len(_stb)} stablecoins we track the weakest print this month was {_wk['coin']} "
            f"at {_wk['minp']:.4f}, {_off} the 0.995 line that triggers Levanter's wobble alert. "
            if _stb and _wk.get("minp") is not None else
            "The stablecoins we track are holding. ")
         + "We publish the weakest reading rather than a pass mark, because the number is the point."
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

    # CLAUDE.md: quote all three scorecard rows with the commodities caveat attached.
    # Never the blended figure, which flatters the weaker sample by averaging it away.
    rows = {c.get("cls"): c for c in (dbt.get("by_class") or [])}
    crow, comrow, fxrow = rows.get("crypto", {}), rows.get("commodity", {}), rows.get("fx", {})
    if crow.get("acc") is not None:
        ci = sn._wilson_ci(crow.get("acc"), crow.get("n"))
        citxt = f", 95 percent interval {ci[0]} to {ci[1]}" if ci else ""
        P.append(
            f"One honesty section to close, quoted by asset class rather than blended into a single "
            f"number. On direction our crypto calls run about {crow['acc']:.0f} percent over "
            f"{crow['n']:,} backtested calls{citxt}. That is a coin flip.")
        P.append("")
        if comrow.get("acc") is not None and comrow.get("n"):
            P.append(
                f"Commodities read {comrow['acc']:.0f} percent over {comrow['n']:,} calls. We do not "
                f"present that as an edge and you should not read it as one. The sample is small, "
                f"commodity moves are serially correlated so consecutive calls are not independent "
                f"bets, the window trended, and we scored three asset classes. The highest of three "
                f"is the one most likely to be luck.")
            P.append("")
        if not fxrow.get("n"):
            P.append("FX has no scored sample yet, so we quote nothing for it rather than filling the "
                     "gap with the blended figure.")
            P.append("")
        P.append(
            f"These are backtested calls over a fixed window{(', ' + dbt['period']) if dbt.get('period') else ''}, "
            f"not a live public record, and we label them that way every time. We publish them because "
            f"the number is the point. Volatility is forecastable and we forecast it. Direction is not, "
            f"so we do not sell it.")
        P.append("")

    # ===== What would make this wrong =====
    # The free monthly argues a view. A paid note should say what would break it,
    # in terms specific enough to check next month rather than general caution.
    P += ["## What would make this read wrong", ""]
    P.append("Every claim above is checkable, so here is what would falsify it. These are the "
             "things we will be marked against, not a disclaimer.")
    P.append("")
    _f = []
    if turbulent:
        _f.append(f"**The concentration breaks.** We say turbulence is sitting in one corner of the "
                  f"board. If crypto or the dollar pairs flip turbulent next month while the "
                  f"commodity complex calms, the rotation read was wrong, not early.")
    if b30.get("acc"):
        _f.append(f"**The hit rate slips.** The classifier runs about {b30['acc']} percent in "
                  f"backtest. If next month's scored calls come in materially under that, the "
                  f"backtest was flattering the live model and we will say so in the scoring.")
    if floor:
        _f.append(f"**Bitcoin closes below the fitted floor.** Near {sn._kfmt(floor)}. That has "
                  f"happened in roughly 5 percent of history. A monthly close under it does not "
                  f"confirm the model, it challenges it, and we would report it that way.")
    if _stb and _wk.get("minp") is not None:
        _f.append(f"**A tracked peg breaks 0.995.** The weakest this month was {_wk['coin']} at "
                  f"{_wk['minp']:.4f}. Below that line the wobble alert fires and the calm reading "
                  f"across crypto stops being the whole story.")
    if corr:
        _f.append(f"**Correlation keeps climbing.** Near {corr:.2f} now. Higher and the calm names "
                  f"stop being a diversifier, which would matter more than any single call on this "
                  f"page.")
    for _b in _f:
        P.append("- " + _b)
    P.append("")

    # ===== Appendix: the complete board =====
    # Top three and bottom three is a summary. A paid note should not make the
    # reader take our word for what the other thirty markets did.
    P += ["## Appendix: every market we track", ""]
    P.append("The full month for every market on the board, not a selection. Ranked within each "
             "class. This is the same data the summary above is drawn from.")
    P.append("")
    for cls, lab in (("crypto", "Crypto"), ("fx", "Foreign exchange"), ("comd", "Commodities")):
        rowset = rets.get(cls) or []
        if not rowset:
            continue
        P += [f"### {lab}", ""]
        P.append("| Market | Move | Market | Move |")
        P.append("| --- | --- | --- | --- |")
        ordered = sorted(rowset, key=lambda kv: kv[1], reverse=True)
        half = (len(ordered) + 1) // 2
        left, right = ordered[:half], ordered[half:]
        for i in range(half):
            a = f"{left[i][0]} | {left[i][1]:+.1f}%"
            b = f"{right[i][0]} | {right[i][1]:+.1f}%" if i < len(right) else " | "
            P.append(f"| {a} | {b} |")
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
            "basis": basis, "ou": ou, "dom": dom, "acc30": b30.get("acc"),
            # The crypto row, never the blended figure. CLAUDE.md.
            "dacc": crow.get("acc")}
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


def x_thread(meta):
    """The monthly Signal as a short promo X thread (each post under the limit)."""
    m = meta
    posts = []
    posts.append(
        (f"The Levanter monthly Signal for {m['mname']} is out, our deeper premium read on "
         f"volatility, valuation and positioning across crypto, FX and commodities. Free while we "
         f"build the list. Thread.") if SIGNAL_FREE else
        (f"The Levanter monthly Signal for {m['mname']} is out: the deeper premium read on volatility, "
         f"valuation and positioning across crypto, FX and commodities. Thread."))
    st = _stats(m["rets"].get("crypto", []))
    if st:
        s0, v0 = st["top"][0]
        posts.append(
            f"The month behind. Crypto: {st['up']} of {st['n']} higher, average {st['avg']:+.1f}%. "
            f"Strongest {s0} {v0:+.1f}%. FX and commodities in the full note.")
    if m["turbulent"]:
        vtxt = (f" The 30-day volatility classifier runs about {m['acc30']}% in backtest, a real edge."
                if m.get("acc30") else "")
        posts.append(
            f"For the month ahead the model reads {_turb_txt(m['turbulent'], 4)} turbulent and the "
            f"rest calm.{vtxt}")
    if m.get("ou") is not None:
        posts.append(
            f"Bitcoin sits about {abs(m['ou']):.0f}% {'below' if m['ou'] < 0 else 'above'} its "
            f"valuation fit. On a monthly horizon valuation says more than any week-ahead guess. "
            f"Context, not a target.")
    # Quote the crypto row (largest sample), never the blended figure. CLAUDE.md.
    cr = {c.get("cls"): c for c in sn._read_root("direction_backtest.json").get("by_class", [])
          }.get("crypto", {})
    if cr.get("n") and cr.get("acc") is not None:
        ci = sn._wilson_ci(cr["acc"], cr["n"])
        citxt = f" (95% CI {ci[0]}-{ci[1]})" if ci else ""
        posts.append(
            f"Direction we do not sell. Crypto calls run about {cr['acc']:.0f}% over {cr['n']:,} "
            f"backtested calls{citxt}, a coin flip, and we publish it. Volatility is forecastable, "
            f"direction is not.")
    posts.append(
        "The full monthly Signal, with the levels and the month-on-month changes, is for subscribers: "
        "read.levantermarkets.com. Educational, not advice.")
    return sn._thread_file(f"Levanter monthly Signal thread · {m['mname']}", posts)


def main():
    argv = sys.argv[1:]
    # One writer at a time. Two sessions in this tree have already
    # produced a half-written feed; see repo_lock.
    try:
        repo_lock.acquire("signal_monthly")
    except repo_lock.LockBusy as e:
        print(f"signal_monthly: {e}", file=sys.stderr)
        sys.exit(1)

    # The monthly Signal reads the same feeds as the weekly, so it gets the same
    # hard precondition: a broken feed stops the build rather than quietly
    # costing the note a section.
    try:
        check_sources(SIGNAL_SOURCES, "the monthly Signal")
    except SourceError as e:
        print(f"signal_monthly: {e}", file=sys.stderr)
        sys.exit(1)
    force = "--force" in argv
    if "--as-of" in argv:
        global _AS_OF
        raw = argv[argv.index("--as-of") + 1]
        _AS_OF = dt.datetime.fromisoformat(raw)
    now = _now()
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
    # The accompanying X thread, in its own channel dir (pasted post by post).
    x_dir = os.path.join("reports", "x")
    os.makedirs(x_dir, exist_ok=True)
    open(os.path.join(x_dir, f"levanter-signal-monthly-x-{month}.md"), "w").write(x_thread(meta))

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
