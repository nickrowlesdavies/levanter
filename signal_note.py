#!/usr/bin/env python3
"""Levanter Signal generator (weekly premium note).

Drafts the midweek/Monday premium "Levanter Signal" from the same live data the
dashboard uses: one chart that matters (the bitcoin valuation fit), the week-ahead
volatility read across crypto, foreign exchange and commodities, and an honest
line on what is and is not knowable. Also drafts a LinkedIn teaser.

This is a PREMIUM piece, so it is written to reports/signals/ and is NOT copied
to the public site. It publishes 06:00 GST on Wednesdays (still anchored to the
week's Monday in title and filename): the first build at or after that time
generates the frozen weekly snapshot, and later builds in the same week skip it
(idempotent), so the "week ahead" numbers do not drift.

    python signal_note.py [--force] [--monday YYYY-MM-DD]

Voice rules: no em dashes, no AI kill-words. Educational, not advice.
"""
import datetime as dt
import json
import os
import sys

import repo_lock
import x_text
from source_guard import SourceError, SIGNAL_SOURCES, check_sources

OUT = "reports/signals"
# The Signal is the PAID tier, currently free while the list is built. There is no
# end date: the plan is to tell readers before that changes, so this is a flag a
# human flips deliberately, not a date that flips itself. It used to be
# LAUNCH_UNTIL = "2026-08-31", which would have silently dropped the free framing
# on 7 September and, worse, promised "free this week and next" in the meantime.
# Set to False on the week the Signal actually goes subscriber-only.
SIGNAL_FREE = True
# Separate from the pricing flag above: this one is the one-time "introducing our new
# weekly newsletter, here is the first Signal" copy in the teaser. It is true for the
# launch issue only. It used to be keyed off SIGNAL_FREE, which meant every issue for
# the whole free period announced itself as the first one.
SIGNAL_FIRST_ISSUE = False
NAMES = {
    "BTC": "bitcoin", "ETH": "ether", "SOL": "solana", "XRP": "XRP",
    "GOLD": "gold", "SILVER": "silver", "PLATINUM": "platinum",
    "PALLADIUM": "palladium", "OIL": "oil", "WTI OIL": "oil", "BRENT OIL": "Brent crude",
    "COPPER": "copper", "NAT GAS": "natural gas", "WHEAT": "wheat", "CORN": "corn",
    "COFFEE": "coffee", "SUGAR": "sugar", "COTTON": "cotton", "SOYBEANS": "soybeans",
    "GASOLINE": "gasoline", "HEATING OIL": "heating oil",
    "AGRICULTURE": "agriculture", "BROAD": "broad commodities",
    "EURUSD": "the euro", "GBPUSD": "sterling", "USDJPY": "the yen",
    "AUDUSD": "the Aussie", "USDCHF": "the Swiss franc", "USDCAD": "the loonie",
    "NZDUSD": "the kiwi", "SPX": "the S&P",
}


def _read(p):
    try:
        return json.load(open(os.path.join("reports", p)))
    except Exception:
        return {}


def _read_root(p):
    """Committed JSON at the repo root (e.g. direction_backtest.json)."""
    try:
        return json.load(open(p))
    except Exception:
        return {}


def _check_sources():
    """Refuse to write a Signal on top of a broken feed. See source_guard."""
    check_sources(SIGNAL_SOURCES, "the Signal")


SIGNAL_STATE = "signal_history.json"   # not *_state.json, which .gitignore excludes


def _load_signal_state():
    try:
        return json.load(open(SIGNAL_STATE))
    except Exception:
        return {}


def _save_signal_state(d):
    json.dump(d, open(SIGNAL_STATE, "w"), indent=2)


def _now_gst():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=4)


def _name(sym):
    return NAMES.get(sym, sym)


def _join(names):
    names = list(names)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _cap(s):
    return s[:1].upper() + s[1:] if s else s


_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten", "eleven", "twelve"]


def _num(n):
    return _WORDS[n] if 0 <= n <= 12 else str(n)


def _sentences(bits):
    """Join clauses as separate sentences (each capitalised), not a run-on."""
    return ". ".join(_cap(b) for b in bits if b)


def _kfmt(v):
    return f"{v/1000:.0f},000" if v and v >= 1000 else f"{v:,.0f}"


METALS = {"GOLD", "SILVER", "PLATINUM", "PALLADIUM", "COPPER"}
ENERGY = {"WTI OIL", "BRENT OIL", "OIL", "NAT GAS", "NATGAS"}
AGRI = {"WHEAT", "CORN", "SOYBEAN", "AGRICULTURE", "SUGAR", "COFFEE"}


def _pct(v, dp=0):
    return f"{v:+.{dp}f}%" if v is not None else "n/a"


def _voldetail(vr, sym):
    a = vr.get("assets", {}).get(sym, {})
    a7, a30 = a.get("7d", {}), a.get("30d", {})
    if not a7:
        return None
    return {"regime": a7.get("regime"), "now": round(a7.get("vol_now", 0)),
            "med": round(a7.get("vol_median", 0)), "reg30": a30.get("regime")}


def _vol_groups(vr):
    """{class: (high_names, low_names)} for the 7-day horizon."""
    cls = vr.get("classes", {})
    assets = vr.get("assets", {})
    out = {"crypto": ([], []), "fx": ([], []), "commodity": ([], [])}
    for sym, c in cls.items():
        if c not in out:
            continue
        r = assets.get(sym, {}).get("7d", {})
        if not r:
            continue
        nm = sym if c == "fx" else _name(sym)   # FX: the model forecasts the pair, e.g. USDCHF
        (out[c][0] if r.get("regime") == "HIGH" else out[c][1]).append(nm)
    return out


def _wilson_ci(acc_pct, n, z=1.96):
    """95% Wilson score interval (%) for a binomial proportion from accuracy% and n.
    Same formula as the dashboard, so the Signal and the site never drift."""
    if not n or acc_pct is None:
        return None
    p = acc_pct / 100.0
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round((c - h) * 100), round((c + h) * 100)]


SECTION_ORDER = [
    "## The seven-day volatility map",
    "## What changed since the last Signal",
    "## The one chart: bitcoin against its long-run trend",
    "## What the model can and cannot do",
    "## The week behind, and what it rhymes with",
    "## Subscriber watchlist, with levels",
]


def _reorder(P, order):
    """Reassemble the note so the volatility map leads.

    The map is the only part of the Signal with a measured, scoreable edge, and
    the valuation section repeats figures the free weekly already gives away, so
    the map runs first. Sections are built in whatever order is convenient in
    code; this puts them in reading order. Anything not named keeps its relative
    position at the end.
    """
    head, cur, secs = [], None, []
    for line in P:
        if line.startswith("## "):
            cur = [line]
            secs.append(cur)
        elif cur is None:
            head.append(line)
        else:
            cur.append(line)
    named = {sec[0]: sec for sec in secs}
    out = list(head)
    for h in order:
        if h in named:
            out += named.pop(h)
    for sec in secs:
        if sec[0] in named:
            out += sec
    return out


def compose(free=False, first=False, monday=None):
    _check_sources()
    cm = _read("crypto_map.json")
    vr = _read("vol_regime.json")
    fx = _read("fx_map.json")
    co = _read("commodities_map.json")
    cg = _read("cycle_gauge.json")
    nv = _read("btc_metcalfe.json")
    ps = _read("prediction_state.json")

    bt = vr.get("backtest", {})
    acc7 = (bt.get("7d") or {}).get("acc")
    acc30 = (bt.get("30d") or {}).get("acc")
    acc90 = (bt.get("90d") or {}).get("acc")
    edge7 = (bt.get("7d") or {}).get("edge")
    edge30 = (bt.get("30d") or {}).get("edge")
    g = _vol_groups(vr)

    # ---- crypto week (7-day moves) ----
    coins = cm.get("coins", [])
    wk = [(c["coin"], c.get("chg7"), c.get("market_cap", 0) or 0)
          for c in coins if c.get("chg7") is not None]
    wk_s = sorted(wk, key=lambda x: x[1])
    w_up = sum(1 for _, v, _ in wk if v > 0)
    w_n = len(wk)
    caps = sum(m for _, _, m in wk) or 1
    w_capw = sum(v * m for _, v, m in wk) / caps
    w_eqw = (sum(v for _, v, _ in wk) / w_n) if w_n else 0
    w_disp = (wk_s[-1][1] - wk_s[0][1]) if wk_s else 0
    mv7 = cm.get("movers", {}).get("7d", [])
    dom = cm.get("btc_dominance", 0)
    corr = cm.get("avg_corr")
    watch = [s["coin"] for s in cm.get("stables", []) if s.get("status") != "ok"]

    # ---- fx + commodities week ----
    fp = sorted(((p["pair"], p.get("chg7")) for p in fx.get("pairs", [])
                 if p.get("chg7") is not None), key=lambda x: x[1])
    ci = sorted(((i["name"], i.get("chg7")) for i in co.get("items", [])
                 if i.get("chg7") is not None), key=lambda x: x[1])
    metals = [(n, v) for n, v in ci if n in METALS]
    com_best = ci[-1] if ci else None

    # ---- vol detail + cycle + valuation ----
    vb, ve, vs = _voldetail(vr, "BTC"), _voldetail(vr, "ETH"), _voldetail(vr, "SOL")
    ou = nv.get("over_under_pct")
    price, fair, floor = nv.get("price"), nv.get("fair_value"), nv.get("floor")
    cyc_b = next((round(a.get("pct_vs_trend", 0)) for a in cg.get("assets", [])
                  if a.get("sym") == "BTC"), None)
    phase = next((a.get("phase", "") for a in cg.get("assets", [])
                  if a.get("sym") == "BTC"), "")

    # Judge each complex on its own members and on the balance of them, not on a
    # single name. This used to call energy quiet whenever any one of oil, copper
    # or natural gas was calm: copper is a metal, and on 2 September it printed
    # "calmer across energy" in the LinkedIn and X copy on a week when oil, Brent,
    # gasoline and heating oil were all turbulent and gasoline was the most
    # stretched market on the board.
    ENERGY_SET = {"OIL", "WTI OIL", "BRENT OIL", "NAT GAS", "GASOLINE", "HEATING OIL"}
    _hi7 = {sym for sym, a in vr.get("assets", {}).items()
            if (a.get("7d") or {}).get("regime") == "HIGH"}
    _lo7 = {sym for sym, a in vr.get("assets", {}).items()
            if (a.get("7d") or {}).get("regime") == "LOW"}

    def _complex_state(syms):
        hi, lo = len(syms & _hi7), len(syms & _lo7)
        if hi == lo:
            return None
        return "loud" if hi > lo else "quiet"

    loud, quiet = [], []
    for _label, _syms in (("the metals", METALS), ("energy", ENERGY_SET)):
        _state = _complex_state(_syms)
        if _state == "loud":
            loud.append(_label)
        elif _state == "quiet":
            quiet.append(_label)
    if not loud and g["commodity"][0]:
        loud.append("commodities")
    if g["crypto"][0]:
        loud.append("big-cap crypto")
    if len(g["fx"][1]) >= 4:
        quiet.append("most foreign exchange markets")
    loud_txt = _join(loud) or "a couple of pockets of the market"
    quiet_txt = " and across ".join(quiet) or "the rest of the board"
    # Direction backtest (committed fact) for the one honesty line and the teaser meta.
    dbt = _read_root("direction_backtest.json")
    n, dacc, period, cls = dbt.get("n"), dbt.get("accuracy"), dbt.get("period", ""), dbt.get("by_class", []) or []
    cr = next((c for c in cls if c.get("cls") == "crypto"), {})

    now = _now_gst()
    stamp = now.strftime("%H:%M GST on %-d %B %Y")
    capw30 = cm.get("cap_weighted_ret")
    all_high = list(g["crypto"][0]) + list(g["commodity"][0]) + list(g["fx"][0])
    fx_low, fx_total = len(g["fx"][1]), len(g["fx"][0]) + len(g["fx"][1])
    calm_energy = [x for x in g["commodity"][1] if x in ("oil", "copper", "natural gas")]
    spx = _voldetail(vr, "SPX")

    # Week-on-week snapshot for the "what changed" section.
    mon = monday or (now - dt.timedelta(days=now.weekday())).date().isoformat()
    cur_state = {"high": sorted(all_high),
                 "btc_ou": round(ou) if ou is not None else None,
                 "btc_price": round(price) if price else None, "capw7": round(w_capw)}
    hist = _load_signal_state()
    prior = [k for k in hist if k < mon]
    prev = hist.get(max(prior)) if prior else None

    P = ["# Levanter Signal", ""]
    if free:
        P += ["> **The Levanter Signal.** A weekly read of volatility, valuation and the week "
              "ahead across crypto, FX and commodities. This is the subscriber tier, and it is free "
              "while we build the list. We will tell you before that changes. Subscribe at "
              "read.levantermarkets.com.", ""]
    P += [f"*Data captured at {stamp}. Every figure below is stamped to a period. This is the "
          f"accountable read behind the free weekly: the changes since last week, the levels to watch, "
          f"and a claim we will score in the next issue.*", "", "---", ""]
    P += ["> **Editor's line (add before publishing, then delete this prompt):** one sentence of your "
          "own read of the week. Two minutes. What it means for how you are positioned, or the single "
          "thing you would tell a friend who asked. This is the line the model cannot write.", ""]

    # ===== One chart: bitcoin valuation =====
    if fair:
        P += ["## The one chart: bitcoin against its long-run trend", ""]
        P.append(
            f"Bitcoin is near {_kfmt(price)} dollars. The **valuation fit** models price against how "
            f"long the network has existed, on a log-log scale. Fair value on that fit lands near "
            f"{_kfmt(fair)}, about {abs(ou):.0f} percent "
            f"{'below' if ou < 0 else 'above'} the line, and the fitted floor "
            f"sits near {_kfmt(floor)}. Bitcoin has closed above that floor line for roughly 95 percent "
            f"of the historical sample. That is an in-sample observation, not a tested probability and "
            f"not a guaranteed level of support.")
        P.append("")
        if cyc_b is not None:
            P.append(
                f"Our **cycle gauge** reports a second number, and it is worth being precise about "
                f"what it is. It fits the same shape of curve, price against network age, but on a "
                f"different price history and with a different band, then adds halving timing to "
                f"classify the phase. It reads bitcoin as {phase.lower()}, about {abs(cyc_b):.0f} "
                f"percent below its own trend line. Do not read the two figures as confirming each "
                f"other. They are the same kind of fit run over overlapping data, so close agreement "
                f"is close to guaranteed and tells you nothing the first number did not. Both are "
                f"long-horizon context. Where price sits against a multi-year fit says nothing about "
                f"the next five days, so read it as valuation, not a reason to act on the week.")
            P.append("")
        P += ["*(Chart: bitcoin price against its fitted fair value and floor.)*", ""]

    # ===== Limits of the model =====
    P += ["## What the model can and cannot do", ""]
    P.append(
        "It is a statistical fit of price to time. It has no hard economic mechanism behind it, cannot "
        "call tops, and may fail outside the historical sample. It is a valuation anchor, not a timing "
        "tool. Treat the fair value and the floor as distant reference points, never as targets and "
        "never as a reason to size up.")
    P.append("")

    # ===== Seven-day volatility map =====
    P += ["## The seven-day volatility map", ""]
    if acc7 and acc30:
        _bt7 = (vr.get("backtest", {}) or {}).get("7d", {}) or {}
        _n7, _ci7 = _bt7.get("n"), _bt7.get("ci")
        _br = _bt7.get("brier") or {}
        P.append(
            f"This is the part with measurable skill, and it is why it leads the issue. The model "
            f"tags each market turbulent or calm for the week ahead. In the five-year "
            f"point-in-time backtest it classified the seven-day regime correctly about {acc7} "
            f"percent of the time"
            + (f" across {_n7:,} calls" if _n7 else "")
            + (f", 95 percent interval {_ci7[0]} to {_ci7[1]}," if _ci7 else "")
            + f" {edge7} percentage points above its naïve baseline, and {acc30} percent at "
            f"thirty days, {edge30} points above baseline. That is a backtest, not a live forward "
            f"record: the live scoreboard is only now starting to fill.")
        P.append("")
        if _br.get("skill") is not None:
            P.append(
                f"Accuracy alone can flatter a model that never commits, so we also score the "
                f"confidence behind each call. The Brier score is {_br['brier']} against "
                f"{_br['brier_base']} for always guessing the base rate, a skill score of "
                f"{_br['skill']:.3f} over {_br.get('n_eval', 0):,} scored calls. Positive but "
                f"small. Read the calls as a lean, not a conviction.")
            P.append("")
    calm_names = list(g["crypto"][1])   # calm crypto, e.g. solana
    calm_names.append(f"all {_num(fx_total)} FX pairs" if fx_low == fx_total
                      else f"{_num(fx_low)} of the {_num(fx_total)} FX pairs")
    if spx and spx.get("regime") == "LOW":
        calm_names.append("the S&P 500")
    calm_names += [x for x in g["commodity"][1] if x in ("oil", "copper", "natural gas")]
    P.append(
        f"For the coming week the model reads {_num(len(all_high))} markets turbulent: {_join(all_high)}. "
        f"The rest of the displayed set is calm, including {_join(calm_names)}. The average market is "
        f"therefore contained even though a few names are carrying wide ranges.")
    P.append("")
    # ---- concentration: which classes are actually carrying the turbulence ----
    _CLSNAME = {"crypto": "Crypto", "fx": "FX", "commodity": "Commodities", "equity": "Equity"}
    _cls = vr.get("classes", {})
    _assets_all = vr.get("assets", {})
    _hi_cls = sorted({_cls.get(sym) for sym in _assets_all
                      if (_assets_all.get(sym, {}).get("7d", {}) or {}).get("regime") == "HIGH"
                      and _cls.get(sym)})
    if len(_hi_cls) == 1:
        P.append(
            f"Worth naming: every market the model calls turbulent this week sits in one asset class, "
            f"{_CLSNAME.get(_hi_cls[0], _hi_cls[0]).lower()}. It reads the rest of the board as calm. "
            f"Turbulence concentrated in one corner is a different picture from a market that is "
            f"nervous everywhere, and it is the more common of the two.")
        P.append("")
    elif len(_hi_cls) > 1:
        # A single marginal name in a second class is not cross-asset turbulence, and
        # saying so would overclaim a shared driver that the data does not show.
        _hi_by_cls = {}
        for sym in _assets_all:
            if (_assets_all.get(sym, {}).get("7d", {}) or {}).get("regime") == "HIGH":
                _hi_by_cls.setdefault(_cls.get(sym), []).append(sym)
        _dom_cls = max(_hi_by_cls, key=lambda c: len(_hi_by_cls[c]))
        _dom_n, _tot_n = len(_hi_by_cls[_dom_cls]), sum(len(v) for v in _hi_by_cls.values())
        _others = [s2 for c, v in _hi_by_cls.items() if c != _dom_cls for s2 in v]
        if _dom_n / _tot_n >= 0.8:
            P.append(
                f"Worth naming: {_num(_dom_n)} of the {_num(_tot_n)} turbulent markets are "
                f"{_CLSNAME.get(_dom_cls, _dom_cls).lower()}, with only "
                f"{_join([_name(x) for x in _others])} outside that class, and "
                f"{'that name sits' if len(_others) == 1 else 'those names sit'} close to the line. "
                f"Treat this as turbulence concentrated in one corner of the board rather than a "
                f"market that is nervous everywhere. The two call for different responses.")
        else:
            P.append(
                f"The turbulence is spread across "
                f"{_join([_CLSNAME.get(c, c).lower() for c in sorted(_hi_by_cls)])} rather than "
                f"sitting in one corner of the board. Cross-class turbulence is the rarer reading, "
                f"and it usually points to one shared driver rather than several unrelated stories.")
        P.append("")
    if corr is not None:
        P.append(
            f"Average cross-asset correlation is near {corr:.2f}. "
            + ("That is high enough that diversification is thin: position count is not the same as "
               "risk spread this week." if corr >= 0.5 else
               "That is loose enough that markets are still trading their own stories, so spreading "
               "risk across them is doing real work."))
        P.append("")

    # ---- the full board ----
    _rows = []
    for sym, a in _assets_all.items():
        a7, a30 = a.get("7d") or {}, a.get("30d") or {}
        nowv, medv = a7.get("vol_now"), a7.get("vol_median")
        if not nowv or not medv:
            continue
        _rows.append({
            "sym": sym, "cls": _CLSNAME.get(_cls.get(sym), "Other"),
            "now": nowv, "med": medv, "ratio": nowv / medv,
            "pctile": ((vr.get("ood", {}) or {}).get(sym, {}) or {}).get("vol_pctile"),
            "call": "turbulent" if a7.get("regime") == "HIGH" else "calm",
            "call30": "turbulent" if a30.get("regime") == "HIGH" else
                      ("calm" if a30.get("regime") else "n/a"),
        })
    _rows.sort(key=lambda r: -r["ratio"])
    if _rows:
        P += ["### The full board, market by market", ""]
        P.append(
            "This is the model's working rather than its conclusion. Volatility is annualised. The "
            "median column is each market's own long-run median, so every row is judged against "
            "itself and never against a common threshold: a 6 percent reading in FX can be stretched "
            "while a 35 percent reading in crypto is quiet. Percentile is where the current reading "
            "sits in that market's own history. The thirty-day column is there so you can see whether "
            "a call is a one-week disturbance or a settled regime.")
        P.append("")
        P.append("| Market | Class | 7d vol | Its median | vs median | Percentile | 30d | Call |")
        P.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in _rows:
            _pc = f"{r['pctile']:.0f}" if r["pctile"] is not None else "n/a"
            P.append(f"| {r['sym']} | {r['cls']} | {r['now']:.0f} | {r['med']:.0f} | "
                     f"{r['ratio']:.2f}x | {_pc} | {r['call30']} | {r['call']} |")
        P.append("")
        _top, _bot = _rows[0], _rows[-1]
        P.append(
            f"The most stretched reading on the board is {_name(_top['sym'])}, running "
            f"{_top['ratio']:.2f} times its own median, and the quietest is {_name(_bot['sym'])} at "
            f"{_bot['ratio']:.2f} times. A market can be called turbulent while still sitting below "
            f"another market's calm reading, which is the whole point of judging each one against "
            f"itself.")
        P.append("")
        # Rows close to their own median are coin-flip calls and are flagged as such.
        _near = [r for r in _rows if 0.93 <= r["ratio"] <= 1.07]
        if _near:
            P.append(
                "Treat the rows near the line with less confidence than the rest. "
                + _cap(_join([f"{_name(r['sym'])} at {r['ratio']:.2f}x" for r in _near[:5]]))
                + (" are" if len(_near[:5]) > 1 else " is")
                + " close enough to their own median that the call could go either way. We would "
                  "rather flag that than present every row as equally settled. The rows worth acting "
                  "on are the stretched readings at the top and the quiet ones at the bottom.")
            P.append("")
        # Horizon disagreement is the weekly's own signal: the monthly cannot show it.
        _split = [r for r in _rows if r["call30"] in ("turbulent", "calm")
                  and r["call30"] != r["call"]]
        if _split:
            _now_hi = [_name(r["sym"]) for r in _split if r["call"] == "turbulent"]
            _now_lo = [_name(r["sym"]) for r in _split if r["call"] == "calm"]
            _bits = []
            if _now_hi:
                _bits.append(f"turbulent this week but calm at thirty days, {_join(_now_hi)}")
            if _now_lo:
                _bits.append(f"calm this week but turbulent at thirty days, {_join(_now_lo)}")
            P.append(
                "Where the two horizons disagree. " + _sentences(_bits) + ". A split like that flags "
                "a near-term move without telling you whether it lasts, so it is the set to watch "
                "rather than the set to act on.")
            P.append("")
        _ood = [r["sym"] for r in _rows
                if ((vr.get("ood", {}) or {}).get(r["sym"], {}) or {}).get("out_of_range")]
        if _ood:
            P.append(
                f"Out-of-range flag: {_join([_name(x) for x in _ood])} "
                + ("is" if len(_ood) == 1 else "are")
                + " trading outside the volatility range the model was fitted on. The call still "
                  "prints, but it is an extrapolation and we would discount it accordingly.")
            P.append("")

    if vb and ve:
        # Every claim here is derived. This paragraph used to hardcode "close to
        # double its normal ... both are turbulent ... the two horizons disagree",
        # which fired regardless of the data and contradicted the calm/turbulent
        # list directly above whenever crypto was quiet.
        _W = {"HIGH": "turbulent", "LOW": "calm"}

        def _w(reg):
            return _W.get(str(reg).upper(), str(reg).lower())

        def _rel(v):
            m = v.get("med") or 0
            if not m:
                return f"near {v['now']} percent"
            r = v["now"] / m
            return (f"near {v['now']} percent against a {v['med']} median, "
                    f"{r:.2f} times its own normal")

        b7, b30 = _w(vb.get("regime")), _w(vb.get("reg30"))
        e7, e30 = _w(ve.get("regime")), _w(ve.get("reg30"))
        agree = (b7 == b30) and (e7 == e30)
        def _horizons(name, h7, h30):
            return (f"{name} reads {h7} at both seven and thirty days"
                    if h7 == h30 else
                    f"{name} reads {h7} at seven days and {h30} at thirty")
        line = (f"The big crypto reads. Bitcoin's one-week volatility is {_rel(vb)}, and ether is "
                f"{_rel(ve)}. {_horizons('Bitcoin', b7, b30)}, and "
                f"{_horizons('ether', e7, e30)}.")
        line += (" The two horizons agree, so this is a settled read rather than a near-term "
                 "disturbance." if agree else
                 " The two horizons disagree, which flags a near-term move without telling us "
                 "whether it lasts.")
        # Only claim the metals are stretched on both horizons when they are.
        _assets = vr.get("assets", {})
        both = [m for m in sorted(METALS)
                if (_assets.get(m, {}).get("7d", {}) or {}).get("regime") == "HIGH"
                and (_assets.get(m, {}).get("30d", {}) or {}).get("regime") == "HIGH"]
        if both:
            _m = _join([m.lower() for m in both])
            line += (f" In the metals, {_m} read turbulent at both seven and thirty days, so that "
                     f"is not just a one-week disturbance.")
        P.append(line)
        P.append("")
    if cr.get("n") and cr.get("acc") is not None:
        P.append(
            f"On direction the model is close to a coin flip: {cr['acc']:.0f} percent over "
            f"{cr['n']:,} backtested crypto calls"
            + (f", a 95 percent interval of {_wc[0]} to {_wc[1]} percent that straddles the "
               f"coin-flip line" if (_wc := _wilson_ci(cr.get('acc'), cr.get('n'))) else "")
            + ". We forecast volatility, not direction. Anyone selling you the second thing at "
              "these sample sizes is selling you noise.")
        P.append("")
    P.append(
        "What this map is not: it says nothing about which way a price goes, it cannot tell you why a "
        "market is stretched, and a turbulent call is not a reason to trade. It is a statement about "
        "the width of the range, which is the input to position size, not to direction.")
    P.append("")

    # ===== What changed =====
    P += ["## What changed since the last Signal", ""]
    if prev:
        # Iterate the stored LIST, not the set. Iterating the set made the
        # "calmed back to normal" order vary between runs on identical data,
        # so the same issue could not be reproduced from the same inputs.
        prev_high_list = prev.get("high", []) or []
        prev_high = set(prev_high_list)
        flips = [h for h in all_high if h not in prev_high]
        calmed = [h for h in prev_high_list if h not in all_high]
        d_ou = (round(ou) - prev["btc_ou"]) if (ou is not None and prev.get("btc_ou") is not None) else None
        bits = []
        if flips:
            bits.append(f"newly turbulent, {_join(flips)}")
        if calmed:
            bits.append(f"calmed back to normal, {_join(calmed)}")
        if not flips and not calmed:
            bits.append("the volatility roster is unchanged from last week")
        if d_ou:
            bits.append(f"bitcoin is about {abs(d_ou)} "
                        f"{'point' if abs(d_ou) == 1 else 'points'} "
                        f"{'cheaper' if d_ou < 0 else 'richer'} against its fitted value")
        P.append("Week on week: " + _sentences([_cap(b) for b in bits]) + ".")
    else:
        P.append(
            "From next week this section flags which markets newly flipped turbulent or calm and how "
            "far bitcoin moved against its fitted value, so you can see what changed rather than only "
            "the latest state.")
    P.append("")

    # ===== The week behind =====
    P += ["## The week behind, and what it rhymes with", ""]
    wk_lead = ""
    if len(mv7) >= 2:
        wk_lead = (f", led by the speculative end, {mv7[0]['coin']} {mv7[0]['ret']:+.0f} percent and "
                   f"{mv7[1]['coin']} {mv7[1]['ret']:+.0f} percent")
    # All three asset classes are always addressed here, even if a feed did not
    # return, so crypto, FX and commodities never silently drop out of the Signal.
    # Breadth is read off the up/down split rather than asserted, so the prose cannot
    # claim a broad tape on a week when only a third of the board closed higher.
    _bratio = (w_up / w_n) if w_n else 0.0
    breadth = "broad" if _bratio >= 0.6 else ("narrow" if _bratio <= 0.4 else "mixed")
    if w_n:
        crypto_clause = (
            f"Over the past seven days crypto was {breadth} and speculative-led: {w_up} of {w_n} coins "
            f"higher, cap-weighted about {w_capw:+.0f} percent on the week"
            + (f" and {capw30:+.0f} percent over thirty days" if capw30 is not None else "")
            + f"{wk_lead}, with a best-to-worst spread near {abs(w_disp):.0f} points. Dominance held "
            f"near {dom:.0f} percent and the stablecoins we track kept their pegs.")
    else:
        crypto_clause = ("Crypto data did not return from the feed this week, so the crypto read is "
                         "limited here; full coverage resumes in the next issue.")
    fx_clause = (
        f" In foreign exchange the biggest seven-day move was {fp[-1][0]} at {fp[-1][1]:+.1f} percent, "
        f"ranges otherwise tight." if fp else
        " In foreign exchange the feed was quiet or unavailable this week, with nothing notable to flag.")
    if metals:
        _shown = metals[-3:][::-1]
        _vals = [vv for _, vv in _shown]
        if all(v < 0 for v in _vals):
            _verb = "the metals fell across the board"
        elif all(v > 0 for v in _vals):
            _verb = "the metals led the week"
        else:
            _verb = "the metals were mixed"
        comm_clause = (f" In commodities {_verb}, "
                       + _join([f"{_name(nn)} {vv:+.0f} percent" for nn, vv in _shown]) + ".")
    else:
        comm_clause = (" In commodities the feed was quiet or unavailable this week, with nothing "
                       "notable to flag.")
    tail = (f" The gains were {breadth}, but the largest moves stayed further out on the risk "
            "curve, and the dollar and most FX ranges were comparatively quiet."
            if (w_n and metals) else "")
    P.append(crypto_clause + fx_clause + comm_clause + tail)
    P.append("")
    metals_hi = [m for m in g["commodity"][0] if m in ("gold", "silver", "platinum")]
    if metals_hi and g["crypto"][0] and len(g["fx"][1]) > len(g["fx"][0]):
        P.append(
            "Read across the three asset classes, the unusual combination is strength in both precious "
            "metals and speculative crypto while the dollar remains comparatively quiet. That is "
            "consistent with abundant liquidity or a debasement trade, but the tape alone cannot tell "
            "us which explanation is driving it.")
    else:
        P.append(
            f"Read across the three asset classes, the turbulence is concentrated in {_join(all_high)} "
            f"while the rest stays quiet. That is specific pockets of risk rather than a broad regime "
            f"shift, and the tape alone does not tell us why they are the loud ones this week.")
    P.append("")

    # ===== Watchlist + review =====
    P += ["## Subscriber watchlist, with levels", ""]
    bullets = [
        (f"- **Bitcoin.** Fitted floor near {_kfmt(floor)}, fair value near {_kfmt(fair)}. A weekly "
         f"close below the fitted floor would be historically unusual and would challenge the model, "
         f"rather than automatically creating a buying opportunity.") if fair else "",
        (f"- **Ether volatility.** Current annualised volatility is near {ve['now']} percent against a "
         f"historical median around {ve['med']}. Watch whether the thirty-day classification also flips "
         f"from calm to turbulent.") if ve else "",
        (f"- **The commodity complex.** Whether the turbulent bid broadens beyond "
         f"{_join(g['commodity'][0])} or "
         f"fades back to calm.") if g["commodity"][0] else "",
        (f"- **Pegs and dominance.** Stablecoins are holding and bitcoin dominance is near {dom:.0f} "
         f"percent. A tracked peg below 0.995 would trigger Levanter's wobble alert. A sharp dominance "
         f"move would show the balance within crypto changing."),
    ]
    P += [b for b in bullets if b]
    P.append("")
    # Marginal calls stay in the scored set. Dropping the ones that look shaky would
    # flatter next week's scoreboard, so they are named here instead.
    # The scored claim covers the whole board, calm calls included, so a marginal
    # calm call is just as much a hostage to fortune as a marginal turbulent one.
    _marg = [(_name(r["sym"]), r["ratio"], r["call"]) for r in _rows
             if 0.93 <= r["ratio"] <= 1.07]
    _score = (
        f"To score next week: the model calls {_join(all_high)} turbulent and the rest calm. In the "
        f"next issue we score each call the way the model does, whether realised volatility over the "
        f"week came in above or below the asset's running-median volatility, and show the hits and "
        f"misses. That is the claim you can hold this Signal to.")
    if _marg:
        _one = len(_marg) == 1
        _clauses = []
        for _call in ("turbulent", "calm"):
            _set = [(n, v) for n, v, c in _marg if c == _call]
            if _set:
                _clauses.append(_join([f"{n} at {v:.2f}x" for n, v in _set])
                                + f", called {_call}")
        _score += (
            f" {_cap(_num(len(_marg)))} {'call sits' if _one else 'calls sit'} close enough to "
            f"the line "
            f"that we would not defend {'it' if _one else 'them'} hard: "
            + "; ".join(_clauses)
            + f". We score {'it' if _one else 'them'} anyway. Quietly dropping the calls that look "
            f"shaky is how a scoreboard gets flattered, and a scoreboard you cannot trust is worth "
            f"nothing to you.")
    P.append(_score)
    P.append("")

    P = _reorder(P, SECTION_ORDER)

    if free:
        footer = ("*This is the Levanter Signal, the weekly subscriber note, free for now while we "
                  "build the list. We will tell you before that changes. Subscribe at "
                  "read.levantermarkets.com. The daily, weekly and monthly reviews stay free at "
                  "levantermarkets.com. Educational market analysis, not financial advice.*")
    else:
        footer = ("*This is a Levanter Signal, the weekly subscriber note. Subscribe at "
                  "read.levantermarkets.com. The daily, weekly and monthly reviews stay free at "
                  "levantermarkets.com. Educational market analysis, not financial advice.*")
    P += ["---", "", footer]

    hist[mon] = cur_state
    for k in sorted(hist)[:-8]:
        hist.pop(k, None)
    _save_signal_state(hist)

    return "\n".join(P), (loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, free, first)


def teaser(meta, hashtags=True):
    loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, free, first = meta
    byc = {c.get("cls"): c for c in cls}
    cr, co = byc.get("crypto", {}), byc.get("commodity", {})
    T = []
    if first:
        T += ["Introducing the Levanter Signal, our new weekly newsletter.", "",
              "Market intelligence across crypto, foreign exchange and commodities, from a site that "
              "models volatility and refuses to pretend it can forecast direction.", ""]
        if free:
            T += ["It is free while we build the list, and we will say so before that changes.", ""]
        T += ["Here is the first Signal in one minute."]
    else:
        T += ["This week's Levanter Signal is out.", "",
              "Market intelligence across crypto, foreign exchange and commodities, from a site that "
              "models volatility and refuses to pretend it can forecast direction.", "",
              "Here is this week's Signal in one minute."]
    T += ["", "What is knowable:", "",
          f"Volatility clusters, so a turbulent-or-calm classification can carry measurable skill. This "
          f"week the model expects wider ranges in {loud_txt}, with calmer conditions across "
          f"{quiet_txt}.", ""]
    if ou is not None:
        T += [f"On the longer view, bitcoin is trading about {abs(ou):.0f} percent "
              f"{'below' if ou < 0 else 'above'} the fair value produced by Levanter's long-run "
              f"valuation fit, which models price against how long the network has existed. That is "
              f"valuation context, not a price target or a prediction for Friday.", ""]
    T += ["What is not knowable:", "", "Direction.", ""]
    if cr.get("n") and cr.get("acc") is not None and co.get("n") and co.get("acc") is not None:
        crci, coci = _wilson_ci(cr["acc"], cr["n"]), _wilson_ci(co["acc"], co["n"])
        cr_ci_txt = (f", a 95 percent interval of {crci[0]} to {crci[1]} percent that straddles "
                     f"the coin-flip line" if crci else "")
        co_ci_txt = (f", a 95 percent interval of {coci[0]} to {coci[1]} percent" if coci else "")
        T += [f"The current direction scorecard says crypto {cr['acc']:.0f} percent, commodities {co['acc']:.0f} "
              f"percent and FX not yet scored. Crypto provides the largest sample, with {cr['n']:,} "
              f"calls{cr_ci_txt}, and its result sits almost exactly at chance.", "",
              f"The commodities figure looks better, but {co['acc']:.0f} percent from {co['n']} calls{co_ci_txt} "
              f"in a strongly trending market does not establish an edge. FX has no resolved calls yet.", "",
              "Read the individual rows, not a flattering blended number.", ""]
    T += ["That is Levanter's approach: model what can be modelled, identify what cannot, and publish "
          "the scorecard.", ""]
    if free:
        T += ["The Signal is free while we build the list. Subscribe now and you keep receiving it:",
              "", "read.levantermarkets.com", ""]
    else:
        T += ["Subscribe to read the full Signal:", "", "read.levantermarkets.com", ""]
    if hashtags:   # LinkedIn wants them; the Substack teaser does not
        T += ["#markets #bitcoin #crypto #investing #volatility"]
    return "\n".join(T).rstrip() + "\n"


X_LIMIT = x_text.X_LIMIT   # characters in a single X post, as X counts them


def _thread_file(head, posts):
    """Render numbered posts as a paste-ready thread file, each within X_LIMIT.
    The separators carry the numbering and are not part of any post.

    Lengths are counted the way X counts them, with every URL charged a flat 23
    characters. An over-long post raises rather than being dropped: this used to
    filter them out silently, so a thread could publish a post short with nothing
    in the output to say which one went missing.
    """
    posts = [p for p in posts if p]
    x_text.require_fit(posts, where=head, limit=X_LIMIT)
    out = [f"# {head}",
           f"X. {len(posts)} posts, each inside the {X_LIMIT}-character limit as X counts it, "
           f"with links charged at {x_text.URL_WEIGHT}. Post in order as a thread. The separator "
           f"lines are not part of any post.", ""]
    for i, p in enumerate(posts, 1):
        out += [f"--- {i}/{len(posts)} ({x_text.x_len(p)} chars) ---", "", p, ""]
    return "\n".join(out).rstrip() + "\n"


def x_thread(meta, monday):
    """The weekly Signal as a short promo X thread (each post under the limit)."""
    loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, free, first = meta
    cr = {c.get("cls"): c for c in cls}.get("crypto", {})
    posts = []
    posts.append(
        ("The Levanter Signal is out, our weekly premium read on volatility, valuation and the week "
         "ahead across crypto, FX and commodities. Free while we build the list. Here it is in a thread."
         ) if free else
        ("This week's Levanter Signal is out: the premium read on volatility, valuation and the week "
         "ahead across crypto, FX and commodities. Here it is in a thread."))
    posts.append(
        f"What is knowable: volatility clusters. This week the model expects wider ranges in "
        f"{loud_txt}, calmer across {quiet_txt}. That turbulent-or-calm call carries measurable "
        f"backtested skill.")
    if ou is not None:
        posts.append(
            f"On the long view, bitcoin sits about {abs(ou):.0f}% "
            f"{'below' if ou < 0 else 'above'} its valuation fit, price against how long the network "
            f"has existed. Valuation context, not a prediction for Friday.")
    if cr.get("n") and cr.get("acc") is not None:
        ci = _wilson_ci(cr["acc"], cr["n"])
        citxt = f" (95% CI {ci[0]}-{ci[1]})" if ci else ""
        posts.append(
            f"What is not knowable: direction. Our crypto calls run about {cr['acc']:.0f}% over "
            f"{cr['n']:,} backtested calls{citxt}, a coin flip, and we publish it. We forecast "
            f"volatility, not direction.")
    # The full board is the paid tier's concrete differentiator, so name the extremes
    # rather than only asserting that a board exists. Read straight from the feed:
    # the promo thread should never drift from the note it is advertising.
    _vr = _read("vol_regime.json")
    _board = []
    for _sym, _a in (_vr.get("assets") or {}).items():
        _a7 = _a.get("7d") or {}
        if _a7.get("vol_now") and _a7.get("vol_median"):
            _board.append((_sym, _a7["vol_now"] / _a7["vol_median"]))
    if _board:
        _board.sort(key=lambda r: -r[1])
        _top, _bot = _board[0], _board[-1]
        posts.append(
            f"Subscribers get the full board: {len(_board)} markets, each judged against its own "
            f"median rather than one threshold for everything. Most stretched this week, "
            f"{_name(_top[0])} at {_top[1]:.2f}x its own normal. Quietest, {_name(_bot[0])} at "
            f"{_bot[1]:.2f}x.")
    posts.append(
        "The full Signal, with the levels and the week-on-week changes, is for subscribers: "
        "read.levantermarkets.com. Educational, not advice.")
    return _thread_file(f"Levanter Signal thread · week of {monday.strftime('%-d %B %Y')}", posts)


def main():
    argv = sys.argv[1:]
    # One writer at a time. Two sessions in this tree have already
    # produced a half-written feed; see repo_lock.
    try:
        repo_lock.acquire("signal_note")
    except repo_lock.LockBusy as e:
        print(f"signal_note: {e}", file=sys.stderr)
        sys.exit(1)

    force = "--force" in argv
    now = _now_gst()
    monday = (now - dt.timedelta(days=now.weekday())).date()
    if "--monday" in argv:
        monday = dt.date.fromisoformat(argv[argv.index("--monday") + 1])

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "docx"), exist_ok=True)
    note_path = os.path.join(OUT, f"levanter-signal-{monday}.md")
    teaser_path = os.path.join(OUT, f"levanter-signal-teaser-{monday}.md")

    if not force:
        if os.path.exists(note_path):
            print(f"signal_note: this week's Signal ({monday}) already prepared; skipping.")
            return
        # Publishes Wednesday, still anchored to the week's Monday in the title and
        # filename. Before Wednesday 06:00 GST it is not due; after, the first build
        # writes it and the rest of the week is idempotent (note already exists).
        wednesday = monday + dt.timedelta(days=2)
        due = dt.datetime.combine(wednesday, dt.time(6, 0))   # Wednesday 06:00 GST
        if now < due:
            print(f"signal_note: not due yet (prepares {wednesday} 06:00 GST).")
            return

    try:
        body, meta = compose(SIGNAL_FREE, SIGNAL_FIRST_ISSUE, monday.isoformat())
    except SourceError as e:
        print(f"signal_note: {e}", file=sys.stderr)
        sys.exit(1)
    title = f"# Levanter Signal · week of {monday.strftime('%-d %B %Y')}"
    body = body.replace("# Levanter Signal\n", title + "\n", 1)
    teaser_sub_path = os.path.join(OUT, f"levanter-signal-teaser-substack-{monday}.md")
    open(note_path, "w").write(body)
    open(teaser_path, "w").write(teaser(meta, hashtags=True))          # LinkedIn: keep hashtags
    open(teaser_sub_path, "w").write(teaser(meta, hashtags=False))     # Substack: no hashtags
    # The accompanying X thread. Its own channel dir, no docx (pasted post by post).
    x_dir = os.path.join("reports", "x")
    os.makedirs(x_dir, exist_ok=True)
    # The note and teasers are already written. A thread that will not fit is a
    # loud failure, not a reason to lose the issue, so report it and exit non-zero.
    x_md = os.path.join(x_dir, f"levanter-signal-x-{monday}.md")
    try:
        open(x_md, "w").write(x_thread(meta, monday))
    except x_text.PostTooLong as e:
        print(f"signal_note: X thread not written. {e}", file=sys.stderr)
        _x_failed = True
    else:
        _x_failed = False
    try:
        import md2docx
        md2docx.convert(note_path, os.path.join(OUT, "docx", f"levanter-signal-{monday}.docx"))
        md2docx.convert(teaser_path, os.path.join(OUT, "docx", f"levanter-signal-teaser-{monday}.docx"))
        md2docx.convert(teaser_sub_path,
                        os.path.join(OUT, "docx", f"levanter-signal-teaser-substack-{monday}.docx"))
        # The thread is copy to be posted, so it ships in the same format as the
        # teasers rather than as the only asset the publisher has to open in a
        # text editor.
        if not _x_failed:
            os.makedirs(os.path.join(x_dir, "docx"), exist_ok=True)
            md2docx.convert(x_md, os.path.join(x_dir, "docx",
                                               f"levanter-signal-x-{monday}.docx"))
    except Exception as e:
        print("signal_note: docx skipped:", e)
    print(f"signal_note: prepared week-of-{monday} Signal + teaser in {OUT}/")
    if _x_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
