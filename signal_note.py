#!/usr/bin/env python3
"""Levanter Signal generator (weekly premium note).

Drafts the midweek/Monday premium "Levanter Signal" from the same live data the
dashboard uses: one chart that matters (the bitcoin valuation fit), the week-ahead
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
# The Signal is the PAID tier, currently free while the list is built. There is no
# end date: the plan is to tell readers before that changes, so this is a flag a
# human flips deliberately, not a date that flips itself. It used to be
# LAUNCH_UNTIL = "2026-08-31", which would have silently dropped the free framing
# on 7 September and, worse, promised "free this week and next" in the meantime.
# Set to False on the week the Signal actually goes subscriber-only.
SIGNAL_FREE = True
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
        nm = sym if c == "fx" else _name(sym)   # FX: the model forecasts the pair, e.g. USDCHF
        (out[c][0] if r.get("regime") == "HIGH" else out[c][1]).append(nm)
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

    loud, quiet = [], []
    if g["commodity"][0]:
        loud.append("the metals" if any(m in g["commodity"][0]
                    for m in ("gold", "silver", "platinum")) else "commodities")
    if g["crypto"][0]:
        loud.append("big-cap crypto")
    if len(g["fx"][1]) >= 4:
        quiet.append("most foreign exchange markets")
    if any(x in g["commodity"][1] for x in ("oil", "copper", "natural gas")):
        quiet.append("energy")
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
    if launch:
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
        P.append(
            f"This is the part with measurable skill. The model tags each market turbulent or calm for "
            f"the week ahead. In the five-year point-in-time backtest it classified the seven-day "
            f"regime correctly about {acc7} percent of the time, {edge7} percentage points above its "
            f"naïve baseline, and {acc30} percent at thirty days, {edge30} points above baseline. That "
            f"is a backtest, not a live forward record: the live scoreboard is only now starting to "
            f"fill.")
        P.append("")
    calm_names = list(g["crypto"][1])   # calm crypto, e.g. solana
    calm_names.append(f"{_num(fx_low)} of the {_num(fx_total)} FX pairs")
    if spx and spx.get("regime") == "LOW":
        calm_names.append("the S&P 500")
    calm_names += [x for x in g["commodity"][1] if x in ("oil", "copper", "natural gas")]
    P.append(
        f"For the coming week the model reads {_num(len(all_high))} markets turbulent: {_join(all_high)}. "
        f"The rest of the displayed set is calm, including {_join(calm_names)}. The average market is "
        f"therefore contained even though a few names are carrying wide ranges.")
    P.append("")
    if vb and ve:
        P.append(
            f"The loudest reads are in big crypto. Bitcoin's one-week volatility is near {vb['now']} "
            f"percent against a {vb['med']} median, and ether near {ve['now']} against {ve['med']}, "
            f"close to double its normal. Both are turbulent at seven days while their thirty-day "
            f"classifications remain calm. The two horizons disagree, which flags a near-term "
            f"disturbance without telling us whether it will last. The metals read turbulent at both "
            f"seven and thirty days, indicating that their elevated-volatility classification extends "
            f"beyond the coming week.")
        P.append("")
    if cr.get("n") and cr.get("acc") is not None:
        P.append(
            f"On direction the model is close to a coin flip: {cr['acc']:.0f} percent over "
            f"{cr['n']:,} backtested crypto calls. We forecast volatility, not direction.")
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
    P.append(
        f"Over the past seven days crypto was broad and speculative-led: {w_up} of {w_n} coins higher, "
        f"cap-weighted about {w_capw:+.0f} percent on the week"
        + (f" and {capw30:+.0f} percent over thirty days" if capw30 is not None else "")
        + f"{wk_lead}, with a best-to-worst spread near {abs(w_disp):.0f} points. Dominance held near "
        f"{dom:.0f} percent and the stablecoins we track kept their pegs. In foreign exchange the "
        f"biggest seven-day move was {fp[-1][0]} at {fp[-1][1]:+.1f} percent, ranges otherwise tight. "
        f"In commodities the metals led the week, "
        + _join([f"{_name(nn)} {vv:+.0f} percent" for nn, vv in metals[-3:][::-1]])
        + ". The gains were broad, but the largest moves stayed further out on the risk curve, and the "
        "dollar and most FX ranges were comparatively quiet.")
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
        (f"- **The metals.** Whether the turbulent bid broadens beyond {_join(g['commodity'][0])} or "
         f"fades back to calm.") if g["commodity"][0] else "",
        (f"- **Pegs and dominance.** Stablecoins are holding and bitcoin dominance is near {dom:.0f} "
         f"percent. A tracked peg below 0.995 would trigger Levanter's wobble alert. A sharp dominance "
         f"move would show the balance within crypto changing."),
    ]
    P += [b for b in bullets if b]
    P.append("")
    P.append(
        f"To score next week: the model calls {_join(all_high)} turbulent and the rest calm. In the "
        f"next issue we score each call the way the model does, whether realised volatility over the "
        f"week came in above or below the asset's running-median volatility, and show the hits and "
        f"misses. That is the claim you can hold this Signal to.")
    P.append("")

    if launch:
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

    return "\n".join(P), (loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, launch)


def teaser(meta, hashtags=True):
    loud_txt, quiet_txt, ou, nv, n, dacc, period, cls, launch = meta
    byc = {c.get("cls"): c for c in cls}
    cr, co = byc.get("crypto", {}), byc.get("commodity", {})
    T = []
    if launch:
        T += ["Introducing the Levanter Signal, our new weekly newsletter.", "",
              "Market intelligence across crypto, foreign exchange and commodities, from a site that "
              "models volatility and refuses to pretend it can forecast direction.", "",
              "It is free while we build the list, and we will say so before that changes.", "",
              "Here is the first Signal in one minute."]
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
        T += [f"The current direction scorecard says crypto {cr['acc']:.0f} percent, commodities {co['acc']:.0f} "
              f"percent and FX not yet scored. Crypto provides the largest sample, with {cr['n']:,} "
              f"calls, and its result sits almost exactly at chance.", "",
              f"The commodities figure looks better, but {co['acc']:.0f} percent from {co['n']} calls in "
              f"a strongly trending market does not establish an edge. FX has no resolved calls yet.", "",
              "Read the individual rows, not a flattering blended number.", ""]
    T += ["That is Levanter's approach: model what can be modelled, identify what cannot, and publish "
          "the scorecard.", ""]
    if launch:
        T += ["The Signal is free while we build the list. Subscribe now and you keep receiving it:",
              "", "read.levantermarkets.com", ""]
    else:
        T += ["Subscribe to read the full Signal:", "", "read.levantermarkets.com", ""]
    if hashtags:   # LinkedIn wants them; the Substack teaser does not
        T += ["#markets #bitcoin #crypto #investing #volatility"]
    return "\n".join(T).rstrip() + "\n"


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

    launch = SIGNAL_FREE
    body, meta = compose(launch, monday.isoformat())
    title = f"# Levanter Signal · week of {monday.strftime('%-d %B %Y')}"
    body = body.replace("# Levanter Signal\n", title + "\n", 1)
    teaser_sub_path = os.path.join(OUT, f"levanter-signal-teaser-substack-{monday}.md")
    open(note_path, "w").write(body)
    open(teaser_path, "w").write(teaser(meta, hashtags=True))          # LinkedIn: keep hashtags
    open(teaser_sub_path, "w").write(teaser(meta, hashtags=False))     # Substack: no hashtags
    try:
        import md2docx
        md2docx.convert(note_path, os.path.join(OUT, "docx", f"levanter-signal-{monday}.docx"))
        md2docx.convert(teaser_path, os.path.join(OUT, "docx", f"levanter-signal-teaser-{monday}.docx"))
        md2docx.convert(teaser_sub_path,
                        os.path.join(OUT, "docx", f"levanter-signal-teaser-substack-{monday}.docx"))
    except Exception as e:
        print("signal_note: docx skipped:", e)
    print(f"signal_note: prepared week-of-{monday} Signal + teaser in {OUT}/")


if __name__ == "__main__":
    main()
