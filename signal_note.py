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
    "PALLADIUM": "palladium", "OIL": "oil", "WTI OIL": "oil", "COPPER": "copper",
    "NAT GAS": "natural gas", "WHEAT": "wheat", "CORN": "corn",
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
    co = _read("commodities_map.json")
    cg = _read("cycle_gauge.json")
    nv = _read("btc_metcalfe.json")
    ps = _read("prediction_state.json")

    g = _vol_groups(vr)
    bt = vr.get("backtest", {})
    acc7 = (bt.get("7d") or {}).get("acc")
    acc30 = (bt.get("30d") or {}).get("acc")
    acc90 = (bt.get("90d") or {}).get("acc")

    # Loud vs quiet, for the one line.
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

    ou = nv.get("over_under_pct")
    read = nv.get("read", "")
    btc_line = ("looks cheap on a decade view and a coin flip on a weekly one"
                if (ou is not None and ou < -15) else
                "looks stretched on a decade view and a coin flip on a weekly one"
                if (ou is not None and ou > 40) else
                "sits near its long-term trend and remains a coin flip week to week")

    one_line = (f"expect the wider ranges in {loud_txt}, calmer trade in {quiet_txt}, "
                f"and remember that bitcoin {btc_line}.")

    P = []
    P.append("# Levanter Signal")
    P.append("")
    P.append("*The weekly premium note. One chart that matters, the volatility read "
             "across crypto, foreign exchange and commodities, and a plain line on "
             "what is and is not knowable from here.*")
    P.append("")
    P.append("---")
    P.append("")
    P.append(f"**The one line:** {one_line}")
    P.append("")

    # The one chart that matters
    P.append("## The one chart that matters")
    P.append("")
    if nv.get("fair_value"):
        price = nv.get("price")
        fair = nv.get("fair_value")
        floor = nv.get("floor")
        cyc = next((round(a.get("pct_vs_trend", 0)) for a in cg.get("assets", [])
                    if a.get("sym") == "BTC"), None)
        phase = next((a.get("phase", "") for a in cg.get("assets", [])
                      if a.get("sym") == "BTC"), "")
        seg = (f"Bitcoin is trading around {_kfmt(price)} dollars. Against its "
               f"long-term adoption trend, the model that actually holds for bitcoin, "
               f"fair value sits near {_kfmt(fair)}. That is roughly {abs(ou):.0f} "
               f"percent {'below' if ou < 0 else 'above'} trend, with the adoption "
               f"floor around {_kfmt(floor)}, a line that has held about 95 percent of "
               f"the time in bitcoin's history.")
        P.append(seg)
        P.append("")
        if cyc is not None:
            P.append(f"The cycle clock agrees: bitcoin is about {abs(cyc):.0f} percent "
                     f"{'below' if cyc < 0 else 'above'} its power-law trend and reads "
                     f"as {phase.lower()}.")
            P.append("")
        P.append("Read that correctly. It is not a price target and it is not a buy "
                 "signal. It is a statement about where bitcoin sits versus its own "
                 "network on a multi-year horizon. The honest caveat, which is the "
                 "whole point of Levanter, is that this tells you nothing about next "
                 "week. Both readings are true at once.")
        P.append("")
        P.append("*(Chart: bitcoin price against its adoption fair value and floor. Attached.)*")
        P.append("")

    # The volatility read
    P.append("## The volatility read, week ahead")
    P.append("")
    if acc7 and acc30:
        P.append(f"This is the part the model is actually good at. Volatility clusters, "
                 f"so a turbulent-or-calm call carries real skill, backtested at {acc7} "
                 f"percent over seven days and {acc30} percent over a month"
                 + (f", {acc90} percent over a quarter" if acc90 else "") + ". Here is "
                 "where it points for the coming week.")
        P.append("")
    loud_bits = []
    if g["commodity"][0]:
        loud_bits.append(f"the precious metals are the loudest room in the building, with "
                         f"{_join(g['commodity'][0])} all reading high volatility")
    if g["crypto"][0]:
        loud_bits.append(f"big-cap crypto is lively, with {_join(g['crypto'][0])} flagged "
                         f"turbulent" + (f" while {_join(g['crypto'][1])} sits calmer"
                         if g["crypto"][1] else ""))
    if loud_bits:
        P.append("The turbulence is concentrated, and it is worth knowing where. "
                 + _sentences(loud_bits) + ".")
        P.append("")
    quiet_bits = []
    if len(g["fx"][1]) >= 3:
        quiet_bits.append(f"foreign exchange is broadly asleep, with {len(g['fx'][1])} of "
                          f"the majors reading low"
                          + (f" and only {_join(g['fx'][0])} showing life" if g["fx"][0] else ""))
    if any(x in g["commodity"][1] for x in ("oil", "copper", "natural gas")):
        quiet_bits.append(f"energy is calm too, with {_join([x for x in g['commodity'][1] if x in ('oil','copper','natural gas')])} all low")
    if quiet_bits:
        P.append("The quiet is just as useful. " + _sentences(quiet_bits) + ".")
        P.append("")
    P.append("So the map is simple. Where the model reads high, plan for wider ranges and "
             "size accordingly. Where it reads low, expect a tighter, less eventful week. "
             "This is not a direction call on any of them. It is a heads-up on where the "
             "range is likely to be widest, which is where position sizing and stops "
             "actually matter.")
    P.append("")

    # Underneath
    coins = cm.get("coins", [])
    if coins:
        P.append("## What the tape is telling you underneath")
        P.append("")
        regime = "risk-on" if cm.get("regime_on") else "risk-off"
        capw = cm.get("cap_weighted_ret")
        dom = cm.get("btc_dominance")
        best, worst = coins[0], coins[-1]
        seg = (f"Crypto is {regime}, the market is "
               f"{'up' if (capw or 0) >= 0 else 'down'} about {abs(capw or 0):.0f} percent "
               f"over the past month, and bitcoin dominance sits near {dom:.0f} percent. "
               f"The best performer on the board is {best['coin']} at "
               f"{best['ret']:+.0f} percent while {worst['coin']} lags at "
               f"{worst['ret']:+.0f} percent. When the biggest moves cluster in the most "
               f"speculative names, the tape is telling you risk appetite is running a "
               f"little ahead of conviction. That is not a sell signal. It is a reason to "
               f"keep your stops honest.")
        P.append(seg)
        P.append("")
        items = sorted([i for i in co.get("items", []) if i.get("ret") is not None],
                       key=lambda x: x["ret"])
        if len(items) >= 2:
            P.append(f"In commodities, the split is wide: {_name(items[-1]['name'])} leads "
                     f"at {items[-1]['ret']:+.0f} percent and {_name(items[0]['name'])} "
                     f"lags at {items[0]['ret']:+.0f} percent.")
            P.append("")

    # What is and is not knowable
    P.append("## What is and is not knowable")
    P.append("")
    acc = ps.get("accuracy")
    rc = ps.get("resolved_count", 0)
    if acc is not None and rc:
        P.append(f"Here is the scoreboard, because it is the reason to trust the rest. "
                 f"Our volatility calls carry measurable skill, in the high sixties to mid "
                 f"seventies. Our direction calls, logged and scored in public, sit at "
                 f"{acc:.0f} percent across {rc:,} resolved calls, almost exactly a coin "
                 f"flip, and we publish that number rather than hide it.")
        P.append("")
    P.append("So the knowable this week: where the volatility is, where the calm is, and "
             "where bitcoin sits on a long-horizon valuation. The unknowable: which way "
             "any of them closes on Friday. We will not sell you the second one dressed "
             "as the first.")
    P.append("")
    P.append("---")
    P.append("")
    P.append("*This is a Levanter Signal, the weekly premium note. The daily, weekly and "
             "monthly reviews stay free at levantermarkets.com. The Signal and the alerts, "
             "a volatility-regime flip, a stablecoin starting to wobble, bitcoin touching "
             "its floor, are for subscribers. Educational market analysis, not financial "
             "advice.*")
    P.append("")
    P.append("*Subscribe: read.levantermarkets.com*")
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
                 f"{'below' if ou < 0 else 'above'} its adoption-trend fair value.")
        T.append("")
    T.append("What is not knowable:")
    T.append("")
    if acc is not None and rc:
        T.append(f"Which way any of it closes on Friday. Our direction calls, logged and "
                 f"scored in public, sit at {acc:.0f} percent across {rc:,} of them. Almost "
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
