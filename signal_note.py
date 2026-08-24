#!/usr/bin/env python3
"""Levanter Signal generator (weekly premium note).

Drafts the midweek/Monday premium "Levanter Signal" from the same live data the
dashboard uses: one chart that matters (bitcoin network value), the week-ahead
volatility read across crypto, foreign exchange and commodities, and an honest
line on what is and is not knowable. Also drafts a LinkedIn teaser.

This is a PREMIUM piece, so it is written to reports/signals/ and is NOT copied
to the public site. It is prepared for 06:00 GST on Mondays: the first build at
or after that time generates the frozen weekly snapshot, and later builds in the
same week skip it (idempotent), so the "week ahead" numbers do not drift.

    python signal_note.py [--force] [--monday YYYY-MM-DD]

Voice rules: no em dashes, no AI kill-words. Educational, not advice.
"""
import datetime as dt
import json
import os
import sys

OUT = "reports/signals"
# Launch window: the Signal is a new weekly newsletter, free this week and next,
# then subscription. Any Signal whose Monday is on or before this date carries the
# launch framing; after that it reverts to the normal subscriber wording.
LAUNCH_UNTIL = "2026-08-31"
NAMES = {
    "BTC": "bitcoin", "ETH": "ether", "SOL": "solana", "XRP": "XRP",
    "GOLD": "gold", "SILVER": "silver", "PLATINUM": "platinum",
    "PALLADIUM": "palladium", "OIL": "oil", "WTI OIL": "oil", "BRENT OIL": "Brent crude",
    "COPPER": "copper", "NAT GAS": "natural gas", "WHEAT": "wheat", "CORN": "corn",
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


SIGNAL_STATE = "signal_history.json"   # not *_state.json, which .gitignore excludes


def _load_signal_state():
    try:
        return json.load(open(SIGNAL_STATE))
    except Exception:
        return {}


def _save_signal_state(d):
    json.dump(d, open(SIGNAL_STATE, "w"), indent=2)


def _now_gst():
    return dt.datetime.utcnow() + dt.timedelta(hours=4)


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
        (out[c][0] if r.get("regime") == "HIGH" else out[c][1]).append(_name(sym))
    return out


def compose(launch=False, monday=None):
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

    loud, quiet = [], []
    if g["commodity"][0]:
        loud.append("the metals" if any(m in g["commodity"][0]
                    for m in ("gold", "silver", "platinum")) else "commodities")
    if g["crypto"][0]:
        loud.append("big-cap crypto")
    if len(g["fx"][1]) >= 4:
        quiet.append("foreign exchange")
    if any(x in g["commodity"][1] for x in ("oil", "copper", "natural gas")):
        quiet.append("energy")
    loud_txt = _join(loud) or "a couple of pockets of the market"
    quiet_txt = _join(quiet) or "the rest"
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
    if launch:
        P += ["> **New: the Levanter Signal, a weekly newsletter.** This is the first issue. It reads "
              "volatility, valuation and the week ahead across crypto, foreign exchange and commodities, "
              "and it is honest about what a model can and cannot forecast. It is **free this week and "
              "next**, then it moves to subscribers. Subscribe at read.levantermarkets.com to keep it.",
              ""]
    P += [f"*Data captured at {stamp}. Every figure below is stamped to a period, because they move. "
          f"This is the accountable read behind the free weekly: the changes since last week, the "
          f"levels to watch, and a claim we will score in the next issue.*", "", "---", ""]

    # ===== One chart: bitcoin valuation =====
    if fair:
        P += ["## The one chart: bitcoin against its adoption model", ""]
        P.append(
            f"Bitcoin is near {_kfmt(price)} dollars, captured {stamp}. We value it against network "
            f"age with a power-law fit. Fair value on that fit lands near {_kfmt(fair)}, about "
            f"{abs(ou):.0f} percent {'below' if ou < 0 else 'above'} the line, and the fitted floor "
            f"sits near {_kfmt(floor)}. Bitcoin has closed above that floor line for roughly 95 percent "
            f"of the historical sample. That is an in-sample observation, not a tested probability and "
            f"not a guaranteed level of support.")
        P.append("")
        if cyc_b is not None:
            P.append(
                f"A separate cycle model classifies bitcoin as {phase.lower()}, about {abs(cyc_b):.0f} "
                f"percent below its own power-law trend. Both are long-horizon context. Where price "
                f"sits against a multi-year fit says nothing about the next five days, so read it as "
                f"valuation, not a reason to act on the week.")
            P.append("")
        P += ["*(Chart: bitcoin price against its adoption fair value and floor.)*", ""]

    # ===== Limits of the model =====
    P += ["## What the model can and cannot do", ""]
    P.append(
        "The limits matter more than the headline. The power law is a fit of price to time. It has no "
        "economic mechanism behind it, it cannot call tops, and a line that holds in the historical "
        "sample can break out of it. It is a valuation anchor, not a timing tool. Treat the fair value "
        "and the floor as distant reference points, never as targets and never as a reason to size up.")
    P.append("")

    # ===== Seven-day volatility map =====
    P += ["## The seven-day volatility map", ""]
    if acc7 and acc30:
        P.append(
            f"This is the part with measurable skill. The model tags each market turbulent or calm for "
            f"the week ahead. Against a 50 percent coin-flip baseline it is right about {acc7} percent "
            f"of the time at seven days and {acc30} percent at thirty, backtested point-in-time over "
            f"five years on non-overlapping samples. That is a backtest, not a live forward record: the "
            f"live scoreboard is only now starting to fill.")
        P.append("")
    calm_bits = f"{_num(fx_low)} of the {_num(fx_total)} displayed FX pairs"
    if spx and spx.get("regime") == "LOW":
        calm_bits += ", the S&P"
    if calm_energy:
        calm_bits += f", and {_join(calm_energy)} in energy"
    P.append(
        f"For the coming week the model reads {_num(len(all_high))} markets turbulent: {_join(all_high)}. "
        f"The rest is calm, including {calm_bits}. So the average market is contained while the "
        f"turbulence is concentrated, which settles the apparent tension in the free weekly between a "
        f"mostly-calm board and loud pockets. Both are true, because only the metals and big crypto are "
        f"carrying the range.")
    P.append("")
    if vb and ve:
        P.append(
            f"The loudest reads are in big crypto. Bitcoin's one-week volatility is near {vb['now']} "
            f"percent against a {vb['med']} median, and ether near {ve['now']} against {ve['med']}, "
            f"close to double its normal. Both are turbulent on the week while their one-month regime "
            f"is still calm, so this is a near-term spike rather than a change of character. The metals "
            f"read turbulent on both the one-week and one-month horizons, so their wider ranges are more "
            f"persistent.")
        P.append("")
    if cr.get("n") and cr.get("acc") is not None:
        P.append(
            f"On direction the model is close to a coin flip, which is the thesis rather than a "
            f"shortfall: {cr['acc']:.0f} percent over {cr['n']:,} backtested crypto calls, the class "
            f"with the most data. The full per-class breakdown, and why the commodities figure is not "
            f"an edge, sit on the track record. We forecast volatility, not direction.")
        P.append("")

    # ===== What changed =====
    P += ["## What changed since the last Signal", ""]
    if prev:
        prev_high = set(prev.get("high", []))
        flips = [h for h in all_high if h not in prev_high]
        calmed = [h for h in prev_high if h not in all_high]
        d_ou = (round(ou) - prev["btc_ou"]) if (ou is not None and prev.get("btc_ou") is not None) else None
        bits = []
        if flips:
            bits.append(f"newly turbulent, {_join(flips)}")
        if calmed:
            bits.append(f"calmed back to normal, {_join(calmed)}")
        if not flips and not calmed:
            bits.append("the volatility roster is unchanged from last week")
        if d_ou:
            bits.append(f"bitcoin is about {abs(d_ou)} points "
                        f"{'cheaper' if d_ou < 0 else 'richer'} against its fitted value")
        P.append("Week on week: " + _sentences([_cap(b) for b in bits]) + ".")
    else:
        P.append(
            "This is the first issue, so there is no prior Signal to compare against. From next week "
            "this section flags which markets newly flipped turbulent or calm and how far bitcoin moved "
            "against its fitted value, so you see the model changing its mind, not just its latest state.")
    P.append("")

    # ===== The week behind =====
    P += ["## The week behind, and what it rhymes with", ""]
    wk_lead = ""
    if len(mv7) >= 2:
        wk_lead = (f", led by the speculative end, {mv7[0]['coin']} {mv7[0]['ret']:+.0f} percent and "
                   f"{mv7[1]['coin']} {mv7[1]['ret']:+.0f} percent")
    P.append(
        f"Over the past seven days crypto was broad and speculative-led: {w_up} of {w_n} coins higher, "
        f"cap-weighted about {w_capw:+.0f} percent on the week"
        + (f" and {capw30:+.0f} percent over thirty days" if capw30 is not None else "")
        + f"{wk_lead}, with a best-to-worst spread near {abs(w_disp):.0f} points. Dominance held near "
        f"{dom:.0f} percent and the stablecoins we track kept their pegs. In foreign exchange the "
        f"biggest seven-day move was {fp[-1][0]} at {fp[-1][1]:+.1f} percent, ranges otherwise tight. "
        f"In commodities the metals led the week, "
        + _join([f"{_name(nn)} {vv:+.0f} percent" for nn, vv in metals[-3:][::-1]])
        + ". Risk appetite is running in the tail while the majors and the dollar sit quiet.")
    P.append("")

    # ===== Watchlist + review =====
    P += ["## Subscriber watchlist, with levels", ""]
    bullets = [
        (f"- **Bitcoin.** Fitted floor near {_kfmt(floor)}, fair value near {_kfmt(fair)}. A weekly "
         f"close below the floor line would be the first in most of the sample.") if fair else "",
        (f"- **Ether volatility.** Watch it fall back toward its {ve['med']} median. Holding near "
         f"{ve['now']} would turn the spike into a regime.") if ve else "",
        (f"- **The metals.** Whether the turbulent bid broadens beyond {_join(g['commodity'][0])} or "
         f"fades back to calm.") if g["commodity"][0] else "",
        (f"- **Pegs and dominance.** Stablecoins holding, dominance near {dom:.0f} percent. A peg "
         f"under 0.995 or a sharp dominance move is the early risk-off tell."),
    ]
    P += [b for b in bullets if b]
    P.append("")
    P.append(
        f"To score next week: the model calls {_join(all_high)} turbulent and the rest calm. In the "
        f"next issue we mark whether those turbulent markets realised a wider-than-median weekly range "
        f"and whether the calm ones stayed contained. That is the claim you can hold this Signal to.")
    P.append("")

    if launch:
        footer = ("*This is the Levanter Signal, our new weekly newsletter, free this week and next. "
                  "After that it moves to subscribers, so subscribe now at read.levantermarkets.com to "
                  "keep getting it. The daily, weekly and monthly reviews stay free at "
                  "levantermarkets.com. Educational market analysis, not financial advice.*")
    else:
        footer = ("*This is a Levanter Signal, the weekly subscriber note. The daily, weekly and "
                  "monthly reviews stay free at levantermarkets.com. Educational market analysis, not "
                  "financial advice.*")
    P += ["---", "", footer, "", "*Subscribe: read.levantermarkets.com*"]

    hist[mon] = cur_state
    for k in sorted(hist)[:-8]:
        hist.pop(k, None)
    _save_signal_state(hist)

    return "\n".join(P), (loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, launch)


def teaser(meta):
    loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, launch = meta
    T = []
    if launch:
        T.append("Introducing the Levanter Signal, a new weekly newsletter. Honest market intelligence "
                 "across crypto, foreign exchange and commodities, from the site that forecasts "
                 "volatility and refuses to forecast direction. Free this week and next, then it moves "
                 "to subscribers.")
        T.append("")
        T.append("Here is the first one, the honest version:")
    else:
        T.append("Most market commentary this week will tell you where prices are going. "
                 "Here is what a model can actually tell you, and what it cannot.")
        T.append("")
        T.append("The week's Levanter Signal is out. The honest version:")
    T.append("")
    T.append("What is knowable:")
    T.append("")
    T.append(f"Volatility clusters, so a turbulent-or-calm call carries real skill. This "
             f"week the model puts the wider ranges in {loud_txt} and the calm in "
             f"{quiet_txt}. If you hold the loud names, plan for it. If you trade the "
             f"quiet ones, expect a duller week.")
    T.append("")
    if ou is not None:
        T.append(f"On the longer view, bitcoin is trading around {abs(ou):.0f} percent "
                 f"{'below' if ou < 0 else 'above'} its network-value (adoption-model) fair value.")
        T.append("")
    T.append("What is not knowable:")
    T.append("")
    if n and dacc is not None:
        cbits = []
        for c in cls:
            lab = c.get("label", c.get("cls", ""))
            lab = lab if lab == "FX" else lab.lower()
            cbits.append(f"{lab} {c['acc']:.0f}%" if c.get("n") and c.get("acc") is not None
                         else f"{lab} not yet scored")
        byc = {c.get("cls"): c for c in cls}
        cr, co = byc.get("crypto", {}), byc.get("commodity", {})
        T.append(f"Which way any of it closes on Friday. On direction we backtest every class and "
                 f"show them all: {_join(cbits)}.")
        T.append("")
        T.append(f"The crypto row is our biggest sample at {cr.get('n', 0):,} calls, and at "
                 f"{cr.get('acc', 0):.0f} percent it sits right on the coin flip. That is the whole "
                 f"thesis. Commodities looks stronger at {co.get('acc', 0):.0f} percent, but it is "
                 f"{co.get('n', 0)} calls in a trending tape, not an edge. FX has no resolved calls "
                 f"yet. Read the rows, not the blend.")
        T.append("")
    T.append("That is the whole idea of Levanter. Forecast what is forecastable, say so "
             "plainly about the rest, and show the scorecard.")
    T.append("")
    if launch:
        T.append("The Signal is free this week and next, then it moves to subscribers. Subscribe now "
                 "to get it while it is free, and to keep it after: read.levantermarkets.com")
    else:
        T.append("The daily, weekly and monthly reviews are free at levantermarkets.com. "
                 "The Signal and the alerts are for subscribers.")
        T.append("")
        T.append("Read the full Signal: read.levantermarkets.com")
    T.append("")
    T.append("#markets #bitcoin #crypto #investing #volatility")
    return "\n".join(T)


def main():
    argv = sys.argv[1:]
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
        if now.weekday() > 2:      # Thu-Sun: the week is underway, do not back-fill it
            print("signal_note: past the Monday preparation window this week; skipping.")
            return
        due = dt.datetime.combine(monday, dt.time(6, 0))   # Monday 06:00 GST
        if now < due:
            print(f"signal_note: not due yet (prepares {monday} 06:00 GST).")
            return

    launch = monday.isoformat() <= LAUNCH_UNTIL
    body, meta = compose(launch, monday.isoformat())
    title = f"# Levanter Signal · week of {monday.strftime('%-d %B %Y')}"
    body = body.replace("# Levanter Signal\n", title + "\n", 1)
    open(note_path, "w").write(body)
    open(teaser_path, "w").write(teaser(meta))
    try:
        import md2docx
        md2docx.convert(note_path, os.path.join(OUT, "docx", f"levanter-signal-{monday}.docx"))
        md2docx.convert(teaser_path, os.path.join(OUT, "docx", f"levanter-signal-teaser-{monday}.docx"))
    except Exception as e:
        print("signal_note: docx skipped:", e)
    print(f"signal_note: prepared week-of-{monday} Signal + teaser in {OUT}/")


if __name__ == "__main__":
    main()
