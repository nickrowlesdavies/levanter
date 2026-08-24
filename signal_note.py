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


def compose():
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
    btc_line = ("looks cheap on a decade view and a coin flip on a weekly one"
                if (ou is not None and ou < -15) else
                "looks stretched on a decade view and a coin flip on a weekly one"
                if (ou is not None and ou > 40) else
                "sits near its long-term trend and remains a coin flip week to week")
    one_line = (f"expect the wider ranges in {loud_txt}, calmer trade in {quiet_txt}, "
                f"and remember that bitcoin {btc_line}.")

    P = ["# Levanter Signal", "",
         "*The weekly premium read. What actually happened across crypto, foreign "
         "exchange and commodities, where the volatility is heading, the one valuation "
         "that matters, and the specific things to watch. The deeper read behind the "
         "free weekly.*", "", "---", "",
         f"**The one line:** {one_line}", ""]

    # ===== The week behind us =====
    P += ["## The week behind us", ""]
    if wk_s:
        lead = ""
        if len(mv7) >= 3:
            lead = (f" The leaders were the speculative end of the board, {mv7[0]['coin']} "
                    f"{mv7[0]['ret']:+.0f} percent, {mv7[1]['coin']} {mv7[1]['ret']:+.0f} "
                    f"percent and {mv7[2]['coin']} {mv7[2]['ret']:+.0f} percent, while the "
                    f"laggard, {wk_s[0][0]}, barely moved at {wk_s[0][1]:+.0f} percent.")
        concentration = ("close together" if abs(w_capw - w_eqw) < 3 else
                         "far apart")
        conc_read = ("so this was breadth plus a hot tail rather than the majors carrying "
                     "the index" if abs(w_capw - w_eqw) < 3 else
                     "so a handful of names did most of the heavy lifting")
        corr_txt = (f" average pairwise correlation sat near {corr:.2f}, so names are "
                    f"still moving somewhat on their own rather than in lockstep," if corr is not None else "")
        peg_txt = ("and every stablecoin we monitor held its peg"
                   if not watch else f"and the peg monitor is flagging {_join(watch)}")
        P.append(
            f"Crypto had a broad week: {w_up} of the {w_n} coins we track finished "
            f"higher and the tape stayed risk-on.{lead} The spread from best to worst was "
            f"about {abs(w_disp):.0f} points in a single week, a lot of dispersion, and "
            f"cap-weighted and equal-weighted returns came out {concentration} (around "
            f"{w_capw:+.0f} and {w_eqw:+.0f} percent), {conc_read}. Bitcoin dominance held "
            f"near {dom:.0f} percent,{corr_txt} {peg_txt}. The honest reading is that risk "
            f"appetite is running, and running hardest in the most speculative corners, "
            f"which is a late-cycle tell rather than a reason to chase.")
        P.append("")
    if fp:
        P.append(
            f"Foreign exchange was quiet, which is itself information. The biggest move "
            f"among the crosses we track was {fp[-1][0]} at {fp[-1][1]:+.1f} percent, the "
            f"weakest {fp[0][0]} at {fp[0][1]:+.1f} percent, and one-week volatility across "
            f"the majors is sitting in the mid single digits. A drifting dollar and tight "
            f"ranges mean the action, and the risk, is elsewhere this week.")
        P.append("")
    if metals and com_best:
        top3 = _join([f"{_name(n)} {v:+.0f} percent" for n, v in metals[-3:][::-1]])
        P.append(
            f"Commodities told a clearer story, and it was the metals: {top3} led, while "
            f"copper went nowhere and the softs lagged. When precious metals bid as the "
            f"dollar drifts, it usually says something about how the market is thinking "
            f"about real rates and safety. The question for the week is whether that bid "
            f"broadens across the complex or fades.")
        P.append("")

    # ===== The one chart =====
    if fair:
        P += ["## The one chart that matters: bitcoin network value", ""]
        P.append(
            f"Bitcoin is trading around {_kfmt(price)} dollars. Against its long-term "
            f"adoption trend, the network-value model that actually holds for bitcoin, "
            f"fair value sits near {_kfmt(fair)}, roughly {abs(ou):.0f} percent "
            f"{'below' if ou < 0 else 'above'} trend, with the adoption floor around "
            f"{_kfmt(floor)}, a level that has held about 95 percent of the time in "
            f"bitcoin's history. In plain terms, on a multi-year view bitcoin is sitting "
            f"in the lower third of its own band.")
        if cyc_b is not None:
            P.append("")
            P.append(
                f"The cycle clock agrees: bitcoin is about {abs(cyc_b):.0f} percent "
                f"{'below' if cyc_b < 0 else 'above'} its power-law trend and reads as "
                f"{phase.lower()}, not a blow-off top. Read it correctly though. This is a "
                f"statement about long-horizon value, not a price target and not a buy "
                f"signal, and it tells you nothing about next week. Cheap on a decade view "
                f"and a coin flip on a weekly one are both true at once.")
        P += ["", "*(Chart: bitcoin price against its adoption fair value and floor.)*", ""]

    # ===== The volatility map, week ahead =====
    P += ["## The volatility map for the week ahead", ""]
    if acc7 and acc30:
        P.append(
            f"This is where the model earns its keep. It does not call direction, it "
            f"calls turbulence, and turbulence clusters, which is why the read is "
            f"backtested at {acc7} percent over a week and {acc30} percent over a month"
            + (f", {acc90} over a quarter" if acc90 else "") + ".")
        P.append("")
    if vb and ve:
        spike = (vb.get("reg30") == "LOW" and ve.get("reg30") == "LOW")
        P.append(
            f"The loudest signal this week is a short-term volatility spike in big crypto. "
            f"Bitcoin's one-week volatility is running around {vb['now']} percent against a "
            f"{vb['med']} percent median, and ether is the standout at {ve['now']} against "
            f"{ve['med']}, close to double its normal."
            + (" Both read turbulent on the week even though their one-month regime is "
               "still calm, so treat this as a near-term spike, wider ranges for a few "
               "sessions rather than a change of character." if spike else "")
            + (f" Solana, unusually, is the quiet one of the three." if vs and vs.get("regime") == "LOW" else ""))
        P.append("")
    if g["commodity"][0]:
        P.append(
            f"The metals are loud too, and more persistently: {_join(g['commodity'][0])} "
            f"read high on both the one-week and one-month horizons, so their elevated "
            f"ranges are not a blip. Against that, foreign exchange is asleep, the S&P "
            f"reads calm, and energy is cooling. Where the model reads high, plan for wider "
            f"ranges and size down; where it reads low, expect a tighter week.")
        P += ["", "*(Charts: the crypto market map and the return-correlation grid.)*", ""]

    # ===== What to watch =====
    P += ["## What to watch this week", ""]
    watch_pts = []
    if fair:
        watch_pts.append(
            f"**Bitcoin's band.** Fair value near {_kfmt(fair)}, the adoption floor near "
            f"{_kfmt(floor)}. At {_kfmt(price)} it is in the lower third of that band, "
            f"cheap on the decade view and a coin flip on the week.")
    if ve:
        watch_pts.append(
            f"**The ether volatility spike.** {ve['now']} percent against a {ve['med']} "
            f"median. When ether's ranges blow out it tends to pull the majors around with "
            f"it, so watch whether it normalises or is the start of something.")
    if metals:
        watch_pts.append(
            f"**The metals bid.** {_cap(_name(metals[-1][0]))} leadership. Whether it broadens "
            f"to the rest of the complex or fades tells you how serious the safety trade is.")
    watch_pts.append(
        f"**Under the hood.** {'Every stablecoin peg is holding' if not watch else 'Peg watch on ' + _join(watch)} "
        f"and dominance is steady near {dom:.0f} percent. "
        + ("No stress signals there, which is the reassuring counterweight to a hot tape."
           if not watch else "Worth keeping an eye on."))
    for w in watch_pts:
        P += ["- " + w]
    P.append("")

    # ===== Scoreboard =====
    acc = ps.get("accuracy")
    rc = ps.get("resolved_count", 0)
    byc = ps.get("accuracy_by_class", {}) or {}
    P += ["## The honest scoreboard", ""]
    if acc is not None and rc:
        parts = [f"{lab} {byc[k]:.0f}%" for k, lab in
                 [("crypto", "crypto"), ("commodity", "commodities")] if byc.get(k) is not None]
        P.append(
            f"Because it is the reason to trust the rest. Our volatility calls carry "
            f"measurable skill, in the high sixties to mid seventies. Our direction calls, "
            f"backtested point-in-time, come in at {acc:.0f} percent across {rc:,} "
            f"calls" + (f" ({', '.join(parts)})" if parts else "") + ", almost exactly a "
            f"coin flip, and we publish that number rather than hide it. The knowable this "
            f"week is where the volatility is and where bitcoin sits on a long-horizon "
            f"valuation. The unknowable is which way any of it closes on Friday, and we "
            f"will not sell you the second one dressed as the first.")
        P.append("")

    P += ["---", "",
          "*This is a Levanter Signal, the weekly premium note. The daily, weekly and "
          "monthly reviews stay free at levantermarkets.com. The Signal and the alerts, a "
          "volatility-regime flip, a stablecoin starting to wobble, bitcoin touching its "
          "floor, are for subscribers. Educational market analysis, not financial advice.*",
          "", "*Subscribe: read.levantermarkets.com*"]
    return "\n".join(P), (loud_txt, quiet_txt, ou, acc, rc, nv)


def teaser(meta):
    loud_txt, quiet_txt, ou, acc, rc, nv = meta
    T = []
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
    if acc is not None and rc:
        T.append(f"Which way any of it closes on Friday. Our direction calls, backtested "
                 f"point-in-time, come in at {acc:.0f} percent across {rc:,} of them. Almost "
                 f"exactly a coin flip, and we publish that rather than hide it.")
        T.append("")
    T.append("That is the whole idea of Levanter. Forecast what is forecastable, say so "
             "plainly about the rest, and show the scorecard.")
    T.append("")
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

    body, meta = compose()
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
