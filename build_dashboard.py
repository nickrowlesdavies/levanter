#!/usr/bin/env python3
"""
Generate a self-contained visual dashboard (reports/dashboard.html) from the
four paper-strategy state files. Open it in any browser. All data stays local
- nothing is uploaded anywhere.

    python build_dashboard.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import traceback
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

R = "reports"
# Archive lives at the repo root (reports/ is gitignored) so the CI job can
# commit it back and past reviews survive each rebuild.
ARCHIVE_PATH = "review_archive.json"


def _read(path):
    p = os.path.join(R, path)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _load_archive():
    if not os.path.exists(ARCHIVE_PATH):
        return {}
    with open(ARCHIVE_PATH) as f:
        return json.load(f)


def _read_root(path):
    """Read a committed JSON file from the repo root (not under reports/)."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _save_archive(a):
    with open(ARCHIVE_PATH, "w") as f:
        json.dump(a, f, ensure_ascii=False)


def _now_gst():
    # Levanter is a Dubai (GST, UTC+4) publication; build runners are UTC.
    return datetime.utcnow() + timedelta(hours=4)


def _series_from_history(hist, key="equity"):
    xs, ys = [], []
    for h in hist or []:
        d = h.get("week") or h.get("month")
        if d is not None and key in h:
            xs.append(pd.to_datetime(d))
            ys.append(h[key])
    return xs, ys


def collect():
    """Normalise every strategy into a common card structure."""
    cards = []

    # FX (paper_state.json)
    fx = _read("paper_state.json")
    if fx:
        start = fx.get("starting_equity", 10000)
        eq = fx.get("realized_equity", start)
        closed = fx.get("closed_trades", [])
        openp = fx.get("open_positions", {})
        # Build equity path from closed-trade pnls.
        xs, ys, run = [], [], start
        for t in closed:
            run += t.get("pnl", 0)
            xs.append(pd.to_datetime(t.get("exit_time")))
            ys.append(run)
        if openp:
            pos = "<br>".join(
                f"{'LONG' if p['direction']==1 else 'SHORT'} {n} @ {p['entry_price']:.4f}"
                for n, p in openp.items())
        else:
            pos = "flat (waiting for a setup)"
        cards.append(dict(key="fx", title="FX mean-reversion", tf="4h majors",
                          equity=eq, start=start, n=f"{len(closed)} closed trades",
                          signal=pos, xs=xs, ys=ys))

    # Carry (carry_state.json)
    c = _read("carry_state.json")
    if c:
        xs, ys = _series_from_history(c.get("history"))
        pos = c.get("history", [{}])[-1] if c.get("history") else {}
        longs = ", ".join(pos.get("longs", [])) or "-"
        shorts = ", ".join(pos.get("shorts", [])) or "-"
        sig = f"LONG: {longs}<br>SHORT: {shorts}"
        cards.append(dict(key="carry", title="Carry basket", tf="monthly, 9 FX",
                          equity=c.get("equity", 10000),
                          start=c.get("start_equity", 10000),
                          n=f"{len(c.get('history', []))} rebalances",
                          signal=sig, xs=xs, ys=ys))

    # Crypto (crypto_state.json)
    cr = _read("crypto_state.json")
    if cr:
        xs, ys = _series_from_history(cr.get("history"))
        h = cr.get("holdings", [])
        last = cr.get("history", [{}])[-1] if cr.get("history") else {}
        regime = last.get("regime", "?")
        sig = ("100% STABLECOIN (risk-off)" if not h
               else "HOLD: " + ", ".join(h) + f"  [{regime}]")
        cards.append(dict(key="crypto", title="Crypto momentum", tf="weekly",
                          equity=cr.get("equity", 10000),
                          start=cr.get("start_equity", 10000),
                          n=f"{len(cr.get('history', []))} weeks",
                          signal=sig, xs=xs, ys=ys))

    # Combined (combined_state.json)
    cb = _read("combined_state.json")
    if cb:
        xs, ys = _series_from_history(cb.get("history"))
        w = cb.get("weights", {})
        top = sorted(w.items(), key=lambda kv: kv[1], reverse=True)[:6]
        sig = "<br>".join(f"{a}: {wt*100:.0f}%" for a, wt in top)
        cards.append(dict(key="combined", title="Combined portfolio", tf="weekly 70/30",
                          equity=cb.get("equity", 10000),
                          start=cb.get("start_equity", 10000),
                          n=f"{len(cb.get('history', []))} weeks",
                          signal=sig, xs=xs, ys=ys))

    # Vol-targeted basket (volbasket_state.json)
    vb = _read("volbasket_state.json")
    if vb:
        xs, ys = _series_from_history(vb.get("history"))
        w = vb.get("weights", {})
        top = sorted(w.items(), key=lambda kv: kv[1], reverse=True)[:4]
        sig = "risk-scaled · " + ", ".join(f"{a} {wt*100:.0f}%" for a, wt in top)
        cards.append(dict(key="volbasket", title="Vol-targeted basket",
                          tf="weekly · 8 assets", equity=vb.get("equity", 10000),
                          start=vb.get("start_equity", 10000),
                          n=f"{len(vb.get('history', []))} weeks",
                          signal=sig, xs=xs, ys=ys))
    return cards


PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4"]


def equity_chart(cards) -> str:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    for i, c in enumerate(cards):
        col = PALETTE[i % len(PALETTE)]
        if len(c["xs"]) >= 2:
            s = pd.Series(c["ys"], index=c["xs"]).sort_index()
            ax.plot(s.index, s.values / s.values[0] * 100, label=c["title"],
                    linewidth=2.2, color=col, solid_capstyle="round")
        elif c["xs"]:
            ax.scatter(c["xs"], [100], s=40, color=col, label=c["title"], zorder=3)
    ax.axhline(100, color="#9ca3af", linestyle="--", linewidth=0.8, alpha=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color("#9ca3af")
        ax.spines[sp].set_alpha(0.3)
    ax.tick_params(colors="#9ca3af", labelsize=8)
    ax.grid(axis="y", color="#9ca3af", alpha=0.12)
    ax.set_ylabel("Indexed to 100", color="#9ca3af", fontsize=9)
    if cards:
        ax.legend(fontsize=8, frameon=False, labelcolor="#9ca3af", ncol=2)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, transparent=True)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def embed_png(path) -> str | None:
    p = os.path.join(R, path)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _status_pill(c):
    k, sig = c["key"], c["signal"].upper()
    if k == "fx":
        return ("in trade", "blue") if "long" in sig.lower() or "short" in c["signal"].lower() else ("flat", "grey")
    if k == "crypto":
        return ("risk-off", "amber") if "STABLECOIN" in sig else ("risk-on", "green")
    if k == "carry":
        return ("active", "green")
    if k == "combined":
        return ("allocated", "blue")
    if k == "volbasket":
        return ("risk-scaled", "blue")
    return ("live", "grey")


def card_html(c, accent) -> str:
    ret = (c["equity"] / c["start"] - 1) * 100
    rcls = "up" if ret >= 0 else "down"
    label, pill = _status_pill(c)
    return f"""
    <div class="card" style="--accent:{accent}">
      <div class="card-top">
        <div class="card-title">{c['title']}<span class="tf">{c['tf']}</span></div>
        <span class="pill {pill}">{label}</span>
      </div>
      <div class="eq">£{c['equity']:,.0f}</div>
      <div class="ret {rcls}">{ret:+.2f}%<span class="meta">· {c['n']}</span></div>
      <div class="sig">{c['signal']}</div>
    </div>"""


MODAL_HTML = (
    '<div id="coinModal" class="modal" onclick="closeCoin(event)">'
    '<div class="modalbox" onclick="event.stopPropagation()">'
    '<div class="modalhead"><span id="mTitle"></span>'
    '<span class="mhead-r"><span id="mStar" class="mstar" onclick="toggleWatch()">☆ Watch</span>'
    '<span id="mClose" class="mclose" onclick="closeCoin()">✕ close</span></span></div>'
    '<div id="mPrice" class="mprice"></div>'
    '<div id="mChart" class="mchart"></div>'
    '<div id="mMoves" class="mmoves"></div>'
    '<div id="mStats" class="mstats"></div>'
    '<div class="mnote">Mechanical read from market data, not financial advice.</div>'
    '</div></div>')

COIN_MODAL_JS = r'''
function _mv(v){ if(v==null) return '<span class="mut">-</span>'; return '<span class="'+(v>=0?'up':'down')+'">'+(v>=0?'+':'')+v.toFixed(1)+'%</span>'; }
function _px(p){ if(p==null) return '-'; if(p>=1000) return '$'+p.toLocaleString(undefined,{maximumFractionDigits:0}); if(p>=1) return '$'+p.toFixed(2); if(p>=0.01) return '$'+p.toFixed(4); return '$'+p.toFixed(6); }
function _spark(a,w,h){ a=(a||[]).filter(function(x){return typeof x==='number';}); if(a.length<2) return ''; var lo=Math.min.apply(null,a),hi=Math.max.apply(null,a),rng=(hi-lo)||1,n=a.length; var pts=a.map(function(v,i){return (i/(n-1)*w).toFixed(1)+','+(h-3-((v-lo)/rng)*(h-6)).toFixed(1);}).join(' '); var col=a[a.length-1]>=a[0]?'#059669':'#dc2626'; return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none"><polyline fill="none" stroke="'+col+'" stroke-width="2" points="'+pts+'"/></svg>'; }
function showAsset(k){ var c=AD[k]; if(!c) return;
  document.getElementById('mTitle').textContent = c.label ? (k+'  ·  '+c.label) : k;
  document.getElementById('mPrice').innerHTML = _px(c.price)+' <span id="icval" class="mut" style="font-size:15px;font-weight:600"></span>';
  window._curHist = (c.hist && c.hist.length>1) ? c.hist : (c.spark||[]);
  if(window.renderIChart) renderIChart(_lastN(window._curHist, 90));
  var mvs=[['7d',c.chg7,7],['14d',c.chg14,14],['28d',c.chg28,28],['30d',c.chg30,30],['60d',c.chg60,60],['6mo',c.chg180,180],['12mo',c.chg365,365]];
  document.getElementById('mMoves').innerHTML = mvs.map(function(m){return '<div class="mvcell tfcell'+(m[2]===90?' on':'')+'" title="show '+m[0]+' history" onclick="setTF('+m[2]+',this)"><div class="mvk">'+m[0]+'</div>'+_mv(m[1])+'</div>';}).join('');
  var rows=[['Signal',c.signal||'-'],['Trend',c.trend||'-'],['Risk',(c.risk!=null?c.risk+' / 100 ('+c.risk_band+')':'-')],['Momentum rank',c.rank||'-'],['Market cap',c.market_cap?'$'+(c.market_cap/1e9).toFixed(1)+'B':'-'],['Volatility',c.vol!=null?c.vol.toFixed(0)+'%':'-'],['Max drawdown',c.dd!=null?c.dd.toFixed(0)+'%':'-'],['Return',_mv(c.ret)]];
  document.getElementById('mStats').innerHTML = rows.map(function(r){return '<div class="mrow"><span class="mk">'+r[0]+'</span><span class="mvv">'+r[1]+'</span></div>';}).join('');
  window._curAsset=k; if(window.renderStar)renderStar(k);
  document.getElementById('coinModal').style.display='flex';
}
function closeCoin(e){ if(!e || e.target.id==='coinModal' || e.target.id==='mClose') document.getElementById('coinModal').style.display='none'; }
document.addEventListener('keydown',function(e){ if(e.key==='Escape') document.getElementById('coinModal').style.display='none'; });
'''


def sparkline(vals, w=84, h=24) -> str:
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = " ".join(f"{i/(n-1)*w:.1f},{h-2-((v-lo)/rng)*(h-4):.1f}"
                   for i, v in enumerate(vals))
    col = "#059669" if vals[-1] >= vals[0] else "#dc2626"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'preserveAspectRatio="none"><polyline fill="none" stroke="{col}" '
            f'stroke-width="1.5" points="{pts}"/></svg>')


def _mv(v) -> str:
    if v is None:
        return '<span class="mut">–</span>'
    return f'<span class="{"up" if v >= 0 else "down"}">{v:+.1f}%</span>'


def _px(p) -> str:
    if p >= 1000:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    if p >= 0.01:
        return f"${p:.4f}"
    return f"${p:.6f}"


def _kfmt(v) -> str:
    return f"${v/1000:.0f}k" if v >= 1000 else f"${v:,.0f}"


def cycle_gauge_section() -> str:
    d = _read("cycle_gauge.json")
    if not d or not d.get("assets"):
        return ""
    banner = (f'<div class="cyc-banner">Crypto cycle phase: <b>{d.get("phase")}</b> · '
              f'{d.get("days_since_halving")} days since the 2024 halving · '
              f'next halving ~{d.get("next_halving")}</div>')
    cards = ""
    for a in d["assets"]:
        head = f'<div class="cyc-h">{a["name"]} <span class="cyc-sym">{a["sym"]}</span></div>'
        px = f'<div class="cyc-px">{_px(a["price"])}</div>'
        if a["kind"] == "crypto":
            pv = a["pct_vs_trend"]
            bp = a.get("bandpos", 0.5) * 100
            meter = (f'<div class="meter"><div class="mmark" style="left:{bp:.0f}%"></div></div>'
                     f'<div class="mlbl"><span>cheap</span><span>trend</span><span>frothy</span></div>')
            proj_html = ""
            if a.get("proj"):
                p1 = a["proj"]["1y"]
                proj_html = (f'<div class="cyc-proj">1yr scenario: {_kfmt(p1["low"])}–'
                             f'{_kfmt(p1["high"])} <span class="mut">(trend {_kfmt(p1["base"])})</span></div>')
            phase_txt = a["phase"] + (" · provisional (short history)" if a.get("provisional") else "")
            cards += (f'<div class="cyc-card">{head}{px}'
                      f'<div class="cyc-metric {"up" if pv >= 0 else "down"}">{pv:+.0f}% vs cycle-gauge trend</div>'
                      f'{meter}<div class="cyc-phase">{phase_txt}</div>{proj_html}</div>')
        elif a["kind"] == "macro":
            pv = a["pct_from_ath"]
            cards += (f'<div class="cyc-card">{head}{px}'
                      f'<div class="cyc-metric {"up" if pv >= -3 else "down"}">{pv:+.0f}% from all-time high</div>'
                      f'<div class="cyc-phase">trend {a.get("trend")} · macro asset (no halving cycle)</div></div>')
        else:
            cards += (f'<div class="cyc-card">{head}{px}'
                      f'<div class="cyc-metric mut">too new for cycle analysis</div>'
                      f'<div class="cyc-phase">{a.get("note", "")} · 30d {a.get("chg30", 0):+.0f}%</div></div>')
    eb = d.get("ethbtc")
    ebline = ""
    if eb:
        rich = ("cheap vs BTC" if eb["percentile"] < 40 else
                "rich vs BTC" if eb["percentile"] > 60 else "mid-range vs BTC")
        ebline = (f'<div class="cyc-eb">ETH/BTC ratio <b>{eb["ratio"]:.4f}</b>, '
                  f'{eb["percentile"]:.0f}th percentile of its history ({rich}); '
                  f'6-month change {eb["chg6m"]:+.0f}%</div>')
    proj_charts = ""
    for a in d["assets"]:
        if a.get("proj_chart"):
            b = embed_png(a["proj_chart"])
            if b:
                proj_charts += (f'<figure><img src="data:image/png;base64,{b}">'
                                f'<figcaption>{a["name"]} cycle-gauge scenario projection '
                                f'(~2yr, scenario band)</figcaption></figure>')
    proj_block = f'<div class="gallery">{proj_charts}</div>' if proj_charts else ""
    return (f'<div class="subh">Market cycle gauge</div>{banner}'
            f'<div class="cyc-grid">{cards}</div>{ebline}{proj_block}')


def btc_network_value_section() -> str:
    """Bitcoin network-value read: dollar fair value + adoption floor (power-law /
    Peterson LPF family), plus the honest Metcalfe-on-addresses decoupling note.
    Complements the cycle gauge above, which shows the same trend as a meter."""
    d = _read("btc_metcalfe.json")
    if not d or not d.get("fair_value"):
        return ""
    fair, floor, top = d["fair_value"], d["floor"], d["frothy_top"]
    ou, pos, read = d["over_under_pct"], d.get("band_position", 50), d.get("read", "")
    updown = "down" if ou < 0 else "up"
    side = "below" if ou < 0 else "above"
    meter = (f'<div class="meter"><div class="mmark" style="left:{pos:.0f}%"></div></div>'
             f'<div class="mlbl"><span>floor {_kfmt(floor)}</span>'
             f'<span>fair {_kfmt(fair)}</span><span>frothy {_kfmt(top)}</span></div>')
    m = d.get("metcalfe_diagnostic") or {}
    metc = ""
    if m:
        metc = ('<div class="nv-metc">We also tested <b>Metcalfe’s Law</b>, the classic '
                'network model that values a chain by its active addresses. It held until '
                f'about 2018 but has since <b>decoupled</b> (the fit since 2019 has an '
                f'R² of {m.get("r2", 0):.2f} and the wrong sign), because exchange '
                'batching, layer-2s and post-ETF custody pull real users off the on-chain '
                'count. So we do not use it. What still holds is the adoption trend above.</div>')
    return ('<div class="subh">Bitcoin network value</div>'
            '<div class="nv-card">'
            f'<div class="nv-lead">Against its long-term adoption trend, bitcoin looks '
            f'<b class="{updown}">{read}</b>: about <b>{abs(ou):.0f}% {side}</b> a fair value '
            f'near <b>{_kfmt(fair)}</b>, with the model’s adoption floor around '
            f'<b>{_kfmt(floor)}</b>, a level roughly 95% of history has sat above.</div>'
            f'{meter}{metc}'
            '<div class="mnote">Long-horizon valuation context, not a signal or a price '
            'target. The power law is a fit to price over time with no hard economic '
            'mechanism and cannot call tops. Educational, not advice.</div></div>')


def prediction_section(cls="crypto") -> str:
    d = _read("prediction_state.json")
    if not d:
        return ""
    label = {"crypto": "crypto", "fx": "FX", "commodity": "commodities"}.get(cls, cls)
    bc = (d.get("by_class") or {}).get(cls)
    if bc is None:                      # older state file without per-class split
        bc = d
    warn = ('<div class="pred-warn">⚠ EXPERIMENTAL MODEL, educational only. '
            'These are mechanical up/down calls logged to test whether a model can '
            'match reality. NOT a forecast, NOT advice, NO liability. Expect accuracy '
            'near a coin-flip (50%). Do not trade on this.</div>')
    acc, rc = bc.get("accuracy"), bc.get("resolved_count", 0)
    byh = bc.get("accuracy_by_horizon", {})
    n = bc.get("n_assets", "?")
    if rc == 0 or acc is None:
        score = (f'<div class="pred-score">Track record ({label}): '
                 f'<b>building history</b>, 0 calls scored yet.</div>')
    else:
        parts = [f"{rc} scored across {n} {label} assets", f"<b>{acc:.0f}% correct</b>"]
        if byh.get("7") is not None:
            parts.append(f"7d {byh['7']:.0f}%")
        if byh.get("30") is not None:
            parts.append(f"30d {byh['30']:.0f}%")
        vs = "beating" if acc > 52 else "≈" if acc >= 48 else "below"
        score = (f'<div class="pred-score">Track record: {" · ".join(parts)}, '
                 f'{vs} coin-flip (50%)</div>')
    up, down = bc.get("open_up", 0), bc.get("open_down", 0)
    summary = (f'<div class="pred-score">This period: <b class="up">{up} UP</b> / '
               f'<b class="down">{down} DOWN</b> across {n} {label} assets. '
               f'Highest-conviction calls:</div>')
    cards = ""
    for p in bc.get("top_calls", []):
        u = p["predicted"] == "up"
        conf = abs(p["prob_up"] - 0.5) * 200
        cards += (f'<div class="pred-card"><div class="pred-h">{p["asset"]} · {p["horizon"]}d</div>'
                  f'<div class="pred-dir {"up" if u else "down"}">{"▲ UP" if u else "▼ DOWN"}</div>'
                  f'<div class="pred-prob">lean {conf:.0f}%</div></div>')
    pegline = ""
    if cls == "crypto":
        pegs = d.get("pegs", {})
        ar = pegs.get("at_risk", [])
        pegline = (f'<div class="pred-recent">Stablecoin peg outlook: '
                   f'<b>{pegs.get("tracked", 0)}</b> predicted to hold peg; at-risk: '
                   f'{", ".join(ar) if ar else "none"}.</div>')
    return (f'<div class="subh">Prediction model '
            f'<span class="mut">(experimental scorecard · {label})</span></div>'
            f'{warn}{score}{summary}<div class="pred-grid">{cards}</div>{pegline}')


def vol_regime_section(classes=None) -> str:
    d = _read("vol_regime.json")
    if not d or not d.get("assets"):
        return ""
    assets = d["assets"]
    if classes:
        clsmap = d.get("classes", {})
        assets = {a: h for a, h in assets.items() if clsmap.get(a) in classes}
        if not assets:
            return ""
    hs = d.get("horizons", [])
    bt = d.get("backtest", {})
    btparts = [f"{h} {bt[h]['acc']}% (+{bt[h]['edge']})" for h in hs
               if h in bt and bt[h]["edge"] > 0]
    note = ('<div class="pred-recent" style="margin-bottom:8px">Predicts whether the '
            'next period will be <b>TURBULENT</b> (high vol) or <b>CALM</b> (low vol), '
            'not price direction. Backtested skill (5yr): ' + " · ".join(btparts) +
            '. <b>A real edge, because volatility clusters</b>, unlike direction.</div>')
    head = "<th>Asset</th>" + "".join(f"<th>{h}</th>" for h in hs)
    rows = ""
    for a, hor in assets.items():
        cells = ""
        for h in hs:
            v = hor.get(h)
            if v:
                cls = "vr-hi" if v["regime"] == "HIGH" else "vr-lo"
                cells += f'<td><span class="{cls}">{v["regime"]}</span></td>'
            else:
                cells += "<td>–</td>"
        rows += f'<tr><td class="cn">{a}</td>{cells}</tr>'
    table = (f'<div class="tablewrap"><table class="coins vr-table"><thead><tr>{head}'
             f'</tr></thead><tbody>{rows}</tbody></table></div>')
    return (f'<div class="subh">Volatility regime forecast '
            f'<span class="mut">(turbulence, not direction, this one has real skill)</span></div>'
            f'{note}{table}')


def orderflow_section() -> str:
    d = _read("orderflow.json")
    if not d or not d.get("coins"):
        return ""
    note = ('<div class="pred-recent" style="margin-bottom:10px">Taker-buy % = share of '
            'volume that was aggressive buying (>50% = buyers lifting offers). Funding = perp '
            'rate (positive = longs pay = leveraged-long crowd). <b>Market context, not a '
            'predictor</b>, tested, it adds ~0 to prediction accuracy.</div>')
    cards = ""
    for c in d["coins"]:
        buy = c["buy_pct"]
        up = buy >= 50
        cards += (f'<div class="of-card"><div class="of-c">{c["coin"]}</div>'
                  f'<div class="of-buy {"up" if up else "down"}">{"BUY" if up else "SELL"} {buy:.0f}%</div>'
                  f'<div class="of-f">fund {c["funding_pct"]:+.3f}%</div></div>')
    return (f'<div class="subh">Crypto order flow <span class="mut">(context)</span></div>'
            f'{note}<div class="of-grid">{cards}</div>')


def crypto_section() -> str:
    data = _read("crypto_map.json")
    if not data:
        return ""
    coins, stables = data["coins"], data["stables"]
    regime_on = data.get("regime_on", True)
    rec = data.get("recommendation", [])
    best, worst = coins[0], coins[-1]

    reg_cls = "on" if regime_on else "off"
    reg_txt = "RISK-ON" if regime_on else "RISK-OFF"
    if not regime_on:
        rec_txt = "Model says: hold stablecoin, market is risk-off."
    elif rec:
        rec_txt = "Model basket (top-momentum uptrends): " + ", ".join(rec)
    else:
        rec_txt = "Model says: no coins currently pass the filter."

    capw, eqw = data.get("cap_weighted_ret"), data.get("equal_weighted_ret")
    dom, tcap = data.get("btc_dominance"), data.get("total_mcap_b")
    hl = (f'<div class="hl">'
          f'<span>Window<b>{data["start"]} → {data["end"]}</b></span>'
          f'<span>Market (cap-wtd)<b>{capw:+.1f}%</b></span>'
          f'<span>Equal-weight<b>{eqw:+.1f}%</b></span>'
          f'<span>BTC dominance<b>{dom:.0f}%</b></span>'
          f'<span>Total cap<b>${tcap:,.0f}B</b></span>'
          f'<span>Best<b>{best["coin"]} {best["ret"]:+.0f}%</b></span>'
          f'<span>Worst<b>{worst["coin"]} {worst["ret"]:+.0f}%</b></span>'
          f'<span>Avg correlation<b>{data["avg_corr"]:.2f}</b></span></div>')

    sigcls = {"buy": "green", "hold": "blue", "avoid": "red",
              "risk-off": "grey", "hot": "amber"}
    riskcls = {"low": "green", "medium": "blue", "high": "amber", "extreme": "red"}
    # Pin the majors to the top, then the rest by momentum.
    pin = ["BTC", "ETH"]
    ordered = ([c for p in pin for c in coins if c["coin"] == p]
               + [c for c in coins if c["coin"] not in pin])

    def render_row(c, tag=""):
        pill = sigcls.get(c.get("signal"), "grey")
        risk = c.get("risk")
        risk_html = (f'<span class="pill {riskcls.get(c.get("risk_band", ""), "grey")}">'
                     f'{risk} {c.get("risk_band", "")}</span>' if risk is not None else "–")
        tagspan = f'<span class="ctag">{tag}</span>' if tag else ""
        return (f'<tr onclick="showAsset(\'{c["coin"]}\')">'
                f'<td class="mut">{c.get("rank", "")}</td>'
                f'<td class="cn">{c["coin"]}{tagspan}</td>'
                f'<td class="pr">{_px(c["price"])}</td>'
                f'<td class="sp">{sparkline(c.get("spark"))}</td>'
                f'<td>{_mv(c.get("chg7"))}</td>'
                f'<td>{_mv(c.get("chg30"))}</td>'
                f'<td>{_mv(c.get("ret"))}</td>'
                f'<td>{risk_html}</td>'
                f'<td><span class="pill {pill}">{c.get("signal", "")}</span></td></tr>')

    rows = "".join(render_row(c) for c in ordered)
    table = (f'<div class="tablewrap"><table class="coins"><thead><tr>'
             f'<th>#</th><th>Coin</th><th>Price</th><th>90d history</th>'
             f'<th>7d</th><th>30d</th><th>90d</th><th>Risk</th><th>Signal</th></tr></thead>'
             f'<tbody>{rows}</tbody></table></div>')

    pmap = {"ok": "green", "watch": "amber", "alert": "red"}
    pegs = ""
    for s in stables:
        mc = s.get("mcap_b")
        capstr = f"${mc:.1f}B · " if mc else ""
        pegs += (f'<div class="peg"><div class="nm">{s["coin"]}'
                 f'<span class="pill {pmap.get(s["status"], "grey")}">{s["status"]}</span></div>'
                 f'<div class="px">${s["price"]:.4f}</div>'
                 f'<div class="lo">{capstr}90d low ${s["minp"]:.4f}</div></div>')

    charts = ""
    for fn, cap in [("crypto_map_treemap.png", "Market map · box size = market cap, colour = 90-day return"),
                    ("crypto_map_correlation.png", "Return correlations (top 24)")]:
        b = embed_png(fn)
        if b:
            charts += (f'<figure><img src="data:image/png;base64,{b}">'
                       f'<figcaption>{cap}</figcaption></figure>')

    mv = data.get("movers", {})
    mv_cards = ""
    for label in ["7d", "14d", "30d", "6mo", "12mo"]:
        items = "".join(
            f'<div class="mvrow"><span class="mvc">{t["coin"]}</span>'
            f'<span class="{"up" if t["ret"] >= 0 else "down"}">{t["ret"]:+.0f}%</span></div>'
            for t in mv.get(label, [])) or '<div class="mvrow mut">n/a</div>'
        mv_cards += f'<div class="mvcard"><div class="mvh">{label}</div>{items}</div>'
    movers_html = (f'<div class="subh">Top 3 movers by timeframe</div>'
                   f'<div class="movers">{mv_cards}</div>') if mv else ""

    return (f'<div class="cbanner {reg_cls}"><div class="reg">Crypto regime · {reg_txt}</div>'
            f'<div class="rec">{rec_txt}</div></div>'
            f'{hl}'
            f'{cycle_gauge_section()}'
            f'{btc_network_value_section()}'
            f'{prediction_section("crypto")}'
            f'{vol_regime_section({"crypto", "equity"})}'
            f'{orderflow_section()}'
            f'{movers_html}'
            f'<div class="subh">Coins · BTC &amp; ETH pinned '
            f'· <b>click any row for detail</b></div>{table}'
            f'<div class="subh">Stablecoin peg monitor</div><div class="pegs">{pegs}</div>'
            f'<div class="gallery">{charts}</div>')


def _movers_panel(movers, keyfield, title="Top 3 movers by timeframe"):
    mv_cards = ""
    for label in ["7d", "14d", "28d", "60d", "6mo", "12mo"]:
        items = "".join(
            f'<div class="mvrow"><span class="mvc">{t[keyfield]}</span>'
            f'<span class="{"up" if t["ret"] >= 0 else "down"}">{t["ret"]:+.1f}%</span></div>'
            for t in movers.get(label, [])) or '<div class="mvrow mut">n/a</div>'
        mv_cards += f'<div class="mvcard"><div class="mvh">{label}</div>{items}</div>'
    return (f'<div class="subh">{title}</div>'
            f'<div class="movers">{mv_cards}</div>') if movers else ""


def _asset_table(rows, keyfield, price_fmt, headers):
    body = ""
    trend_cls = {"up": "up", "down": "down"}
    for c in rows:
        body += (f'<tr onclick="showAsset(\'{c[keyfield]}\')">'
                 f'<td class="cn">{c[keyfield]}</td>'
                 f'<td>{price_fmt(c["price"])}</td>'
                 f'<td class="sp">{sparkline(c.get("spark"))}</td>'
                 f'<td>{_mv(c.get("chg7"))}</td>'
                 f'<td>{_mv(c.get("chg30"))}</td>'
                 f'<td>{_mv(c.get("chg180"))}</td>'
                 f'<td class="{trend_cls.get(c.get("trend"), "mut")}">{c.get("trend", "-")}</td>'
                 f'<td>{c.get("vol", 0):.0f}%</td></tr>')
    th = "".join(f"<th>{h}</th>" for h in headers)
    return (f'<div class="tablewrap"><table class="coins"><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def fx_section() -> str:
    d = _read("fx_map.json")
    if not d:
        return '<div class="sig">FX data is being updated. Please check back shortly.</div>'
    pairs = d.get("pairs", [])
    best = max(pairs, key=lambda c: c.get("chg30") or -999) if pairs else None
    worst = min(pairs, key=lambda c: c.get("chg30") or 999) if pairs else None
    up30 = sum(1 for c in pairs if (c.get("chg30") or 0) > 0)
    banner = (f'<div class="cbanner {"on" if up30 >= len(pairs)/2 else "off"}">'
              f'<div class="reg">FX · {len(pairs)} majors &amp; crosses</div>'
              f'<div class="rec">{up30}/{len(pairs)} pairs higher over 30d · '
              f'best {best["pair"]} {best.get("chg30",0):+.1f}% · '
              f'worst {worst["pair"]} {worst.get("chg30",0):+.1f}%</div></div>')
    table = _asset_table(pairs, "pair", lambda p: f"{p:.4f}",
                         ["Pair", "Rate", "90d", "7d", "30d", "6mo", "Trend", "Vol"])
    return (f'{banner}{_movers_panel(d.get("movers", {}), "pair")}'
            f'<div class="subh">Pairs · <b>click any row for detail</b> · '
            f'sorted by 30d move</div>{table}'
            f'{vol_regime_section({"fx"})}'
            f'{prediction_section("fx")}'
            f'<div class="mnote">FX has no market cap or power-law cycle, so this is '
            f'trend, momentum, volatility and regime. Rates are mid prices. '
            f'Mechanical read, not advice.</div>')


def commodities_tab_section() -> str:
    d = _read("commodities_map.json")
    if not d:
        return ('<div class="sig">Commodities data is being updated. '
                'Please check back shortly.</div>')
    items = d.get("items", [])
    best = items[0] if items else None
    worst = items[-1] if items else None
    up30 = sum(1 for c in items if (c.get("chg30") or 0) > 0)
    banner = (f'<div class="cbanner {"on" if up30 >= len(items)/2 else "off"}">'
              f'<div class="reg">Commodities · {len(items)} markets</div>'
              f'<div class="rec">{up30}/{len(items)} higher over 30d · '
              f'best {best["name"]} {best.get("chg30",0):+.1f}% · '
              f'worst {worst["name"]} {worst.get("chg30",0):+.1f}%</div></div>')
    table = _asset_table(items, "name",
                         lambda p: (f"${p:,.0f}" if p >= 100 else f"${p:,.2f}"),
                         ["Market", "Price", "90d", "7d", "30d", "6mo", "Trend", "Vol"])
    return (f'{banner}{_movers_panel(d.get("movers", {}), "name")}'
            f'<div class="subh">Metals · energy · agriculture · <b>click any row for '
            f'detail</b> · sorted by 30d move</div>{table}'
            f'{vol_regime_section({"commodity"})}'
            f'{prediction_section("commodity")}'
            f'<div class="mnote">Futures/ETF prices via public market data. '
            f'Mechanical read, not advice.</div>')


def _cross_movers(horizon="chg30"):
    """Best performers across ALL markets for one horizon (for the Home tab)."""
    out = []
    cm = _read("crypto_map.json") or {}
    for c in (cm.get("coins", []) or []):
        out.append(("crypto", c["coin"], c.get(horizon)))
    fx = _read("fx_map.json") or {}
    for c in fx.get("pairs", []):
        out.append(("fx", c["pair"], c.get(horizon)))
    co = _read("commodities_map.json") or {}
    for c in co.get("items", []):
        out.append(("commodity", c["name"], c.get(horizon)))
    out = [(cls, k, v) for cls, k, v in out if v is not None]
    out.sort(key=lambda t: t[2], reverse=True)
    return out


def home_section(cards) -> str:
    tag = {"crypto": "blue", "fx": "green", "commodity": "amber"}
    up = _cross_movers("chg30")
    if not up:
        return '<div class="sig">No market data yet. Run the map scripts first.</div>'
    top = up[:8]
    bot = list(reversed(up[-8:]))

    def board(rows, title):
        cells = "".join(
            f'<div class="xrow" onclick="showAsset(\'{k}\')">'
            f'<span class="xk"><span class="pill {tag[cls]}">{cls}</span>{k}</span>'
            f'<span class="{"up" if v >= 0 else "down"}">{v:+.1f}%</span></div>'
            for cls, k, v in rows)
        return f'<div class="xboard"><div class="subh">{title}</div>{cells}</div>'

    # quick regime read per class
    cm = _read("crypto_map.json") or {}
    fxm = _read("fx_map.json") or {}
    com = _read("commodities_map.json") or {}
    reg_cards = ""
    for name, on, sub in [
        ("Crypto", cm.get("regime_on", True),
         f'cap-wtd {cm.get("cap_weighted_ret", 0):+.1f}% · BTC dom {cm.get("btc_dominance", 0):.0f}%'),
        ("FX", None, f'{sum(1 for c in fxm.get("pairs", []) if (c.get("chg30") or 0) > 0)}'
                     f'/{len(fxm.get("pairs", []))} pairs up 30d'),
        ("Commodities", None, f'{sum(1 for c in com.get("items", []) if (c.get("chg30") or 0) > 0)}'
                              f'/{len(com.get("items", []))} up 30d')]:
        badge = ("RISK-ON" if on else "RISK-OFF") if on is not None else "MIXED"
        bcls = "green" if on else ("grey" if on is None else "red")
        reg_cards += (f'<div class="mvcard"><div class="mvh">{name} '
                      f'<span class="pill {bcls}">{badge}</span></div>'
                      f'<div class="mut" style="font-size:12px">{sub}</div></div>')

    strat = ""
    if cards:
        total = sum(c["equity"] for c in cards)
        tstart = sum(c["start"] for c in cards) or 1
        tret = (total / tstart - 1) * 100
        strat = (f'<div class="subh">Paper strategies</div>'
                 f'<div class="hl"><span>Combined equity<b>£{total:,.0f}</b></span>'
                 f'<span>Return<b class="{"up" if tret>=0 else "down"}">{tret:+.2f}%</b></span>'
                 f'<span>Strategies<b>{len(cards)}</b></span></div>')

    # Featured one-line cross-market read (mirrors tradewind's "latest brief").
    reg = "risk-on" if cm.get("regime_on", True) else "risk-off"
    b, w = top[0], bot[0]
    fx_up = sum(1 for c in fxm.get("pairs", []) if (c.get("chg30") or 0) > 0)
    brief_txt = (f'Crypto is <b>{reg}</b>. Across all markets over 30 days, '
                 f'<b>{b[1]}</b> leads ({b[2]:+.0f}%) and <b>{w[1]}</b> lags ({w[2]:+.0f}%); '
                 f'{fx_up}/{len(fxm.get("pairs", []))} FX pairs are higher.')
    brief = (f'<div class="brief"><div class="brief-k">This week\'s read</div>'
             f'<div class="brief-t">{brief_txt}</div>'
             f'<button class="brief-b" onclick="levTab(\'reviews\')">Full reviews →</button></div>')

    return (f'{brief}'
            f'{SUBSCRIBE_BOX}'
            f'<div class="subh">Market regime · at a glance</div>'
            f'<div class="movers">{reg_cards}</div>'
            f'<div class="xboards">{board(top, "🔥 Top performers · 30d · all markets")}'
            f'{board(bot, "❄️ Weakest · 30d · all markets")}</div>'
            f'{strat}'
            f'<div class="mnote">Moves shown are <b>historical</b> price changes over the '
            f'trailing window, not forecasts. Click any name for full detail. '
            f'Educational, not financial advice.</div>')


def _review_for(rows, keyfield, label):
    """Generate a short factual weekly/monthly review paragraph for one class."""
    def top(field, rev=True):
        r = [c for c in rows if c.get(field) is not None]
        if not r:
            return None
        return sorted(r, key=lambda c: c[field], reverse=rev)[0]
    up7 = sum(1 for c in rows if (c.get("chg7") or 0) > 0)
    up30 = sum(1 for c in rows if (c.get("chg30") or 0) > 0)
    n = len(rows)
    b7, w7 = top("chg7"), top("chg7", rev=False)
    b30, w30 = top("chg30"), top("chg30", rev=False)
    avg30 = sum((c.get("chg30") or 0) for c in rows) / n if n else 0
    hi_vol = top("vol")
    week = (f'<b>This week ({label}).</b> {up7} of {n} {label.lower()} rose over the last 7 days. '
            f'Strongest was {b7[keyfield]} at {b7.get("chg7",0):+.1f}%, weakest {w7[keyfield]} '
            f'at {w7.get("chg7",0):+.1f}%.') if b7 else ""
    month = (f' <b>This month.</b> Over 30 days the average move was {avg30:+.1f}% with '
             f'{up30}/{n} higher. {b30[keyfield]} led ({b30.get("chg30",0):+.1f}%); '
             f'{w30[keyfield]} lagged ({w30.get("chg30",0):+.1f}%). '
             f'Most volatile: {hi_vol[keyfield]} (~{hi_vol.get("vol",0):.0f}% annualised).') if b30 else ""
    return week + month


def _daily_para(rows, keyfield, label, hi7, n7):
    """Recap the last session (from chg1) + preview the coming one honestly:
    we don't forecast direction, so 'coming session' = what to watch, led by the
    volatility-regime near-term (7d) read for the class."""
    have = [c for c in rows if c.get("chg1") is not None]
    if not have:
        return ""
    b1 = max(have, key=lambda c: c["chg1"])
    w1 = min(have, key=lambda c: c["chg1"])
    up1 = sum(1 for c in have if c["chg1"] > 0)
    active = sorted((c for c in rows if c.get("vol") is not None),
                    key=lambda c: c["vol"], reverse=True)[:2]
    names = ", ".join(c[keyfield] for c in active) if active else "none"
    turb = "turbulent" if (n7 and hi7 >= n7 / 2) else "calmer"
    vrbit = (f' Volatility regime points to <b>{turb}</b> conditions near-term '
             f'({hi7}/{n7} flagged high-vol at 7d).') if n7 else ""
    yesterday = (f'<b>Yesterday.</b> {up1} of {len(have)} {label.lower()} closed higher. '
                 f'Best {b1[keyfield]} {b1["chg1"]:+.1f}%, weakest {w1[keyfield]} {w1["chg1"]:+.1f}%.')
    coming = (f' <b>Coming session.</b> The model does not call direction (that is a coin-flip); '
              f'it flags what to watch.{vrbit} Most active names to watch: {names}.')
    return yesterday + coming


def _cstats(rows, kf, field):
    """Best/worst/breadth/average for one class over one change-field."""
    have = [c for c in rows if c.get(field) is not None]
    if not have:
        return None
    b = max(have, key=lambda c: c[field])
    w = min(have, key=lambda c: c[field])
    up = sum(1 for c in have if c[field] > 0)
    avg = sum(c[field] for c in have) / len(have)
    hv = max((c for c in rows if c.get("vol") is not None),
             key=lambda c: c["vol"], default=None)
    return dict(kf=kf, n=len(have), b=b, w=w, up=up, avg=avg, hv=hv,
                bn=b[kf], bv=b[field], wn=w[kf], wv=w[field])


def _dollar_read(pairs, field):
    """Positive => the US dollar strengthened over the window."""
    quote = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}       # up => USD weaker
    base = {"USDJPY", "USDCHF", "USDCAD", "USDSEK", "USDNOK", "USDMXN", "USDZAR"}
    vals = []
    for c in pairs:
        v = c.get(field)
        if v is None:
            continue
        if c.get("pair") in quote:
            vals.append(-v)
        elif c.get("pair") in base:
            vals.append(v)
    return sum(vals) / len(vals) if vals else 0.0


def _vol_outlook(vr, cls):
    va, vc = vr.get("assets", {}), vr.get("classes", {})
    mem = [a for a, c in vc.items() if c == cls]
    hi = sum(1 for a in mem if (va.get(a, {}).get("7d") or {}).get("regime") == "HIGH")
    return hi, len(mem)


def _levanter_view(regime_on, crypto_avg, vol_share):
    if not regime_on:
        return ("When risk comes off, correlations rise and the diversification you thought "
                "you had can thin out just when you need it most. Cash and havens are positions "
                "too. The point of reading every market on one page is to see those shifts early, "
                "not to pick the exact bottom.")
    if crypto_avg > 5:
        return ("A word while the tape runs hot. The strongest week is usually the hardest time "
                "to add, not the easiest. Momentum is real, but so is mean reversion, and the "
                "crowd that arrives late to a move tends to fund the exit of those who were early. "
                "We flag what moved. We do not tell you to chase it.")
    if vol_share >= 0.5:
        return ("If there is one thing these pages can honestly forecast, it is weather, not "
                "direction. Volatility clusters: calm tends to follow calm and storms follow "
                "storms far more reliably than prices trend. That is why our week-ahead talks in "
                "terms of turbulence rather than targets. Size for the weather you can see coming.")
    return ("The durable edges in markets are unglamorous: diversification, sensible position "
            "sizing, and the discipline to cut losers. None of them require predicting next week. "
            "Much of what looks like skill in a rising market is simply exposure, and we would "
            "rather be honest about that than sell a crystal ball.")


def _piece_data():
    return (_read("crypto_map.json") or {}, _read("fx_map.json") or {},
            _read("commodities_map.json") or {}, _read("cycle_gauge.json") or {},
            _read("vol_regime.json") or {})


def _topn(rows, kf, field, n=3, rev=True):
    have = [c for c in rows if c.get(field) is not None]
    have.sort(key=lambda c: c[field], reverse=rev)
    return [(c[kf], c[field]) for c in have[:n]]


def _fmt_moves(lst):
    return ", ".join(f"{n} ({v:+.1f}%)" for n, v in lst) if lst else "none"


def _sentences(parts):
    """Join clause fragments as separate sentences (full stops, not semicolons)."""
    out = []
    for p in parts:
        if not p:
            continue
        s = p[0].upper() + p[1:]
        out.append(s if s.endswith(".") else s + ".")
    return " ".join(out)


def _macro_read(cm, fxm, com, field):
    pairs, items = fxm.get("pairs", []), com.get("items", [])
    cd = {c.get("name"): c for c in items}
    dollar = _dollar_read(pairs, field)
    g = lambda name: cd.get(name, {}).get(field)
    return dict(
        dollar=dollar,
        dxi=("stronger" if dollar > 0.5 else "softer" if dollar < -0.5 else "little changed"),
        gold=g("GOLD"), silver=g("SILVER"), platinum=g("PLATINUM"),
        copper=g("COPPER"), oil=g("WTI OIL"), brent=g("BRENT OIL"), gas=g("NAT GAS"),
        regime_on=cm.get("regime_on", True), capw=cm.get("cap_weighted_ret"))


def _weekly_opinion(regime_on, cs, mac, vol_share, corr, top):
    lead = top[1] if top else "the leaders"
    if regime_on and cs and cs["avg"] > 6:
        return [
            f"The temptation this week is to extrapolate. When {lead} prints a number like the one "
            f"it just did and the screen is a wall of green, the mind quietly rewrites the odds and "
            f"decides the move is only getting started. It rarely is. The strongest week in a run "
            f"is far more often the middle than the beginning, and by the time a move is obvious "
            f"enough to feel safe, most of it has already happened.",
            "None of this means selling. It means refusing to confuse a fast tape with a free one. "
            "Momentum is a real and durable effect, but it is paid for with sharp, sudden reversals "
            "that arrive without warning, and the people who get hurt are almost always the ones who "
            "sized up at the top of the excitement rather than the bottom of the boredom.",
            "Our read is simple and unfashionable. Let the winners run if you already own them, but "
            "treat new money added into a vertical move as the most expensive money you will spend "
            "all year. The edge was in being early and diversified, not in chasing the print."]
    if not regime_on:
        return [
            "Risk came off this week, and the first casualty of a risk-off tape is the illusion of "
            "diversification. Correlations rise together precisely when you need them to fall, and "
            "the portfolio that felt spread out in calm markets suddenly moves as one red block.",
            f"That is the real lesson of a week like this. The dollar was {mac['dxi']} and havens "
            f"did their job while risk assets did not, which is exactly the pattern that separates a "
            f"genuine hedge from a correlated bet wearing a different label. Cash is a position. So "
            f"is patience.",
            "We are not in the business of calling bottoms, and we will not pretend to see one here. "
            "The value of reading every market on one page is that you notice the tone change early, "
            "size down before you are forced to, and keep enough dry powder to act when the fear is "
            "someone else's problem rather than yours."]
    if vol_share >= 0.5:
        return [
            "If there is one honest forecast in these pages, it is about turbulence rather than "
            "direction, and the model is leaning turbulent. That is not a reason to do anything "
            "dramatic. It is a reason to check that your position sizes assume the wider ranges that "
            "high-volatility regimes reliably deliver.",
            "Volatility is the one market variable that genuinely persists. Calm begets calm and "
            "storms beget storms, which is why a turbulence read carries real skill while a "
            "direction call does not. The practical translation is unglamorous: smaller size into "
            "the same conviction, wider stops or none at all, and no leverage you would not be happy "
            "to hold through a gap.",
            "The mistake to avoid is treating a volatile week as a signal about where prices are "
            "going. It is not. It is a signal about how roughly they will get wherever they go. Trade "
            "the weather you can see, not the destination you cannot."]
    if corr and corr > 0.55:
        return [
            f"The tell this week was correlation. With average cross-asset correlation up near "
            f"{corr:.2f}, markets stopped trading their own stories and started trading a single "
            f"one, and that single story is almost always liquidity. When everything moves together, "
            f"it is usually money, not fundamentals, doing the moving.",
            "That matters because a liquidity-driven tape flatters everyone equally on the way up and "
            "punishes everyone equally on the way down. The diversification you think you own is "
            "thinner than the label suggests, and the only real hedge is the one that is genuinely "
            "uncorrelated, which in practice means less exposure, not cleverer exposure.",
            "We would use a week like this to check the honest question behind every portfolio: if "
            "the liquidity tide goes out, how much of what I own is just beta wearing a costume? The "
            "answer is usually more than you would like."]
    return [
        "Quiet weeks are where the process earns its keep. There is no dramatic move to explain and "
        "no narrative demanding a hot take, which is exactly when the unglamorous work of "
        "diversification and disciplined sizing does its compounding.",
        "The industry hates weeks like this because there is nothing to sell. We prefer them. The "
        "edge in markets was never in predicting the next seven days, which is close to a coin flip "
        "and always will be. It was in owning things that do not all move together, cutting the ones "
        "that break, and letting time do the heavy lifting.",
        "So our opinion this week is to have fewer of them. Do less, watch more, and let the "
        "signal that actually exists, which is volatility, tell you when the weather is about to "
        "turn."]


def weekly_content():
    cm, fxm, com, cg, vr = _piece_data()
    coins, pairs, items = cm.get("coins", []), fxm.get("pairs", []), com.get("items", [])
    if not (coins or pairs or items):
        return None
    F = "chg7"
    cs, fs, ds = (_cstats(coins, "coin", F), _cstats(pairs, "pair", F),
                  _cstats(items, "name", F))
    regime_on = cm.get("regime_on", True)
    reg = "risk-on" if regime_on else "risk-off"
    cross = _cross_movers(F)
    top, bot = (cross[0], cross[-1]) if cross else (None, None)
    top3 = [(k, v) for _, k, v in cross[:3]]
    bot3 = [(k, v) for _, k, v in reversed(cross[-3:])]
    mac = _macro_read(cm, fxm, com, F)
    corr = cm.get("avg_corr")
    dom = cm.get("btc_dominance")
    pd = {c["pair"]: c for c in pairs}
    hic, nc = _vol_outlook(vr, "crypto")
    hif, nf = _vol_outlook(vr, "fx")
    hid, nd = _vol_outlook(vr, "commodity")
    tot_hi, tot_n = hic + hif + hid, max(1, nc + nf + nd)
    cga = {a.get("sym"): a for a in cg.get("assets", [])}
    btc_vt = cga.get("BTC", {}).get("pct_vs_trend")
    phase = cg.get("phase", "")
    eb = cg.get("ethbtc") or {}
    at_risk = [s["coin"] for s in cm.get("stables", []) if s.get("status") != "ok"]
    today = datetime.now()

    lead = []
    if top3 and bot3:
        lead.append(
            f"It was a **{reg}** week. The three strongest markets on the entire board were "
            f"{_fmt_moves(top3)}; the three weakest were {_fmt_moves(bot3)}. When the leaders are "
            f"clustered in one asset class and the laggards in another, the tape is telling you "
            f"where money is rotating, not just what went up.")
    lead.append(
        f"Underneath the headline, breadth was **{'broad' if cs and cs['up'] > cs['n']/2 else 'narrow'}** "
        f"in crypto ({cs['up'] if cs else 0} of {cs['n'] if cs else 0} names higher), the dollar "
        f"finished **{mac['dxi']}**, and commodities {'firmed' if ds and ds['avg'] > 0 else 'eased'} "
        f"on average ({ds['avg']:+.1f}%). The volatility model reads {tot_hi} of {tot_n} tracked "
        f"markets as turbulent looking a week out, so expect the ranges to stay {'wide' if tot_hi >= tot_n/2 else 'contained'}.")
    lead.append("Follow the money, not the noise.")

    crypto = []
    if cs:
        cd = {c["coin"]: c for c in coins}
        b7, e7 = cd.get("BTC", {}).get(F), cd.get("ETH", {}).get(F)
        if b7 is not None and e7 is not None:
            maj = (f"Bitcoin {'added' if b7 >= 0 else 'lost'} {abs(b7):.1f}% and ether "
                   f"{'added' if e7 >= 0 else 'lost'} {abs(e7):.1f}%, but the outsized gains sat "
                   f"further out the risk curve, where **{cs['bn']}** led at {cs['bv']:+.1f}%. ")
        else:
            maj = f"**{cs['bn']}** was the standout at {cs['bv']:+.1f}%. "
        crypto.append(
            f"Crypto traded {reg}, with {cs['up']} of {cs['n']} coins higher on the week. " + maj +
            "When the biggest moves sit in smaller, higher-beta names rather than the majors, it is "
            "the market's way of telling you risk appetite is running ahead of conviction.")
        cyc = []
        if dom is not None:
            cyc.append(f"Bitcoin dominance sits near {dom:.0f}% of total market value")
        if btc_vt is not None:
            cyc.append(f"bitcoin itself trades about {abs(btc_vt):.0f}% "
                       f"{'above' if btc_vt >= 0 else 'below'} the cycle gauge's trend line")
        nvw = _read("btc_metcalfe.json") or {}
        if nvw.get("floor"):
            cyc.append(f"our separate valuation fit, run on a different price history, puts "
                       f"the long-term floor, the level roughly 95% of history has sat above, near "
                       f"{_kfmt(nvw['floor'])}")
        if phase:
            cyc.append(f"the cycle clock reads {phase.lower()}")
        if eb.get("ratio") is not None:
            cyc.append(f"the ether-to-bitcoin ratio is {eb['ratio']:.4f}")
        struct = (_sentences(cyc) if cyc else
                  "The structural picture is little changed from last week.")
        crypto.append(struct + " None of that forecasts next week, but it frames how much room "
                      "the move has before it is fighting its own history.")

    fx = []
    if fs:
        risk_fx = [(p, pd.get(p, {}).get(F)) for p in ("AUDUSD", "NZDUSD")
                   if pd.get(p, {}).get(F) is not None]
        haven_fx = [(p, pd.get(p, {}).get(F)) for p in ("USDJPY", "USDCHF")
                    if pd.get(p, {}).get(F) is not None]
        fx.append(
            f"The dollar was **{mac['dxi']}** on the week. **{fs['bn']}** was the strongest pair we "
            f"track at {fs['bv']:+.1f}% and **{fs['wn']}** the weakest at {fs['wv']:+.1f}%, with "
            f"{fs['up']} of {fs['n']} pairs finishing higher.")
        if risk_fx or haven_fx:
            fx.append(
                "The internals matter more than the averages here. The risk-sensitive commodity "
                "currencies, " + (_fmt_moves(risk_fx) or "the Aussie and Kiwi") + ", and the "
                "traditional havens, " + (_fmt_moves(haven_fx) or "the yen and franc") + ", tend "
                "to pull in opposite directions, and which side won this week is a cleaner read on "
                "global risk appetite than any single equity index.")

    comd = []
    if ds:
        metals = [(n, mac[n.lower()]) for n in ("GOLD", "SILVER", "PLATINUM")
                  if mac.get(n.lower()) is not None]
        energy = [("WTI oil", mac["oil"]), ("Brent", mac["brent"]), ("nat gas", mac["gas"])]
        energy = [(n, v) for n, v in energy if v is not None]
        comd.append(
            f"Commodities {'advanced' if ds['avg'] > 0 else 'slipped'} on balance ({ds['avg']:+.1f}% "
            f"average), led by **{ds['bn']}** at {ds['bv']:+.1f}% with **{ds['wn']}** the laggard "
            f"at {ds['wv']:+.1f}%.")
        parts = []
        if metals:
            parts.append("precious metals ran " + _fmt_moves(metals))
        if energy:
            parts.append("energy showed " + _fmt_moves(energy))
        if mac.get("copper") is not None:
            parts.append(f"and copper, the market's rough gauge of industrial demand, was "
                         f"{mac['copper']:+.1f}%")
        if parts:
            comd.append("Split the complex apart and it tells a fuller story. " + _sentences(parts)
                        + " Copper firm alongside oil points to a growth impulse. Copper soft while "
                        "gold runs points the other way, toward caution and a hunt for safety.")

    cross_read = []
    both = mac.get("gold") is not None and mac.get("capw") is not None
    if both:
        g, c = mac["gold"], mac["capw"]
        if g > 0 and c > 0:
            tell = ("gold and crypto rose together, a signature of abundant liquidity and a "
                    "debasement bid rather than of clean, fundamentals-driven risk-taking")
        elif g > 0 and c <= 0:
            tell = ("gold rose while crypto fell, the classic fingerprint of fear, with money "
                    "paying up for safety and dumping the high-beta end of the risk curve")
        elif g <= 0 and c > 0:
            tell = ("crypto rose while gold slipped, about as clean a risk-on signal as the tape "
                    "offers, with no obvious rush for cover underneath it")
        else:
            tell = "both gold and crypto softened, consistent with liquidity draining out broadly"
        corrbit = (f" Average cross-asset correlation ran near {corr:.2f}, "
                   f"{'high enough that diversification was thin this week' if corr and corr > 0.5 else 'low enough that markets were still trading their own stories'}."
                   if corr is not None else "")
        cross_read.append(f"Read across the whole board, {tell}.{corrbit}")
    if cross_read:
        cross_read.append("One board beats one screen.")

    ahead = [
        "We do not forecast direction over the coming week, because in liquid markets it is close "
        "to a coin flip and pretending otherwise is how people lose money. What we forecast is "
        "weather.",
        "So here it is.",
        f"The volatility model leans **{'turbulent' if hic >= max(1, nc)/2 else 'calmer'}** on "
        f"crypto, **{'turbulent' if hif >= max(1, nf)/2 else 'calmer'}** on FX and "
        f"**{'turbulent' if hid >= max(1, nd)/2 else 'calmer'}** on commodities. Expect the widest "
        f"ranges in {cs['hv']['coin'] if cs and cs['hv'] else '-'}, "
        f"{fs['hv']['pair'] if fs and fs['hv'] else '-'} and "
        f"{ds['hv']['name'] if ds and ds['hv'] else '-'}."
        + (f" On the stablecoin side, keep an eye on {', '.join(at_risk)} for peg stress." if at_risk
           else " Stablecoin pegs look orderly, which is one less thing to worry about.")]

    vol_share = tot_hi / tot_n
    opinion = _weekly_opinion(regime_on, cs, mac, vol_share, corr, top)

    sf = (f"A {reg} week with "
          + (f"{top[1]} leading the board and {bot[1]} lagging. " if top and bot else "")
          + "Below, the full read across crypto, FX and commodities, the cross-asset tell, and our "
            "opinion on what actually matters from here.")
    return dict(
        kicker="Levanter Weekly", title="The Week in Review, and the Week Ahead",
        dateline=f"Week ending {today:%A, %-d %B %Y}", standfirst=sf,
        sections=[("The lead", lead), ("Crypto: the week in review", crypto),
                  ("FX: the week in review", fx),
                  ("Commodities: the week in review", comd),
                  ("The cross-asset read", cross_read),
                  ("The week ahead", ahead),
                  ("Opinion: the Levanter view", opinion)])


def _monthly_opinion(regime_on, phase, mac, bt):
    cool = phase and any(w in phase.lower() for w in ("peak", "cooldown", "late"))
    acc30 = bt.get("30d", {}).get("acc")
    acc90 = bt.get("90d", {}).get("acc")
    skill = (f" Our own volatility read backs this up, landing near {acc30}% at a month and "
             f"{acc90}% at a quarter, while our direction calls sit where theory says they should, "
             f"close to a coin flip." if acc30 and acc90 else "")
    if cool:
        body = [
            "Every cycle produces the same conversation at roughly the same point. The early move "
            "is dismissed, the middle is doubted, the top is celebrated as a new paradigm, and the "
            "cooldown is explained away as a healthy pause right up until it is not. We appear to be "
            "somewhere in the second half of that arc, and the honest position is humility rather "
            "than a target.",
            "The uncomfortable fact the halving math keeps repeating is diminishing returns. Each "
            "era has delivered a smaller multiple than the one before, because a market cannot keep "
            "compounding at the same rate as its base grows without eventually swallowing the entire "
            "world. That is not bearishness. It is arithmetic. The people who lose the most in this "
            "phase are the ones who size their expectations to the last cycle rather than the trend "
            "of cycles.",
            "There is a subtler trap in a cooldown, which is that it can last far longer and feel "
            "far more constructive than a crash. Sideways is not safe. A market that grinds within a "
            "wide range for months trains people out of their discipline, rewards the sellers of "
            "options and the takers of leverage, and then reminds everyone at once why those trades "
            "carried a premium in the first place. Boredom is not the absence of risk. It is often "
            "where risk quietly accumulates.",
            "None of that tells you what price does next month, and we will not pretend it does. "
            "What it tells you is how to hold whatever you hold: with position sizes that assume the "
            "drawdowns of this asset class are real and recurring, not theoretical, and with a plan "
            "that survives being wrong.",
            "The broader point is that structure beats prediction. Where an asset sits against its "
            "own long history, how its volatility is behaving, and whether the whole board is moving "
            "as one are all knowable. The next candle is not." + skill]
    elif not regime_on:
        body = [
            "The month closed risk-off, and risk-off months are where portfolios are quietly "
            "remade. The moves themselves are rarely the damage. The damage is in the decisions "
            "they provoke: the forced selling, the abandoned plan, the sudden discovery that "
            "positions thought to be independent were the same trade all along.",
            "This is the environment that separates a real hedge from a correlated bet in a costume. "
            "When the dollar firms and havens outperform while everything on the risk curve is "
            "marked down together, you are being shown, for free, which parts of your book actually "
            "diversify and which merely felt like they did in calmer weather.",
            "The instinct in these months is to do something, and the something is almost always "
            "wrong. Selling the bottom of a washout feels like risk management and is usually just "
            "the crowd flinching in unison. The antidote is not bravery, which is unreliable, but "
            "preparation: a book sized so that a bad month is survivable without heroics, and a list "
            "written in advance of what you would want to own if it went on sale.",
            "We are not calling a bottom. We do not think anyone reliably can. The value in reading "
            "every market on one page is not prophecy, it is early awareness: seeing the tone change, "
            "trimming before you are forced to, and keeping enough cash and composure to act when "
            "the fear belongs to someone else.",
            "So the monthly opinion is boring on purpose. Hold less than you could. Owe nothing you "
            "could be forced to unwind. And treat the ability to do nothing under pressure as the "
            "edge it actually is." + skill]
    else:
        body = [
            "A month like this one, broadly constructive and without a crisis to narrate, is the "
            "hardest to write about honestly, because the temptation is to manufacture a story that "
            "explains the gains and then quietly implies they will continue. We would rather not.",
            "The durable truth underneath every month, up or down, is that direction over these "
            "horizons is close to unforecastable and the returns that look like skill in a rising "
            "market are mostly just exposure. That is not cynicism. It is the finding of every honest "
            "backtest we have run, and it is oddly liberating, because it points you at the things that "
            "do work.",
            "It is worth being precise about what a green month does and does not tell you. It tells "
            "you that risk was rewarded, which is useful history. It does not tell you that risk will "
            "be rewarded again, which is the only thing anyone actually wants to know and the one "
            "thing the month cannot say. Confusing the two is how good years end badly, with people "
            "sizing up into strength precisely because it has felt easy.",
            "Those things that do work are unglamorous and they compound. Spread risk across markets "
            "that genuinely move to different drummers. Size to the volatility you can actually "
            "measure rather than the conviction you happen to feel. Cut what breaks quickly and let "
            "what works run without interference. Do that for long enough and the arithmetic does "
            "more than any forecast ever could.",
            "That is the whole Levanter thesis in a paragraph, and we will keep saying it because the "
            "industry keeps selling the opposite. Certainty is easy to market and process is not, but "
            "process is the only one of the two that survives contact with reality." + skill]
    closers = [
        "If that all sounds like a counsel of modesty, it is, and deliberately so. The single most "
        "expensive belief in this business is that someone, somewhere, can tell you what happens "
        "next, and the entire architecture of financial media exists to sell you that belief on a "
        "monthly subscription. We are trying to sell you the opposite: a clear-eyed read of what is "
        "knowable, an honest label on what is not, and no pretence in between.",
        "So take from this what the data actually supports and leave the rest. Watch the volatility, "
        "respect the cycle, read every market against every other, and let the process rather than "
        "the prediction carry the weight. We will be back next month with the same discipline and, "
        "in all likelihood, a different-looking market to apply it to."]
    return body + closers


def monthly_content():
    cm, fxm, com, cg, vr = _piece_data()
    coins, pairs, items = cm.get("coins", []), fxm.get("pairs", []), com.get("items", [])
    if not (coins or pairs or items):
        return None
    F = "chg30"
    cs, fs, ds = (_cstats(coins, "coin", F), _cstats(pairs, "pair", F),
                  _cstats(items, "name", F))
    regime_on = cm.get("regime_on", True)
    reg = "risk-on" if regime_on else "risk-off"
    cross = _cross_movers(F)
    top, bot = (cross[0], cross[-1]) if cross else (None, None)
    top3 = [(k, v) for _, k, v in cross[:3]]
    mac = _macro_read(cm, fxm, com, F)
    phase = cg.get("phase", "")
    days_h = cg.get("days_since_halving")
    eb = cg.get("ethbtc") or {}
    cga = {a.get("sym"): a for a in cg.get("assets", [])}
    bt = vr.get("backtest", {})
    dom = cm.get("btc_dominance")
    today = datetime.now()

    review = []
    if top and bot:
        review.append(
            f"The month read **{reg}**. Across every market we cover, the strongest performers were "
            f"{_fmt_moves(top3)}, and the weakest single market was **{bot[1]}** at {bot[2]:+.0f}%. "
            f"The spread between them, and where each sits by asset class, is the month's story in "
            f"one line.")
    if cs:
        cd = {c["coin"]: c for c in coins}
        b30, e30 = cd.get("BTC", {}).get(F), cd.get("ETH", {}).get(F)
        maj = (f"bitcoin {b30:+.0f}% and ether {e30:+.0f}%"
               if b30 is not None and e30 is not None else f"led by {cs['bn']}")
        review.append(
            f"Crypto carried the risk appetite, with {cs['up']} of {cs['n']} coins higher on the "
            f"month ({maj}) and **{cs['wn']}** the notable faller at {cs['wv']:+.0f}%"
            + (f". Bitcoin dominance is near {dom:.0f}%." if dom else "."))
    if fs:
        review.append(
            f"In currencies the dollar was **{mac['dxi']}**. **{fs['bn']}** was the standout pair "
            f"({fs['bv']:+.1f}%) and **{fs['wn']}** the weakest ({fs['wv']:+.1f}%).")
    if ds:
        review.append(
            f"Commodities averaged {ds['avg']:+.1f}%, led by **{ds['bn']}** ({ds['bv']:+.0f}%) with "
            f"**{ds['wn']}** the laggard ({ds['wv']:+.0f}%).")
    if review:
        review.append("That is the month in four lines.")

    macro = []
    macro.append(
        f"Start with the dollar, because it prices everything else. It was **{mac['dxi']}** on the "
        f"month, and a {'firmer' if mac['dollar'] > 0 else 'softer'} dollar tends to "
        f"{'tighten' if mac['dollar'] > 0 else 'ease'} global financial conditions and to "
        f"{'lean against' if mac['dollar'] > 0 else 'support'} commodities and risk assets priced "
        f"in it. This is read from the tape rather than from any headline, but it is the single "
        f"most important number in the paragraph.")
    if mac.get("gold") is not None:
        g = mac["gold"]
        macro.append(
            f"Gold was {g:+.1f}% on the month. Gold is the market's quiet barometer of real rates "
            f"and fear at once, and its strength "
            f"{'alongside a softer dollar is the textbook signature of falling real-rate expectations or a safety bid' if g > 0 and mac['dollar'] < 0 else 'even as the dollar firmed is a louder signal, usually a hunt for safety that overrides the currency headwind' if g > 0 else 'giving way points to the opposite, a market comfortable enough to leave the safety trade'}. "
            f"We read it as a sentiment gauge, not a forecast.")
    if mac.get("copper") is not None and mac.get("oil") is not None:
        cop, oil = mac["copper"], mac["oil"]
        growth = ("a genuine growth impulse" if cop > 0 and oil > 0 else
                  "a growth scare, or at least fading demand" if cop < 0 and oil < 0 else
                  "a mixed message, worth watching but not yet a trend")
        macro.append(
            f"The industrial complex is the reality check on the narrative. Copper, the metal with "
            f"a PhD in economics, was {cop:+.1f}% and oil {oil:+.1f}%. Taken together that points to "
            f"{growth}. When the paper markets and the physical economy disagree, the physical "
            f"economy is usually the one worth believing.")
    macro.append(
        f"Put it on one canvas and the month's macro tell is this: crypto trading {reg} "
        f"{'while gold also bid suggests liquidity and a debasement theme rather than clean, confident risk-taking' if regime_on and (mac.get('gold') or 0) > 0 else 'while gold slipped is about as honest a risk-on signal as markets produce' if regime_on else 'with havens outperforming is the fingerprint of caution'}. "
        f"None of it is a prediction. All of it is context, and context is what stops you reading a "
        f"single market in a vacuum.")
    macro.append("Everything else is downstream of the dollar.")

    cycle = []
    cparts = []
    if phase:
        cparts.append(f"the cycle clock reads **{phase.lower()}**")
    if days_h:
        cparts.append(f"we are roughly {days_h} days past the 2024 halving")
    nvm = _read("btc_metcalfe.json") or {}
    if cga.get("BTC", {}).get("pct_vs_trend") is not None:
        v = cga["BTC"]["pct_vs_trend"]
        cparts.append(f"bitcoin sits about {abs(v):.0f}% {'above' if v >= 0 else 'below'} the "
                      f"**cycle gauge's** trend line")
        if nvm.get("floor") and nvm.get("fair_value"):
            cparts.append(f"our separate **valuation fit**, run on a different price history, "
                          f"puts fair value near {_kfmt(nvm['fair_value'])} and its floor around "
                          f"{_kfmt(nvm['floor'])}; both fit price against network age, so read their "
                          f"agreement as overlap rather than confirmation")
    if cga.get("ETH", {}).get("pct_vs_trend") is not None:
        v = cga["ETH"]["pct_vs_trend"]
        cparts.append(f"ether trades about {abs(v):.0f}% {'above' if v >= 0 else 'below'} its own "
                      f"trend")
    if cga.get("SOL", {}).get("pct_vs_trend") is not None:
        v = cga["SOL"]["pct_vs_trend"]
        cparts.append(f"solana sits about {abs(v):.0f}% {'above' if v >= 0 else 'below'} its own "
                      f"trend")
    if cparts:
        cycle.append("Here is where we stand. " + _sentences(cparts))
    md = nvm.get("metcalfe_diagnostic") or {}
    if md and md.get("r2") is not None:
        cycle.append(
            "A word on how we value the network, because it is fashionable to quote Metcalfe's "
            "Law, the idea that a network is worth the square of its users. It is a good idea that "
            "has stopped working for bitcoin. Fit against active addresses since 2019 it has an "
            f"R-squared of about {md['r2']:.2f} and the wrong sign, because exchange batching, "
            "layer-two activity and post-ETF custody now hide real users from the on-chain count. "
            "What still holds is the plain adoption trend, price against network age, and that is "
            "the fair value and floor we quote. We would rather tell you which model broke than "
            "quote you a number that sounds clever and means nothing.")
    if eb.get("ratio") is not None:
        cycle.append(
            f"The ether-to-bitcoin ratio is {eb['ratio']:.4f}"
            + (f", in roughly the {eb['pctile']:.0f}th percentile of its history" if eb.get("pctile") is not None else "")
            + ". Leadership inside crypto rotates, and the majors do not move as one, which is why "
              "a single 'crypto' number hides more than it reveals.")
    cycle.append(
        "The through-line across cycles remains diminishing returns. Each halving era has delivered "
        "a smaller multiple than the last, for the simple reason that a market cannot compound at "
        "its youthful rate forever without eventually outgrowing everything else in existence. That "
        "is arithmetic, not pessimism, and it argues against assuming the next run rhymes with the "
        "biggest one you remember.")
    cycle.append("Arithmetic, not mood.")

    elevated = any(v.get("30d", {}).get("regime") == "HIGH"
                   for v in vr.get("assets", {}).values())
    corr = cm.get("avg_corr")

    rotation = []
    capw, eqw = cm.get("cap_weighted_ret"), cm.get("equal_weighted_ret")
    cls_avg = {"crypto": cs["avg"] if cs else None, "FX": fs["avg"] if fs else None,
               "commodities": ds["avg"] if ds else None}
    ranked = sorted(((k, v) for k, v in cls_avg.items() if v is not None),
                    key=lambda kv: kv[1], reverse=True)
    if ranked:
        lc, lv = ranked[0]
        gc, gv = ranked[-1]
        rotation.append(
            f"Step back from the individual names and the rotation is clearest at the asset-class "
            f"level. On average **{lc}** did the most work this month ({lv:+.1f}%) and **{gc}** the "
            f"least ({gv:+.1f}%). Which class leads tells you what the market is paying up for. Risk "
            f"and liquidity, or safety and hard assets. That is worth more than any single ticker.")
    if capw is not None and eqw is not None:
        rotation.append(
            f"Inside crypto, the equal-weighted basket returned {eqw:+.0f}% against {capw:+.0f}% "
            f"cap-weighted. "
            + ("The average coin beat the heavyweights, so the move broadened into smaller names. "
               "Historically that signals healthy appetite, and also a later, frothier stage where "
               "the quality bar quietly drops." if eqw > capw else
               "The large names carried the tape while the average coin lagged. That is a narrower "
               "and usually more durable kind of strength, but it leaves less fuel in the "
               "speculative tail.")
            + (f" Dominance near {dom:.0f}% fits the picture." if dom else ""))
    rotation.append(
        "Rotation is worth tracking because it turns before prices do. Leadership passing from the "
        "majors to the small caps, from crypto to gold, or from growth-sensitive metals to "
        "defensive ones, is the market rehearsing its next mood while the index still looks calm. "
        "We would rather catch the rehearsal than wait for the show.")
    rotation.append("Money moves first.")

    risks = []
    bull_bits, bear_bits = [], []
    if regime_on:
        bull_bits.append("the cross-market tape is risk-on")
    if cs and cs["up"] > cs["n"] / 2:
        bull_bits.append("crypto breadth is positive")
    if mac["dollar"] < 0:
        bull_bits.append("a softer dollar is easing conditions")
    if regime_on and (mac.get("gold") or 0) > 0:
        bull_bits.append("gold and crypto are bid together, a liquidity tailwind")
    if phase and any(w in phase.lower() for w in ("peak", "cooldown", "late")):
        bear_bits.append(f"the cycle reads {phase.lower()}")
    bear_bits.append("the halving math points to diminishing returns")
    if elevated:
        bear_bits.append("the volatility model leans turbulent")
    if corr and corr > 0.5:
        bear_bits.append(f"correlations are high near {corr:.2f}, so diversification is thin")
    risks.append("No honest monthly skips the other side of the argument, so here is ours, plainly.")
    risks.append(
        "The bull case. " + (", ".join(bull_bits).capitalize() if bull_bits else
                             "Few clean positives this month") + ". Taken together that is an "
        "environment where risk has been rewarded and the path of least resistance has been up.")
    risks.append(
        "The bear case. " + (", ".join(bear_bits).capitalize() if bear_bits else
                             "Few obvious negatives, which is itself a mild warning") + ". Taken "
        "together that is an environment where the easy gains may already be behind and the margin "
        "for error is thinner than it feels.")
    risks.append(
        "What would change our mind, either way. A decisive break in the dollar, gold rolling over "
        "or accelerating, a spike in cross-asset correlation, or a flip in the volatility regime. "
        "Those are the signals we watch. A loud headline is not one of them.")
    risks.append("Both cases are real.")

    essay = _monthly_opinion(regime_on, phase, mac, bt)
    ahead = [
        "For the month ahead we hold the same discipline. We will not tell you where prices are "
        "going, because we cannot and neither can anyone selling you the opposite. We will tell you "
        "where turbulence is likely to sit, where each market stands against its own history, and "
        "what would change the picture.",
        f"As it stands, the volatility model frames the coming weeks as "
        f"**{'turbulent' if elevated else 'mixed to calmer'}** across the board and the cross-market "
        f"backdrop remains **{reg}**. If the dollar or gold breaks its recent character, or "
        f"correlations spike, that is the signal to revisit the whole read. We will, as the data "
        f"does."]

    sf = (f"A longer look across crypto, FX and commodities for {today:%B}: what moved, the macro "
          f"picture the tape is painting, where we sit in the cycle, and a proper opinion on where "
          f"the balance of risk lies from here.")
    return dict(
        kicker="Levanter Monthly", title="The Month in Markets, and the Bigger Picture",
        dateline=f"{today:%B %Y}", standfirst=sf,
        sections=[("The month in review", review), ("Rotation and leadership", rotation),
                  ("The macro picture", macro), ("Where we are in the cycle", cycle),
                  ("Risks, and what would change our mind", risks),
                  ("Opinion: the Levanter thesis", essay), ("The month ahead", ahead)])


def _md_bold_html(s):
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)


def render_piece_html(c):
    if not c:
        return '<div class="mnote">Not enough data to compose this piece yet.</div>'
    secs = ""
    for head, paras in c["sections"]:
        body = "".join(f"<p>{_md_bold_html(p)}</p>" for p in paras if p)
        if body:
            secs += f'<h3 class="pc-h">{head}</h3>{body}'
    return (f'<article class="piece"><div class="pc-kicker">{c["kicker"]}</div>'
            f'<h2 class="pc-title">{c["title"]}</h2>'
            f'<div class="pc-date">{c["dateline"]}</div>'
            f'<p class="pc-stand">{_md_bold_html(c["standfirst"])}</p>{secs}'
            f'<div class="pc-cta">Explore the live dashboard, updated around the clock, at '
            f'<a href="https://levantermarkets.com">levantermarkets.com</a>. '
            f'Subscribe for the daily, weekly and monthly at '
            f'<a href="https://read.levantermarkets.com">read.levantermarkets.com</a>.</div>'
            f'<div class="pc-foot">&copy; {datetime.now().year} Levanter. Educational market '
            f'analysis across crypto, FX and commodities. Not financial advice.</div></article>')


def render_piece_md(c):
    if not c:
        return ""
    out = [f"# {c['title']}", "", f"*{c['kicker']} · {c['dateline']}*", "",
           f"**{c['standfirst']}**", ""]
    for head, paras in c["sections"]:
        real = [p for p in paras if p]
        if not real:
            continue
        out.append(f"## {head}")
        out.append("")
        for p in real:
            out.append(p)
            out.append("")
    out += ["---",
            "**Explore the live dashboard**, updated around the clock, with every market's full "
            "history, charts and forecasts: levantermarkets.com",
            "",
            "**Subscribe** for the daily, weekly and monthly pieces: read.levantermarkets.com",
            "",
            f"*© {datetime.now().year} Levanter. Educational market analysis across crypto, FX "
            "and commodities. Not financial advice.*"]
    return "\n".join(out)


def _plain(s):
    """Strip the light HTML the on-site paragraphs carry, for plain-text pieces."""
    return s.replace("<b>", "").replace("</b>", "").strip()


_NOTE_FIELD = {"daily": "chg1", "weekly": "chg7", "monthly": "chg30"}
_CLS_NAME = {"crypto": "crypto", "fx": "FX", "commodity": "commodities"}
_MKT_DISP = {"Crypto": "crypto", "FX": "FX", "Commodities": "commodities"}


def _note_markets():
    """(title, rows, key field, plural label, vol-regime class) per asset class."""
    cm = _read("crypto_map.json") or {}
    fxm = _read("fx_map.json") or {}
    com = _read("commodities_map.json") or {}
    return [("Crypto", cm.get("coins", []), "coin", "Coins", "crypto"),
            ("FX", fxm.get("pairs", []), "pair", "Pairs", "fx"),
            ("Commodities", com.get("items", []), "name", "Markets", "commodity")]


def _vol_lean(vr, vrc):
    hi, n = _vol_outlook(vr, vrc)
    return ("turbulent" if (n and hi >= n / 2) else "calmer"), hi, n


def _vol_summary(leans):
    """One grouped line, for the tiers too short to carry a read per market."""
    def join(names):
        return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    turbs = [_MKT_DISP[k] for k, v in leans.items() if v == "turbulent"]
    calms = [_MKT_DISP[k] for k, v in leans.items() if v == "calmer"]
    if not turbs:
        return f"Volatility leans calmer across {join(calms)} looking a week out."
    if not calms:
        return f"Volatility leans turbulent across {join(turbs)} looking a week out."
    return (f"Volatility leans turbulent on {join(turbs)}, calmer on {join(calms)}, "
            f"looking a week out.")


def _moved(v):
    return f"added {v:.1f}%" if v >= 0 else f"lost {abs(v):.1f}%"


def _majors_opener(kind, field, reg, up, n):
    """Lead the weekly and monthly on the majors and the macro read rather than on
    whatever topped the board. The board leader is often a small, fast-moving name,
    and fronting a substantial piece with it misreads the week. It still gets its
    due inside its own market block."""
    cm = _read("crypto_map.json") or {}
    fxm = _read("fx_map.json") or {}
    com = _read("commodities_map.json") or {}
    mac = _macro_read(cm, fxm, com, field)
    cd = {c["coin"]: c for c in cm.get("coins", [])}
    btc, eth = cd.get("BTC", {}).get(field), cd.get("ETH", {}).get(field)
    bits = []
    if btc is not None and eth is not None:
        bits.append(f"bitcoin {_moved(btc)} and ether {_moved(eth)}")
    elif btc is not None:
        bits.append(f"bitcoin {_moved(btc)}")
    bits.append(f"the dollar finished {mac['dxi']}")
    if mac.get("gold") is not None:
        bits.append(f"gold {_moved(mac['gold'])}")
    if mac.get("brent") is not None:
        bits.append(f"Brent {_moved(mac['brent'])}")
    body = (", ".join(bits[:-1]) + " and " + bits[-1]) if len(bits) > 1 else bits[0]
    body = body[0].upper() + body[1:]
    span = "week" if kind == "weekly" else "month"
    tail = (f"{up} of {n} markets finished the week higher." if kind == "weekly"
            else f"{up} of {n} markets are higher over 30 days.")
    return f"A {reg} {span}. {body}. {tail}"


def _note_narrative(kind, top, bot, up, n):
    """One line of read on top of the numbers, so a piece does not open the same
    way every time."""
    span = {"daily": "session", "weekly": "week", "monthly": "month"}[kind]
    if n and up >= n * 0.75:
        return ("Breadth that wide is usually liquidity doing the work rather than any single "
                "story, so treat the leaderboard as a ranking, not a reason.")
    if n and up <= n * 0.3:
        return (f"A narrow {span}. When only a handful of names hold up, the move belongs to those "
                f"names and not to the market.")
    if top[0] != bot[0]:
        return (f"The leaders and the laggards sit in different corners of the board, "
                f"{_CLS_NAME.get(top[0], top[0])} on top and {_CLS_NAME.get(bot[0], bot[0])} at "
                f"the bottom. That is money rotating, not a rising tide.")
    return (f"A split {span}, with the strongest and weakest names in the same asset class. "
            f"Worth seeing where the money settles before reading much into it.")


def _cycle_context():
    """Slower-moving structure, for the monthly tier only."""
    cm = _read("crypto_map.json") or {}
    cg = _read("cycle_gauge.json") or {}
    bits = []
    dom = cm.get("btc_dominance")
    if dom is not None:
        bits.append(f"bitcoin dominance sits near {dom:.0f}% of total market value")
    vt = {a.get("sym"): a for a in cg.get("assets", [])}.get("BTC", {}).get("pct_vs_trend")
    if vt is not None:
        bits.append(f"bitcoin trades about {abs(vt):.0f}% "
                    f"{'above' if vt >= 0 else 'below'} the cycle gauge's trend line")
    if cg.get("phase"):
        bits.append(f"the cycle clock reads {cg['phase'].lower()}")
    corr = cm.get("avg_corr")
    if corr is not None:
        bits.append(f"average correlation across the board is {corr:.2f}, so "
                    f"{'diversification is thin' if corr > 0.5 else 'the names are still moving apart'}")
    if not bits:
        return ""
    # Joined by hand rather than via _sentences, which capitalises each clause and
    # adds its own full stop. Both fight the "Underneath the month," lead-in.
    return "Underneath the month, " + "; ".join(bits) + "."


def _market_line(kind, tier, title, rows, kf, label, vr):
    """One market's line, at the depth the tier calls for."""
    field = _NOTE_FIELD[kind]
    st = _cstats(rows, kf, field)
    if not st:
        return ""
    lean, hi, n7 = _vol_lean(vr, {"Crypto": "crypto", "FX": "fx",
                                  "Commodities": "commodity"}[title])
    if tier == "compact":
        return f"{title} {st['up']}/{st['n']} higher, {st['bn']} {st['bv']:+.1f}%, {st['wn']} {st['wv']:+.1f}%."
    if tier == "mirror":
        # The exact paragraphs the site renders for this market, so the Note and
        # the daily review carry the same words. Two things the site can do that a
        # plain-text Note cannot: it repeats the no-forecast caveat under every
        # heading (stated once up top here instead), and it labels the window
        # "This week (Coins)" where the block title already says Crypto.
        para = _daily_para(rows, kf, label, hi, n7)
        if not para:
            return ""
        review = _review_for(rows, kf, label)
        if review:
            para += " " + review
        para = para.replace("The model does not call direction (that is a "
                            "coin-flip); it flags what to watch. ", "")
        para = para.replace(f"This week ({label}).", "This week.")
        return f"{title}. {_plain(para)}"
    line = f"{title}. {st['up']} of {st['n']} {label.lower()} higher."
    if tier in ("full", "deep"):
        # Top and weakest three supersede a single leader-and-laggard clause, so
        # the longer tiers print those instead of both.
        line += f" Average move {st['avg']:+.1f}%."
        top3 = _topn(rows, kf, field, 3)      # list of (name, value) tuples
        if len(top3) >= 3:
            line += " Top three: " + _fmt_moves(top3) + "."
        bot3 = _topn(rows, kf, field, 3, rev=False)
        if len(bot3) >= 3:
            line += " Weakest three: " + _fmt_moves(bot3) + "."
        if st.get("hv") is not None:
            line += (f" Most volatile: {st['hv'][kf]} "
                     f"(~{st['hv'].get('vol', 0):.0f}% annualised).")
    else:
        line += (f" {st['bn']} led {st['bv']:+.1f}%, {st['wn']} lagged "
                 f"{st['wv']:+.1f}%.")
    if n7:
        line += f" Volatility {lean} near-term ({hi}/{n7} flagged high-vol at 7d)."
    if tier in ("standard", "full", "deep"):
        active = sorted((c for c in rows if c.get("vol") is not None),
                        key=lambda c: c["vol"], reverse=True)[:2]
        if active:
            line += " Most active: " + ", ".join(c[kf] for c in active) + "."
    # Each of the longer tiers carries the neighbouring window for context: the
    # weekly says where the month sits, the monthly says where the week sits.
    if tier == "full":
        mo = _cstats(rows, kf, "chg30")
        if mo:
            line += (f" Zooming out, over 30 days {mo['up']} of {mo['n']} are higher, "
                     f"{mo['bn']} best at {mo['bv']:+.1f}% and {mo['wn']} worst at "
                     f"{mo['wv']:+.1f}%.")
    if title == "Crypto" and tier in ("full", "deep"):
        stables = (_read("crypto_map.json") or {}).get("stables", []) or []
        if stables:
            off = [s["coin"] for s in stables if s.get("status") != "ok"]
            line += (f" Stablecoin pegs: {', '.join(off)} off peg."
                     if off else " Stablecoin pegs all holding, which is one less thing to watch.")
    if tier == "deep":
        wk = _cstats(rows, kf, "chg7")
        if wk:
            line += (f" Over the last 7 days {wk['up']} of {wk['n']} rose, {wk['bn']} best at "
                     f"{wk['bv']:+.1f}% and {wk['wn']} worst at {wk['wv']:+.1f}%.")
        dy = _cstats(rows, kf, "chg1")
        if dy:
            line += f" Yesterday {dy['up']} of {dy['n']} closed higher."
    return line


# kind -> channel -> tier. The daily is a Substack Note only and stays tight.
# LinkedIn carries the weekly and monthly, which run fuller in that order.
_TIERS = {"daily": {"substack": "mirror"},
          "weekly": {"linkedin": "full"},
          "monthly": {"linkedin": "deep"}}


def _closing_read(kind, leans):
    """Sign-off for the weekly and monthly: the one forward-looking call the model
    is willing to make, stated plainly."""
    span = "week" if kind == "weekly" else "month"
    return (f"{_vol_summary(leans)} That is where the ranges should be widest, and it is the only "
            f"part of the {span} ahead we will commit to. Direction we leave alone, because over "
            f"these horizons it is close to a coin-flip and anyone telling you otherwise is "
            f"selling something.")


def _build_note(kind, channel):
    """Plain-text short-form piece. Mirrors the matching review on the site and
    adds a line of narrative. Does not email, does not publish."""
    tier = _TIERS[kind][channel]
    cm = _read("crypto_map.json") or {}
    vr = _read("vol_regime.json") or {}
    cross = _cross_movers(_NOTE_FIELD[kind])
    if not cross:
        return ""
    top, bot = cross[0], cross[-1]
    up = sum(1 for _, _, v in cross if v > 0)
    n = len(cross)
    reg = "risk-on" if cm.get("regime_on", True) else "risk-off"
    now = _now_gst()
    if kind == "daily":
        head = f"Levanter daily · {now:%A %-d %B}"
        opener = (f"{top[1]} led the whole board yesterday ({top[2]:+.1f}%), {bot[1]} lagged "
                  f"({bot[2]:+.1f}%). {up} of {n} markets closed higher. Tape {reg}.")
    elif kind == "weekly":
        # Dated by the week it covers, matching the filename and the site's
        # "Week ending ..." label, not by the day the build happened to run.
        head = f"Levanter weekly · week ending {_week_key(now):%-d %B}"
        opener = _majors_opener(kind, _NOTE_FIELD[kind], reg, up, n)
    else:
        head = f"Levanter monthly · {now:%B %Y}"
        opener = _majors_opener(kind, _NOTE_FIELD[kind], reg, up, n)

    lines = [head, "", opener, ""]
    if tier != "compact":
        lines += [_note_narrative(kind, top, bot, up, n), ""]
    if tier == "mirror":
        lines += ["We do not call direction, because over one session that is a coin-flip. "
                  "What the model does call is where the turbulence is likely to sit.", ""]

    leans = {}
    mkt_lines = []
    for title, rows, kf, label, vrc in _note_markets():
        if not rows:
            continue
        leans[title] = _vol_lean(vr, vrc)[0]
        ln = _market_line(kind, tier, title, rows, kf, label, vr)
        if ln:
            mkt_lines.append(ln)
    if tier == "compact":
        lines += mkt_lines + ["", _vol_summary(leans), ""]
    else:
        for ln in mkt_lines:
            lines += [ln, ""]

    if tier == "deep":
        cyc = _cycle_context()
        if cyc:
            lines += [cyc, ""]
    if kind == "daily":
        if tier == "compact":
            lines += ["We do not call direction, because over one session that is a coin-flip. "
                      "What the model does call is where the turbulence is likely to sit.", ""]
    else:
        lines += [_closing_read(kind, leans), "",
                  f"The full {kind} review, with the charts and the opinion piece, is on "
                  f"Substack: read.levantermarkets.com", ""]
    lines += ["Full board, charts and forecasts: levantermarkets.com",
              "Educational, not advice."]
    return "\n".join(x for x in lines).strip() + "\n"


def daily_note():
    return _build_note("daily", "substack")


def weekly_post():
    return _build_note("weekly", "linkedin")


def monthly_post():
    return _build_note("monthly", "linkedin")


def _teaser(kind, field):
    """One-line Note to post when a big piece drops. Links to the newsletter."""
    cross = _cross_movers(field)
    if not cross:
        return ""
    top, bot = cross[0], cross[-1]
    cm = _read("crypto_map.json") or {}
    reg = "risk-on" if cm.get("regime_on", True) else "risk-off"
    if kind == "weekly":
        return (f"New: the Levanter Weekly. A {reg} week, {top[1]} led the whole board and "
                f"{bot[1]} lagged. The week in review, the week ahead, and an honest opinion on "
                f"what actually matters.\n\nRead it: read.levantermarkets.com\n"
                f"Live market dashboard: levantermarkets.com")
    return (f"New: the Levanter Monthly. {top[1]} led the month, {bot[1]} lagged. The macro "
            f"picture, where we sit in the cycle, and a proper opinion piece.\n\n"
            f"Read it: read.levantermarkets.com\nLive market dashboard: levantermarkets.com")


def _week_key(now):
    """The Sunday that ends the week `now` falls in. The site anchors the weekly
    review to this date, so the writeups key off the same one."""
    return (now - timedelta(days=(now.weekday() + 1) % 7)).date()


def write_writeups():
    """Write Substack-ready Markdown for the daily, weekly and monthly pieces."""
    out_dir = os.path.join(R, "substack")
    os.makedirs(out_dir, exist_ok=True)
    today = _now_gst().strftime("%Y-%m-%d")
    month = _now_gst().strftime("%Y-%m")
    files = {}
    # Only draft a piece on the day it is published, so there is never a stale
    # weekly or monthly sitting around to be posted by mistake. Sunday matches the
    # site, which anchors the weekly to the Sunday that ends the week and freezes
    # it. The site's own review pages come from review_archive.json and are not
    # affected by this gate. Set LEVANTER_FORCE_WRITEUPS=1 to draft out of turn,
    # for a catch-up run after a missed day.
    now = _now_gst()
    force = os.environ.get("LEVANTER_FORCE_WRITEUPS") == "1"
    weekly_day = force or now.weekday() == 6          # Sunday
    monthly_day = force or now.day == 28
    # Anchor to what the site actually shows. update_review_archive() runs first
    # and freezes the week's piece; reading it back here means the Markdown, the
    # docx and the LinkedIn post are the same snapshot as the published article,
    # not a fresher one generated minutes later. Falls back to live content for
    # archive entries written before this was stored.
    arch = _load_archive()
    wentry = (arch.get("weekly", {}) or {}).get(_week_key(now).isoformat(), {})
    mentry = (arch.get("monthly", {}) or {}).get(month, {})
    if weekly_day:
        wmd = wentry.get("md") or (render_piece_md(weekly_content() or {}) if weekly_content() else "")
        if wmd:
            # Named for the week it covers, not the day it was drafted, so a
            # catch-up run cannot produce a file labelled with the wrong week.
            p = os.path.join(out_dir, f"levanter-weekly-{_week_key(now).isoformat()}.md")
            open(p, "w").write(wmd)
            files["weekly"] = p
    if monthly_day:
        mmd = mentry.get("md") or (render_piece_md(monthly_content() or {}) if monthly_content() else "")
        if mmd:
            p = os.path.join(out_dir, f"levanter-monthly-{month}.md")
            open(p, "w").write(mmd)
            files["monthly"] = p
    # daily digest (compact, from the quick per-class notes)
    cm = _read("crypto_map.json") or {}
    fxm = _read("fx_map.json") or {}
    com = _read("commodities_map.json") or {}
    vr = _read("vol_regime.json") or {}
    dlines = [f"# Levanter Daily · {datetime.now():%A, %-d %B %Y}", ""]
    for title, rows, kf, lbl, vrc in [
        ("Crypto", cm.get("coins", []), "coin", "Coins", "crypto"),
        ("FX", fxm.get("pairs", []), "pair", "Pairs", "fx"),
        ("Commodities", com.get("items", []), "name", "Markets", "commodity")]:
        if not rows:
            continue
        hi7, n7 = _vol_outlook(vr, vrc)
        para = _daily_para(rows, kf, lbl, hi7, n7)
        if para:
            dlines += [f"## {title}", "",
                       para.replace("<b>", "**").replace("</b>", "**"), ""]
    dlines += ["---",
               "Live dashboard: levantermarkets.com     Subscribe: read.levantermarkets.com",
               "", "*Levanter. Educational, not financial advice.*"]
    p = os.path.join(out_dir, f"levanter-daily-{today}.md")
    open(p, "w").write("\n".join(dlines))
    files["daily"] = p
    # Short daily Note + one-line teasers for the weekly/monthly
    note = daily_note()
    if note:
        p = os.path.join(out_dir, f"levanter-note-daily-{today}.md")
        open(p, "w").write(note)
        files["note"] = p
    wp = (wentry.get("li") or weekly_post()) if weekly_day else None
    if wp:
        p = os.path.join(out_dir, f"levanter-li-weekly-{_week_key(now).isoformat()}.md")
        open(p, "w").write(wp)
        files["li_weekly"] = p
    mp = (mentry.get("li") or monthly_post()) if monthly_day else None
    if mp:
        p = os.path.join(out_dir, f"levanter-li-monthly-{month}.md")
        open(p, "w").write(mp)
        files["li_monthly"] = p
    wt = _teaser("weekly", "chg7") if weekly_day else None
    if wt:
        p = os.path.join(out_dir, f"levanter-teaser-weekly-{today}.md")
        open(p, "w").write(wt)
        files["teaser_weekly"] = p
    mt = _teaser("monthly", "chg30") if monthly_day else None
    if mt:
        p = os.path.join(out_dir, f"levanter-teaser-monthly-{month}.md")
        open(p, "w").write(mt)
        files["teaser_monthly"] = p
    # Always mirror every piece to Word (.docx) for easy copy-paste
    try:
        import md2docx
        md2docx.convert_dir(out_dir)
        print(f"docx: mirrored {len(files)} pieces to {out_dir}/docx/")
    except Exception as e:
        print("docx skipped (python-docx not installed?):", e)
    return files


def _daily_blocks_html() -> str:
    """The three per-class daily review blocks (crypto / FX / commodities)."""
    cm = _read("crypto_map.json") or {}
    fxm = _read("fx_map.json") or {}
    com = _read("commodities_map.json") or {}
    vr = _read("vol_regime.json") or {}
    dblocks = []
    for title, rows, kf, lbl, vrc in [
        ("Crypto", cm.get("coins", []), "coin", "Coins", "crypto"),
        ("FX", fxm.get("pairs", []), "pair", "Pairs", "fx"),
        ("Commodities", com.get("items", []), "name", "Markets", "commodity")]:
        if not rows:
            continue
        hi7, n7 = _vol_outlook(vr, vrc)
        daily = _daily_para(rows, kf, lbl, hi7, n7)
        txt = _review_for(rows, kf, lbl)
        dblock = f'<div class="revd">{daily}</div>' if daily else ""
        dblocks.append(f'<div class="rev"><div class="revh">{title}</div>'
                       f'<div class="revb">{dblock}{txt}</div></div>')
    return "".join(dblocks)


def update_review_archive() -> dict:
    """Persist today's daily / weekly / monthly reviews into review_archive.json
    so past pieces are kept and shown in an archive, not overwritten each build.
    Daily keyed by day, monthly by month (upsert). Weekly is anchored to the Sunday
    that ENDS the week and FROZEN once, so a re-run mid-week and the Sunday->Monday
    ISO-week roll cannot create a second near-identical weekly."""
    now = _now_gst()
    arch = _load_archive()
    daily = dict(arch.get("daily", {}))
    weekly = dict(arch.get("weekly", {}))
    monthly = dict(arch.get("monthly", {}))

    dhtml = _daily_blocks_html()
    if dhtml:
        dkey = now.strftime("%Y-%m-%d")
        daily[dkey] = {"date": dkey, "label": now.strftime("%A, %-d %B %Y"), "html": dhtml}

    wk = weekly_content()
    if wk:
        # Sunday that ends the current week; weekly is "The Week in Review", so the
        # slug date is the week's END. Freeze once (do not overwrite) so the number
        # of weekly entries is exactly one per week.
        sunday = _week_key(now)
        wkey = sunday.isoformat()
        if wkey not in weekly:
            # Freeze the Markdown and the LinkedIn post in the same instant as the
            # HTML. The site shows this entry for the rest of the week, so anything
            # regenerated later from fresher data would no longer match it.
            weekly[wkey] = {"key": wkey, "date": wkey,
                            "label": "Week ending " + sunday.strftime("%-d %B %Y"),
                            "title": wk.get("title", ""), "html": render_piece_html(wk),
                            "md": render_piece_md(wk), "li": weekly_post()}

    mo = monthly_content()
    if mo:
        mkey = now.strftime("%Y-%m")
        monthly[mkey] = {"key": mkey, "label": now.strftime("%B %Y"),
                         "title": mo.get("title", ""), "html": render_piece_html(mo),
                         "md": render_piece_md(mo), "li": monthly_post()}

    def _cap(d, n):
        return {k: d[k] for k in sorted(d.keys(), reverse=True)[:n]}

    arch = {"daily": _cap(daily, 60), "weekly": _cap(weekly, 16),
            "monthly": _cap(monthly, 18), "updated": now.strftime("%Y-%m-%d %H:%M GST")}
    _save_archive(arch)
    return arch


def _review_slug(cadence, entry):
    """Permalink slug matching build_reviews.py. Daily key is a date, weekly key is
    the week-ending Sunday date, monthly key is YYYY-MM."""
    try:
        if cadence == "daily":
            return f"{entry['date']}-daily"
        return f"{entry['key']}-{cadence}"
    except Exception:
        return None


def _perma_row(cadence, entry):
    sl = _review_slug(cadence, entry)
    if not sl:
        return ""
    return (f'<div class="rev-perma-row"><a href="/reviews/{sl}/">'
            f'Open this review as its own page &#8599;</a></div>')


def _arch_list(title, items, cadence) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<details class="rev-arch-item"><summary>{it["label"]}'
        + (f' <span class="rev-arch-t">{it["title"]}</span>' if it.get("title") else "")
        + f'</summary><div class="rev-arch-b">{_perma_row(cadence, it)}{it["html"]}</div></details>'
        for it in items)
    return f'<div class="rev-arch"><div class="rev-arch-h">{title}</div>{rows}</div>'


def reviews_section() -> str:
    arch = _load_archive()

    def _desc(d):
        return [d[k] for k in sorted(d.keys(), reverse=True)]

    wl, ml, dl = _desc(arch.get("weekly", {})), _desc(arch.get("monthly", {})), _desc(arch.get("daily", {}))

    # Weekly / Monthly current tabs show the latest piece only; every past piece
    # lives on the Archive tab so there is one clear place to browse the history.
    weekly_html = wl[0]["html"] if wl else render_piece_html(weekly_content())
    monthly_html = ml[0]["html"] if ml else render_piece_html(monthly_content())

    # Daily: a dated list, newest first, each day expandable with its date.
    if not dl:
        live = _daily_blocks_html()
        if live:
            dl = [{"date": _now_gst().strftime("%Y-%m-%d"),
                   "label": _now_gst().strftime("%A, %-d %B %Y"), "html": live}]
    day_items = ""
    for i, d in enumerate(dl[:60]):
        op = " open" if i == 0 else ""
        day_items += (f'<details class="rev-day"{op}><summary>{d["label"]}</summary>'
                      f'<div class="rev-day-b">{_perma_row("daily", d)}{d["html"]}</div></details>')
    daily_html = (f'<div class="rev-daily-list">{day_items}</div>'
                  f'<div class="mnote">Daily notes are mechanical (1-day recap plus a volatility '
                  f'watch-list), one entry per day. Not a direction forecast or advice.</div>')

    # Archive: one place with every review we have kept, grouped and dated.
    archive_body = (_arch_list("Monthly", ml[:24], "monthly") + _arch_list("Weekly", wl[:26], "weekly")
                    + _arch_list("Daily", dl[:45], "daily"))
    if not archive_body:
        archive_body = ('<div class="mnote">The archive is filling up. Past daily, weekly and '
                        'monthly reviews collect here as they publish.</div>')
    archive_html = ('<div class="rev-arch-intro">Every review we publish is kept, and each has its own '
                    'page. The latest sits on the Weekly, Monthly and Daily tabs; the full run is below, '
                    'newest first, and the complete index lives at <a href="/reviews/">levantermarkets.com/reviews</a>.</div>'
                    + archive_body)

    nav = ('<div class="rev-tabs">'
           '<button class="rev-tab on" onclick="revShow(\'rev-daily\',this)">Daily</button>'
           '<button class="rev-tab" onclick="revShow(\'rev-weekly\',this)">Weekly</button>'
           '<button class="rev-tab" onclick="revShow(\'rev-monthly\',this)">Monthly</button>'
           '<button class="rev-tab" id="rev-archive-btn" onclick="revShow(\'rev-archive\',this)">'
           'Archive</button></div>')
    return (f'{nav}'
            f'<div id="rev-daily" class="rev-pane active">{daily_html}</div>'
            f'<div id="rev-weekly" class="rev-pane">{weekly_html}</div>'
            f'<div id="rev-monthly" class="rev-pane">{monthly_html}</div>'
            f'<div id="rev-archive" class="rev-pane">{archive_html}</div>')


def about_section() -> str:
    return (
        '<div class="about">'
        f'<div class="about-hero"><div class="about-mark">{HEADER_MARK}</div>'
        '<div><div class="about-h1">Levanter</div>'
        '<div class="about-tag">Reading the winds across crypto, FX and commodities.</div>'
        '</div></div>'
        '<div class="about-block"><h3>What we do</h3><p>Levanter pulls the whole market picture '
        'into one place: what moved and by how much across crypto, foreign exchange and '
        'commodities, which regime each market is in, where the big crypto cycles sit, and '
        'plain-English daily, weekly and monthly reviews. Click any asset for its full history, '
        'volatility and drawdown, and keep the names you care about on a personal watchlist.</p></div>'
        '<div class="about-block"><h3>Our aim</h3><p>To give honest, mechanical market '
        'intelligence that never oversells. We measure what is actually predictable and say so '
        'plainly. Volatility clusters, so a turbulent-or-calm forecast genuinely works (backtested '
        '66 to 74 percent). Direction, over days to weeks, is close to a coin flip in efficient '
        'markets, so we label those calls experimental and never dress them up as advice.</p></div>'
        '<div class="about-block"><h3>How it works</h3><p>Everything is built from public data and '
        'tested point-in-time, with no look-ahead. Signals are rules, not opinions, and the track '
        'record is scored against reality so you can see when the model is right and when it is '
        'not.</p></div>'
        '<div class="about-block"><h3>What Levanter is not</h3><p>Not financial advice, not a '
        'broker, and not a record of anyone\'s trades. There are no positions to follow and nothing '
        'to buy here. It is an educational tool for reading markets, and you stay in control of '
        'every decision.</p></div>'
        '<p class="about-name">Named after the Levanter, the easterly wind of the western '
        'Mediterranean and the Levant.</p></div>')


def track_record_section() -> str:
    vr = _read("vol_regime.json") or {}
    ps = _read("prediction_state.json") or {}
    bt = vr.get("backtest", {})
    hs = vr.get("horizons", [])
    intro = ('<div class="cbanner on"><div class="reg">Track record</div>'
             '<div class="rec">We test every call against reality and show the results in full, '
             'the misses included. The point of '
             'Levanter is honesty, so here is the evidence, updated as the data resolves.</div></div>')

    volcards = ""
    for h in hs:
        b = bt.get(h)
        if not b:
            continue
        e = b.get("edge", 0)
        volcards += (f'<div class="trk-card"><div class="trk-h">{h}</div>'
                     f'<div class="trk-acc">{b.get("acc", 0)}%</div>'
                     f'<div class="trk-sub {"up" if e > 0 else "down" if e < 0 else "mut"}">'
                     f'{e:+d} vs baseline</div>'
                     f'<div class="trk-n">{b.get("n", 0):,} tests</div></div>')
    vol = (f'<div class="subh">Volatility model, the forecast that works</div>'
           f'<div class="trk-note">We predict whether the next period will be turbulent or calm. '
           f'Backtested over five years, point-in-time, on non-overlapping samples. It carries '
           f'real skill, because volatility clusters. Accuracy against a coin-flip baseline:</div>'
           f'<div class="trk-grid">{volcards}</div>') if volcards else ""

    bt = _read_root("direction_backtest.json") or {}
    dirscore = ('<div class="subh">Direction calls, the honest scoreboard</div>'
                '<div class="trk-note">We backtest directional up and down calls against what '
                'actually happened, and log new ones as they are made. As theory predicts in '
                'efficient markets, this sits near a coin flip. We publish it anyway, because '
                'pretending otherwise is how the rest of the industry loses your money.</div>')
    if bt.get("n") and bt.get("accuracy") is not None:
        byc = {c.get("cls"): c for c in bt.get("by_class", [])}
        cr, co = byc.get("crypto", {}), byc.get("commodity", {})
        # Lead with the per-class rows. Always all three, never the good ones alone.
        cls_rows = ""
        for c in bt.get("by_class", []):
            lab = c.get("label", c.get("cls", ""))
            if c.get("n") and c.get("acc") is not None:
                cls_rows += (f'<div class="trk-cls"><span class="k">{lab}</span>'
                             f'<span class="v">{c["acc"]:.0f}% over {c["n"]:,} calls</span></div>')
            else:
                cls_rows += (f'<div class="trk-cls"><span class="k">{lab}</span>'
                             f'<span class="v mut">no resolved calls yet</span></div>')
        dirscore += (f'<div class="trk-line"><b>Backtested {bt.get("period", "")}, point-in-time, '
                     f'and we show every class:</b></div><div class="trk-clsgrid">{cls_rows}</div>')
        if cr.get("n") and cr.get("acc") is not None:
            dirscore += (f'<div class="trk-line">The crypto row is the one that carries weight. At '
                         f'<b>{cr["n"]:,} calls</b> it is a real sample, and at <b>{cr["acc"]:.0f}%</b> '
                         f'it lands right on the coin-flip baseline. That is the thesis, confirmed on '
                         f'the class we have the most data for.</div>')
        if co.get("n") and co.get("acc") is not None:
            dirscore += (f'<div class="trk-note">Commodities looks stronger at <b>{co["acc"]:.0f}%</b>, '
                         f'and it is not an edge. It is {co["n"]} calls across a dozen commodities, '
                         f'about seven a market over four months, so consecutive calls overlap and are '
                         f'not independent trials. Allow even a little of that serial correlation and '
                         f'the effective sample roughly halves, at which point {co["acc"]:.0f}% is no '
                         f'longer statistically significant. The window was a strongly trending one for '
                         f'the metals too, which flatters any directional model until the trend breaks. '
                         f'Treat it as noise, not skill.</div>')
        dirscore += (f'<div class="trk-line">Taken together the classes average '
                     f'<b>{bt["accuracy"]:.0f}%</b>, but that is a weighted blend of {cr.get("n", 0):,} '
                     f'crypto calls and {co.get("n", 0)} commodity calls pulling opposite ways, not a '
                     f'finding in itself. Read the rows, not the blend.</div>')
    # Make staleness visible: state the fixed window, and self-flag if the backtest
    # is past its review date (the live-forward calls will have matured by then).
    close_txt = (f'That backtest is a fixed window, closed on {bt.get("window_close")}. '
                 if bt.get("window_close") else '')
    stale = ""
    ra = bt.get("review_after")
    if ra and _now_gst().date().isoformat() > ra:
        stale = (' <b>This backtest window is now past its review date, so the live calls have '
                 'since matured and should be folded in.</b>')
    dirscore += (f'<div class="trk-line">{close_txt}The live scoreboard, logged as calls are made, '
                 f'takes over from here and is filling up now, scored as each call matures.{stale}</div>')

    method = ('<div class="mnote">Everything is tested point-in-time with no look-ahead, from '
              'public data. Volatility forecasting has real, measurable skill. Price-direction '
              'forecasting does not, and we will never sell you the illusion that it does. '
              'Educational, not financial advice.</div>')
    return intro + vol + dirscore + method


def build_modal_data() -> str:
    """One global AD object (crypto + FX + commodities) + the modal script,
    so a click on any row in any tab opens the same detail popup."""
    import json as _json
    fields = ["coin", "label", "price", "market_cap", "rank", "trend", "signal",
              "risk", "risk_band", "vol", "dd", "ret", "chg7", "chg14", "chg28",
              "chg30", "chg60", "chg180", "chg365", "spark", "hist"]
    chg = ["chg7", "chg14", "chg28", "chg30", "chg60", "chg180", "chg365"]
    ad = {}
    cm = _read("crypto_map.json") or {}
    for c in (cm.get("coins", []) or []):
        ad[c["coin"]] = {k: c.get(k) for k in fields}
    fx = _read("fx_map.json") or {}
    for c in fx.get("pairs", []):
        ad[c["pair"]] = dict(label="FX pair", price=c.get("price"),
                             trend=c.get("trend"), vol=c.get("vol"),
                             ret=c.get("ret"), spark=c.get("spark"),
                             hist=c.get("hist"), **{k: c.get(k) for k in chg})
    co = _read("commodities_map.json") or {}
    for c in co.get("items", []):
        ad[c["name"]] = dict(label="Commodity", price=c.get("price"),
                             trend=c.get("trend"), vol=c.get("vol"),
                             ret=c.get("ret"), spark=c.get("spark"),
                             hist=c.get("hist"), **{k: c.get(k) for k in chg})
    return ('<script>const AD=' + _json.dumps(ad) + ';'
            + COIN_MODAL_JS + CHART_JS + WATCHLIST_JS + '</script>')


HEADER_MARK = (
    '<svg width="46" height="46" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">'
    '<defs><linearGradient id="hm" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#0ea5e9"/><stop offset="0.55" stop-color="#3b82f6"/>'
    '<stop offset="1" stop-color="#6366f1"/></linearGradient></defs>'
    '<rect x="6" y="6" width="108" height="108" rx="28" fill="url(#hm)"/>'
    '<g fill="none" stroke="#fff" stroke-linecap="round">'
    '<path d="M28 80 C50 71 66 71 86 76" stroke-width="8" opacity="0.5"/>'
    '<path d="M28 60 C54 48 74 48 96 55" stroke-width="8.5"/>'
    '<path d="M28 40 C46 33 60 33 76 37" stroke-width="8" opacity="0.82"/></g>'
    '<path d="M86 46 l14 -6 -4 14" fill="none" stroke="#fff" stroke-width="8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>')

SUBSCRIBE_URL = "https://read.levantermarkets.com/subscribe"
SUBSCRIBE_EMBED = "https://read.levantermarkets.com/embed"
SUBSCRIBE_BOX = (
    '<div class="subbox"><div class="subbox-tx">'
    '<div class="subbox-t">Get Levanter in your inbox</div>'
    '<div class="subbox-s">The weekly and monthly in your inbox, plus daily on the site. '
    'Honest, and free.</div></div>'
    '<div class="subbox-form">'
    f'<iframe id="subEmbed" src="{SUBSCRIBE_EMBED}" title="Subscribe to Levanter" width="100%" '
    'height="95" style="border:0;border-radius:10px;background:#fff;display:block" '
    'scrolling="no"></iframe>'
    f'<a id="subBtn" class="subbox-b" style="display:none" href="{SUBSCRIBE_URL}" target="_blank" '
    'rel="noopener">Subscribe</a>'
    f'<a class="subbox-alt" href="{SUBSCRIBE_URL}" target="_blank" rel="noopener">'
    'or subscribe at read.levantermarkets.com</a></div></div>')

TAB_JS = (
    "(function(){var tabs=document.querySelectorAll('#tabs .tab');"
    "function go(t){tabs.forEach(function(x){x.classList.remove('active')});"
    "document.querySelectorAll('.tabpane').forEach(function(p){p.classList.remove('active')});"
    "var b=document.querySelector('#tabs .tab[data-t=\"'+t+'\"]');"
    "var el=document.getElementById('pane-'+t);"
    "if(b)b.classList.add('active');if(el)el.classList.add('active');}"
    "tabs.forEach(function(b){b.addEventListener('click',function(){go(b.dataset.t);"
    "history.replaceState(null,'','#'+b.dataset.t);window.scrollTo(0,0);});});"
    "window.levTab=go;"
    "window.revShow=function(id,btn){var ps=document.querySelectorAll('.rev-pane');"
    "for(var i=0;i<ps.length;i++)ps[i].classList.remove('active');"
    "var el=document.getElementById(id);if(el)el.classList.add('active');"
    "if(btn){var ts=btn.parentNode.querySelectorAll('.rev-tab');"
    "for(var j=0;j<ts.length;j++)ts[j].classList.remove('on');btn.classList.add('on');}};"
    "var h=location.hash.replace('#','');"
    "if(h=='archive'){go('reviews');var ab=document.getElementById('rev-archive-btn');"
    "if(ab)window.revShow('rev-archive',ab);}"
    "else if(h&&document.getElementById('pane-'+h))go(h);"
    "var gh=new Date().getHours(),g=document.getElementById('greet');"
    "if(g)g.textContent=gh<12?'Good morning':gh<18?'Good afternoon':'Good evening';"
    "var gd=document.getElementById('livedate');"
    "if(gd)gd.textContent=new Date().toLocaleDateString(undefined,"
    "{weekday:'short',day:'numeric',month:'short',year:'numeric'});"
    "var se=document.getElementById('subEmbed');"
    "if(se){se.addEventListener('load',function(){se.setAttribute('data-ok','1');});"
    "setTimeout(function(){if(se.getAttribute('data-ok')!=='1'){var b=document.getElementById('subBtn');"
    "if(b){se.style.display='none';b.style.display='inline-block';}}},2200);}"
    "})();")

# Client-side watchlist: persisted in localStorage, rendered from the global AD
# object. No account, nothing uploaded - private to the viewer's browser.
WATCHLIST_JS = r'''
function _lw(){try{return JSON.parse(localStorage.getItem('levWatch')||'[]')}catch(e){return[]}}
function _sw(a){localStorage.setItem('levWatch',JSON.stringify(a));}
function inWatch(k){return _lw().indexOf(k)>=0;}
function toggleWatch(k){k=k||window._curAsset;if(!k)return;var a=_lw(),i=a.indexOf(k);if(i>=0)a.splice(i,1);else a.push(k);_sw(a);renderStar(k);renderWatchlist();updWatchCount();}
function renderStar(k){var el=document.getElementById('mStar');if(!el)return;var on=inWatch(k);el.textContent=on?'★ Watching':'☆ Watch';el.classList.toggle('on',on);}
function updWatchCount(){var b=document.querySelector('#tabs .tab[data-t="watchlist"]');if(b){var n=_lw().filter(function(k){return AD[k];}).length;b.textContent=n?('★ Watchlist ('+n+')'):'☆ Watchlist';}}
function renderWatchlist(){var host=document.getElementById('watchBody');if(!host)return;var a=_lw().filter(function(k){return AD[k];});
if(!a.length){host.innerHTML='<div class="mnote" style="padding:14px 4px">Your watchlist is empty. Open any asset (click a row on Crypto, FX or Commodities) and tap the star, or add one below.</div>';return;}
var rows=a.map(function(k){var c=AD[k];var tc=c.trend==='up'?'up':(c.trend==='down'?'down':'mut');
return '<tr onclick="showAsset(\''+k+'\')"><td class="cn">'+k+'</td><td>'+_px(c.price)+'</td><td class="sp">'+_spark(c.spark,84,24)+'</td><td>'+_mv(c.chg7)+'</td><td>'+_mv(c.chg30)+'</td><td class="'+tc+'">'+(c.trend||'-')+'</td><td><span class="wrm" title="remove" onclick="event.stopPropagation();toggleWatch(\''+k+'\')">✕</span></td></tr>';}).join('');
host.innerHTML='<div class="tablewrap"><table class="coins"><thead><tr><th>Asset</th><th>Price</th><th>90d</th><th>7d</th><th>30d</th><th>Trend</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>';}
function watchAddFromInput(){var el=document.getElementById('watchAdd');if(!el)return;var k=(el.value||'').trim().toUpperCase();
var hit=Object.keys(AD).filter(function(x){return x.toUpperCase()===k;})[0];
if(hit&&!inWatch(hit)){var a=_lw();a.push(hit);_sw(a);renderWatchlist();updWatchCount();}el.value='';}
(function(){var dl=document.getElementById('watchOpts');if(dl){Object.keys(AD).sort().forEach(function(k){var o=document.createElement('option');o.value=k;dl.appendChild(o);});}renderWatchlist();updWatchCount();})();
'''

# Dynamic (hover) price chart in the detail popup + click-to-enlarge for the
# static PNG panels. Both are inline + CSP-safe (no external chart library).
CHART_JS = r'''
function _lastN(a,n){a=a||[];return n?a.slice(Math.max(0,a.length-n)):a;}
function setTF(days,btn){if(window.renderIChart)renderIChart(_lastN(window._curHist,days));if(btn&&btn.parentNode){var cs=btn.parentNode.querySelectorAll('.tfcell');for(var i=0;i<cs.length;i++)cs[i].classList.remove('on');btn.classList.add('on');}}
function renderIChart(a){var host=document.getElementById('mChart');if(!host)return;a=(a||[]).filter(function(n){return typeof n==='number';});
if(a.length<2){host.innerHTML='';return;}
var w=490,h=120,pad=8,n=a.length,lo=Math.min.apply(null,a),hi=Math.max.apply(null,a),rng=(hi-lo)||1;
function X(i){return pad+i/(n-1)*(w-2*pad);}function Y(v){return h-pad-((v-lo)/rng)*(h-2*pad);}
var pts=a.map(function(v,i){return X(i).toFixed(1)+','+Y(v).toFixed(1);}).join(' ');
var col=a[n-1]>=a[0]?'#059669':'#dc2626';
var area='M'+X(0).toFixed(1)+','+(h-pad)+' L'+pts.split(' ').join(' L')+' L'+X(n-1).toFixed(1)+','+(h-pad)+' Z';
host.innerHTML='<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none">'
+'<defs><linearGradient id="icg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'+col+'" stop-opacity="0.22"/><stop offset="1" stop-color="'+col+'" stop-opacity="0"/></linearGradient></defs>'
+'<path d="'+area+'" fill="url(#icg)"/><polyline fill="none" stroke="'+col+'" stroke-width="2" points="'+pts+'"/>'
+'<line id="icln" x1="0" y1="0" x2="0" y2="'+h+'" stroke="#8b97a8" stroke-width="1" style="opacity:0"/>'
+'<circle id="icdot" r="3.5" fill="'+col+'" stroke="#fff" stroke-width="1.5" style="opacity:0"/></svg>'
+'<div id="ictip" class="ictip"></div>';
var svg=host.querySelector('svg'),ln=host.querySelector('#icln'),dot=host.querySelector('#icdot'),tip=host.querySelector('#ictip'),val=document.getElementById('icval');
function at(e){var r=svg.getBoundingClientRect();var cx=(e.touches?e.touches[0].clientX:e.clientX)-r.left;var xw=cx/r.width*w;var i=Math.round((xw-pad)/(w-2*pad)*(n-1));i=Math.max(0,Math.min(n-1,i));var vx=X(i),vy=Y(a[i]);ln.setAttribute('x1',vx);ln.setAttribute('x2',vx);ln.style.opacity=0.6;dot.setAttribute('cx',vx);dot.setAttribute('cy',vy);dot.style.opacity=1;tip.textContent=_px(a[i]);tip.style.opacity=1;if(val)val.textContent='· '+_px(a[i]);}
function off(){ln.style.opacity=0;dot.style.opacity=0;tip.style.opacity=0;if(val)val.textContent='';}
svg.addEventListener('mousemove',at);svg.addEventListener('mouseleave',off);
svg.addEventListener('touchmove',function(e){at(e);e.preventDefault();},{passive:false});svg.addEventListener('touchend',off);}
document.addEventListener('click',function(e){var t=e.target;if(t&&t.tagName==='IMG'&&t.closest&&t.closest('figure')){var lb=document.getElementById('lightbox'),im=document.getElementById('lbimg');if(lb&&im){im.src=t.src;lb.style.display='flex';}}});
'''


APP_JSONLD = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "@id": "https://levantermarkets.com/app/#dataset",
  "name": "Levanter cross-market dashboard",
  "description": "Daily readings across 35 crypto assets, 16 FX pairs and 12 commodities: price, multi-horizon returns, volatility regime classification (turbulent or calm) at 7, 30, 60 and 90 days, stablecoin peg monitoring, and long-horizon bitcoin valuation models. Built from free public sources and tested point-in-time with no look-ahead.",
  "url": "https://levantermarkets.com/app/",
  "creator": { "@id": "https://levantermarkets.com/#organization" },
  "license": "https://levantermarkets.com/app/#about",
  "isAccessibleForFree": true,
  "keywords": ["crypto", "foreign exchange", "commodities", "volatility", "market regime", "backtest"],
  "measurementTechnique": "Point-in-time backtested volatility regime classification with no look-ahead",
  "temporalCoverage": "2021/..",
  "variableMeasured": [
    { "@type": "PropertyValue", "name": "Volatility regime", "description": "TURBULENT or CALM classification at 7, 30, 60 and 90 day horizons. Backtested accuracy 66%, 72%, 72% and 74% respectively." },
    { "@type": "PropertyValue", "name": "Experimental direction call", "description": "Mechanical up or down lean. Explicitly experimental. Expect accuracy near a coin flip." }
  ]
}
</script>"""


def main():
    import sys
    market_only = "--market-only" in sys.argv
    out_path = os.path.join(R, "dashboard.html")
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]

    cards = [] if market_only else collect()
    chart = "" if market_only else equity_chart(cards)
    # Build runners are UTC; Levanter is a Dubai (GST, UTC+4) publication, so
    # stamp the "last updated" time in GST explicitly rather than an unlabelled UTC.
    stamp = (datetime.utcnow() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M") + " GST"
    year = datetime.now().year

    research = [
        ("combined_portfolio.png", "Combined portfolio: core + trend sleeve (validated blend)"),
        ("trend_basket.png", "Diversified trend-following (walk-forward)"),
        ("crypto_walkforward.png", "Crypto momentum (honest walk-forward)"),
        ("carry_basket.png", "Carry basket (9 currencies)"),
        ("walkforward_comparison.png", "FX strategies (walk-forward)"),
    ]
    research_html = ""
    for fn, cap in research:
        b64 = embed_png(fn)
        if b64:
            research_html += (f'<figure><img src="data:image/png;base64,{b64}">'
                              f'<figcaption>{cap}</figcaption></figure>')

    total = sum(c["equity"] for c in cards) or 1
    total_start = sum(c["start"] for c in cards) or 1
    tret = (total / total_start - 1) * 100
    tcls = "up" if tret >= 0 else "down"
    cards_html = "".join(card_html(c, PALETTE[i % len(PALETTE)])
                         for i, c in enumerate(cards))

    icon_b64 = ""
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "brand", "levanter-icon.svg")
    if os.path.exists(icon_path):
        icon_b64 = base64.b64encode(open(icon_path, "rb").read()).decode()

    # Cloudflare Web Analytics: drop your token into cf_analytics.token (git-ignored)
    cf_snippet = ""
    cf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cf_analytics.token")
    if os.path.exists(cf_path):
        _tok = open(cf_path).read().strip()
        if _tok:
            cf_snippet = ('<script type="module" src="https://static.cloudflareinsights.com/'
                          'beacon.min.js"'
                          f' data-cf-beacon=\'{{"token": "{_tok}"}}\'></script>')

    modal_data = build_modal_data()

    # Archive first: it freezes the week's piece, and write_writeups() reads that
    # frozen copy so the deliverables match the published article exactly.
    #
    # These two used to swallow the exception and print a one-line "skipped",
    # which looked close enough to success that a broken build quietly shipped
    # the previous run's files. Print the full traceback and remember the
    # failure; main() exits non-zero at the end. The dashboard HTML is still
    # written first, so a writeup bug cannot take the site down with it.
    failed = []
    try:
        a = update_review_archive()
        print("review archive: %d daily, %d weekly, %d monthly kept"
              % (len(a.get("daily", {})), len(a.get("weekly", {})), len(a.get("monthly", {}))))
    except Exception:
        traceback.print_exc()
        failed.append("review archive")

    try:
        wfiles = write_writeups()
        print("Substack writeups:", ", ".join(sorted(wfiles.values())))
    except Exception:
        traceback.print_exc()
        failed.append("Substack writeups")

    if market_only:
        strat_btn = strat_pane = ""
    else:
        strat_btn = '<button class="tab" data-t="strategies">Strategies</button>'
        strat_pane = (
            f'<section class="tabpane" id="pane-strategies">'
            f'<div class="hl"><span>Combined paper equity<b>£{total:,.0f}</b></span>'
            f'<span>Return<b class="{tcls}">{tret:+.2f}%</b></span>'
            f'<span>Strategies<b>{len(cards)}</b></span></div>'
            f'<div class="grid">{cards_html}</div>'
            f'<div class="panel"><img src="data:image/png;base64,{chart}" alt="equity curves"></div>'
            f'<h2>Research &amp; Validation</h2><div class="gallery">{research_html}</div>'
            f'<div class="note">Simulated accounts, £10,000 each to start. Honestly '
            f'walk-forward-validated edges. The value is diversification and '
            f'drawdown control, not outsized returns.</div></section>')

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://levantermarkets.com/app/">
<meta http-equiv="refresh" content="300">
<title>Levanter · Markets, Signals, Insight</title>
<link rel="icon" href="data:image/svg+xml;base64,{icon_b64}">
<meta name="description" content="Honest market intelligence across crypto, FX and commodities. Volatility yes, direction no. Daily on the site, weekly and monthly in your inbox.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Levanter">
<meta property="og:title" content="Levanter · Markets, Signals, Insight">
<meta property="og:description" content="Honest market intelligence across crypto, FX and commodities. Volatility yes, direction no.">
<meta property="og:url" content="https://levantermarkets.com">
<meta property="og:image" content="https://levantermarkets.com/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Levanter · Markets, Signals, Insight">
<meta name="twitter:description" content="Honest market intelligence across crypto, FX and commodities. Volatility yes, direction no.">
<meta name="twitter:image" content="https://levantermarkets.com/og.png">
{cf_snippet}
{APP_JSONLD}
<style>
  :root{{--bg:#eef1f6;--panel:#ffffff;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;
    --shadow:0 1px 3px rgba(15,23,42,.06),0 8px 24px rgba(15,23,42,.05);
    --grad:linear-gradient(120deg,#0ea5e9,#3b82f6 55%,#6366f1);
    --brand:#3b82f6}}
  @media(prefers-color-scheme:dark){{:root{{--bg:#0b0e14;--panel:#151a23;--fg:#e8edf5;
    --muted:#8b97a8;--line:#232c3a;--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35)}}}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--fg);-webkit-font-smoothing:antialiased;
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}}
  .wrap{{max-width:1120px;margin:0 auto;padding:20px 18px 60px}}
  .hero{{background:var(--grad);border-radius:20px;padding:22px 24px;color:#fff;
    box-shadow:var(--shadow);margin-bottom:20px}}
  .hero h1{{font-size:19px;font-weight:700;margin:0 0 14px;letter-spacing:.2px;
    display:flex;align-items:center;gap:8px}}
  .live-dot{{width:8px;height:8px;border-radius:50%;background:#4ade80;
    box-shadow:0 0 0 0 rgba(74,222,128,.7);animation:pulse 2s infinite}}
  @keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(74,222,128,.6)}}70%{{box-shadow:0 0 0 8px rgba(74,222,128,0)}}100%{{box-shadow:0 0 0 0 rgba(74,222,128,0)}}}}
  .hero .total{{font-size:38px;font-weight:800;letter-spacing:-.5px}}
  .hero .tsub{{opacity:.9;font-size:13px;margin-top:2px}}
  .badge{{display:inline-block;background:rgba(255,255,255,.22);border-radius:20px;
    padding:3px 10px;font-size:13px;font-weight:600;margin-left:8px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:22px}}
  .card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;
    box-shadow:var(--shadow);position:relative;overflow:hidden;transition:transform .15s ease}}
  .card:hover{{transform:translateY(-2px)}}
  .card::before{{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent)}}
  .card-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:10px}}
  .card-title{{font-weight:700;font-size:14px;line-height:1.3}}
  .tf{{display:block;color:var(--muted);font-weight:500;font-size:11px;margin-top:2px}}
  .pill{{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;
    padding:4px 9px;border-radius:20px;white-space:nowrap}}
  .pill.green{{background:rgba(16,185,129,.15);color:#059669}}
  .pill.amber{{background:rgba(245,158,11,.16);color:#d97706}}
  .pill.blue{{background:rgba(99,102,241,.15);color:#4f46e5}}
  .pill.grey{{background:rgba(100,116,139,.16);color:#64748b}}
  .pill.red{{background:rgba(220,38,38,.16);color:#dc2626}}
  .hl{{display:flex;flex-wrap:wrap;gap:22px;margin:0 4px 16px;font-size:12px;color:var(--muted)}}
  .hl b{{color:var(--fg);font-size:15px;display:block}}
  .subh{{font-weight:700;font-size:13px;margin:8px 4px 10px}}
  .pegs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:10px;margin-bottom:20px}}
  .peg{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;box-shadow:var(--shadow)}}
  .peg .nm{{font-weight:700;font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:6px}}
  .peg .px{{font-size:18px;font-weight:800}} .peg .lo{{font-size:11px;color:var(--muted)}}
  .up{{color:#059669;font-weight:600}} .down{{color:#dc2626;font-weight:600}} .mut{{color:var(--muted)}}
  .nv-card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:16px 18px;box-shadow:var(--shadow);margin-bottom:14px}}
  .nv-lead{{font-size:14px;line-height:1.65;margin-bottom:6px}}
  .nv-metc{{font-size:12.5px;line-height:1.6;color:var(--muted);margin-top:14px;
    border-top:1px solid var(--line);padding-top:11px}}
  .cbanner{{display:flex;flex-wrap:wrap;gap:6px 20px;align-items:center;justify-content:space-between;
    border-radius:16px;padding:14px 18px;margin-bottom:16px;box-shadow:var(--shadow);color:#fff}}
  .cbanner.on{{background:linear-gradient(120deg,#065f46,#10b981)}}
  .cbanner.off{{background:linear-gradient(120deg,#7c2d12,#f59e0b)}}
  .cbanner .reg{{font-weight:800;font-size:16px;letter-spacing:.3px}}
  .cbanner .rec{{font-size:13px;opacity:.96}}
  .tablewrap{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);
    border-radius:16px;box-shadow:var(--shadow);margin-bottom:22px}}
  table.coins{{width:100%;border-collapse:collapse;font-size:13px;min-width:580px}}
  table.coins th{{text-align:right;color:var(--muted);font-weight:600;font-size:10px;
    text-transform:uppercase;letter-spacing:.4px;padding:10px 12px;border-bottom:1px solid var(--line)}}
  table.coins th:nth-child(1),table.coins th:nth-child(2),table.coins th:nth-child(4){{text-align:left}}
  table.coins td{{text-align:right;padding:8px 12px;border-bottom:1px solid var(--line);
    font-variant-numeric:tabular-nums}}
  table.coins tr:last-child td{{border-bottom:none}}
  table.coins td.cn{{text-align:left;font-weight:700}}
  table.coins td.sp{{text-align:left;width:90px}}
  table.coins tbody tr:hover{{background:var(--bg)}}
  .movers{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:22px}}
  .mvcard{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow)}}
  .mvcard .mvh{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:700;margin-bottom:8px}}
  .mvrow{{display:flex;justify-content:space-between;align-items:center;font-size:13px;padding:3px 0}}
  .mvrow .mvc{{font-weight:700}}
  table.coins tbody tr{{cursor:pointer}}
  .ctag{{font-size:9px;font-weight:700;text-transform:uppercase;background:rgba(245,158,11,.16);
    color:#d97706;padding:2px 6px;border-radius:6px;margin-left:6px;letter-spacing:.3px}}
  .modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:50;
    align-items:center;justify-content:center;padding:16px}}
  .modalbox{{background:var(--panel);border:1px solid var(--line);border-radius:18px;
    max-width:540px;width:100%;padding:22px;box-shadow:0 20px 60px rgba(0,0,0,.45)}}
  .modalhead{{display:flex;justify-content:space-between;align-items:center;font-size:18px;font-weight:800;margin-bottom:8px}}
  .mclose{{cursor:pointer;color:var(--muted);font-size:15px}}
  .mprice{{font-size:30px;font-weight:800;display:flex;align-items:center;gap:14px;margin-bottom:16px;flex-wrap:wrap}}
  .mmoves{{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:16px}}
  .mvcell{{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:8px 3px;text-align:center;font-size:12px}}
  .mvk{{color:var(--muted);font-size:9px;text-transform:uppercase;margin-bottom:3px}}
  .mstats{{display:grid;grid-template-columns:1fr 1fr;gap:2px 20px}}
  .mrow{{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:7px 0;font-size:13px}}
  .mk{{color:var(--muted)}} .mvv{{font-weight:600}}
  .mnote{{color:var(--muted);font-size:11px;margin-top:14px}}
  .cyc-banner{{background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:10px 14px;font-size:13px;margin-bottom:12px}}
  .cyc-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px;margin-bottom:12px}}
  .cyc-card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;box-shadow:var(--shadow)}}
  .cyc-h{{font-weight:700;font-size:14px;margin-bottom:4px}}
  .cyc-sym{{color:var(--muted);font-weight:500;font-size:11px}}
  .cyc-px{{font-size:22px;font-weight:800}}
  .cyc-metric{{font-size:13px;font-weight:700;margin:2px 0}}
  .cyc-phase{{font-size:11px;color:var(--muted);margin-top:4px}}
  .meter{{position:relative;height:8px;border-radius:5px;background:linear-gradient(90deg,#10b981,#f59e0b,#dc2626);margin:9px 0 3px}}
  .mmark{{position:absolute;top:-3px;width:3px;height:14px;background:var(--fg);border-radius:2px;transform:translateX(-50%)}}
  .mlbl{{display:flex;justify-content:space-between;font-size:9px;color:var(--muted)}}
  .cyc-eb{{font-size:12px;color:var(--muted);margin-bottom:16px;background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
  .cyc-proj{{font-size:11px;color:var(--fg);margin-top:7px;padding-top:7px;border-top:1px solid var(--line)}}
  .pred-warn{{background:linear-gradient(120deg,#7c2d12,#b91c1c);color:#fff;border-radius:12px;padding:11px 15px;font-size:12px;margin-bottom:12px;font-weight:600;line-height:1.5}}
  .pred-score{{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:13px;margin-bottom:12px}}
  .pred-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:10px}}
  .pred-card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;box-shadow:var(--shadow);text-align:center}}
  .pred-h{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}}
  .pred-dir{{font-size:19px;font-weight:800;margin:4px 0}}
  .pred-prob{{font-size:11px;color:var(--muted)}}
  .pred-recent{{font-size:13px;color:var(--muted);margin-bottom:20px}}
  .of-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:8px;margin-bottom:20px}}
  .of-card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:9px 8px;box-shadow:var(--shadow);text-align:center}}
  .of-c{{font-weight:700;font-size:13px}}
  .of-buy{{font-size:12px;font-weight:700;margin:2px 0}}
  .of-f{{font-size:10px;color:var(--muted)}}
  .vr-hi{{background:rgba(245,158,11,.16);color:#d97706;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}}
  .vr-lo{{background:rgba(16,185,129,.15);color:#059669;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}}
  table.vr-table th,table.vr-table td{{text-align:center}}
  table.vr-table td.cn{{text-align:left}}
  .eq{{font-size:30px;font-weight:800;letter-spacing:-.5px}}
  .ret{{font-size:14px;font-weight:700;margin:2px 0 12px}}
  .ret.up{{color:#059669}} .ret.down{{color:#dc2626}}
  .ret .meta{{color:var(--muted);font-weight:500}}
  .sig{{font-size:12px;background:var(--bg);border-radius:10px;padding:10px 12px;line-height:1.7;
    color:var(--fg);border:1px solid var(--line)}}
  .panel{{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px;
    box-shadow:var(--shadow);margin-bottom:26px}}
  h2{{font-size:14px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);
    margin:26px 4px 12px}}
  .gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}}
  figure{{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:10px;box-shadow:var(--shadow)}}
  img{{max-width:100%;display:block;border-radius:8px}}
  figcaption{{color:var(--muted);font-size:12px;margin-top:8px;padding:0 4px 4px}}
  .note{{color:var(--muted);font-size:12px;margin-top:26px;border-top:1px solid var(--line);
    padding-top:16px;line-height:1.6}}
  code{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:12px}}
  .brand{{display:flex;align-items:center;gap:14px;margin:4px 2px 16px}}
  .bmark{{flex:0 0 auto;line-height:0}}
  .bname{{font-size:26px;font-weight:800;letter-spacing:.3px;line-height:1}}
  .btag{{font-size:10.5px;font-weight:700;letter-spacing:2.6px;text-transform:uppercase;
    color:var(--muted);margin-top:5px}}
  .bmeta{{margin-left:auto;font-size:12px;color:var(--muted);display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}}
  .bmeta .stamp{{margin-left:8px;opacity:.7}}
  .brief{{display:flex;align-items:center;gap:16px;flex-wrap:wrap;background:var(--grad);
    color:#fff;border-radius:16px;padding:15px 18px;margin-bottom:18px;box-shadow:var(--shadow)}}
  .brief-k{{font-size:10.5px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;opacity:.9;white-space:nowrap}}
  .brief-t{{font-size:13.5px;font-weight:600;line-height:1.5;flex:1;min-width:200px}}
  .brief-b{{appearance:none;border:0;background:rgba(255,255,255,.22);color:#fff;font-weight:700;
    font-size:12px;padding:8px 14px;border-radius:10px;cursor:pointer;white-space:nowrap;font-family:inherit}}
  .brief-b:hover{{background:rgba(255,255,255,.34)}}
  .mhead-r{{display:flex;align-items:center;gap:14px}}
  .mstar{{cursor:pointer;font-size:12px;font-weight:700;color:var(--muted);white-space:nowrap;
    border:1px solid var(--line);border-radius:8px;padding:4px 9px}}
  .mstar.on{{color:#d97706;border-color:rgba(245,158,11,.5);background:rgba(245,158,11,.1)}}
  .watchadd{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
  .watchadd input{{flex:1;min-width:220px;background:var(--panel);border:1px solid var(--line);
    border-radius:10px;padding:10px 13px;color:var(--fg);font-size:13px;font-family:inherit}}
  .watchadd .brief-b{{background:var(--grad)}}
  .wrm{{cursor:pointer;color:var(--muted);font-weight:700;padding:0 6px}}
  .wrm:hover{{color:#dc2626}}
  .tabs{{display:flex;gap:5px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);
    border-radius:14px;padding:6px;box-shadow:var(--shadow);margin-bottom:20px;position:sticky;top:8px;z-index:20}}
  .tab{{appearance:none;border:0;background:transparent;color:var(--muted);font-weight:700;
    font-size:13px;padding:9px 15px;border-radius:10px;cursor:pointer;font-family:inherit}}
  .tab:hover{{color:var(--fg)}}
  .tab.active{{background:var(--grad);color:#fff}}
  .tabpane{{display:none}}
  .tabpane.active{{display:block;animation:fade .25s ease}}
  @keyframes fade{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
  .xboards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:10px}}
  @media(max-width:640px){{.xboards{{grid-template-columns:1fr}}}}
  .xboard{{background:var(--panel);border:1px solid var(--line);border-radius:16px;
    padding:4px 14px 10px;box-shadow:var(--shadow)}}
  .xrow{{display:flex;justify-content:space-between;align-items:center;padding:9px 2px;
    border-bottom:1px solid var(--line);cursor:pointer;font-size:14px}}
  .xrow:last-child{{border-bottom:none}} .xrow:hover{{background:var(--bg)}}
  .xk{{display:flex;align-items:center;gap:9px;font-weight:700}} .xk .pill{{font-size:9px}}
  .rev{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
    box-shadow:var(--shadow);margin-bottom:14px}}
  .revh{{font-weight:800;font-size:15px;margin-bottom:7px}}
  .revb{{font-size:13.5px;line-height:1.7;color:var(--fg)}}
  .rev-tabs{{display:flex;gap:6px;margin-bottom:16px}}
  .rev-tab{{appearance:none;border:1px solid var(--line);background:var(--panel);color:var(--muted);
    font-weight:700;font-size:12.5px;padding:7px 16px;border-radius:10px;cursor:pointer;font-family:inherit}}
  .rev-tab.on{{background:var(--grad);color:#fff;border-color:transparent}}
  .rev-pane{{display:none}} .rev-pane.active{{display:block}}
  .rev-arch{{margin-top:26px;border-top:1px solid var(--line);padding-top:16px}}
  .rev-arch-h{{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:1.2px;
    color:var(--muted);margin-bottom:10px}}
  details.rev-arch-item,details.rev-day{{border:1px solid var(--line);border-radius:11px;
    margin-bottom:8px;background:var(--panel)}}
  details.rev-arch-item>summary,details.rev-day>summary{{cursor:pointer;padding:12px 15px;
    font-weight:700;font-size:14px;list-style:none;user-select:none}}
  details>summary::-webkit-details-marker{{display:none}}
  details.rev-day>summary::before,details.rev-arch-item>summary::before{{content:'\\25B8';
    color:var(--muted);margin-right:9px;font-size:11px}}
  details[open].rev-day>summary::before,details[open].rev-arch-item>summary::before{{content:'\\25BE'}}
  .rev-day-b,.rev-arch-b{{padding:2px 15px 12px}}
  .rev-arch-t{{color:var(--muted);font-weight:600}}
  .rev-daily-list details.rev-day:first-child{{border-color:var(--brand)}}
  .rev-arch-intro{{color:var(--muted);font-size:14px;line-height:1.6;margin-bottom:20px;max-width:640px}}
  .rev-perma-row{{margin:2px 0 12px}}
  .rev-perma-row a{{font-size:12.5px;font-weight:700;color:var(--brand);text-decoration:none}}
  .rev-perma-row a:hover{{text-decoration:underline}}
  #rev-archive .rev-arch:first-of-type{{margin-top:0;border-top:0;padding-top:0}}
  .piece{{max-width:720px;background:var(--panel);border:1px solid var(--line);border-radius:16px;
    padding:26px 28px;box-shadow:var(--shadow)}}
  .pc-kicker{{font-size:11px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:var(--brand)}}
  .pc-title{{font-size:24px;font-weight:800;letter-spacing:-.2px;margin:6px 0 4px;line-height:1.2;color:var(--fg)}}
  .pc-date{{font-size:12px;color:var(--muted);margin-bottom:14px}}
  .pc-stand{{font-size:16px;line-height:1.6;font-weight:600;color:var(--fg);margin:0 0 18px;
    padding-bottom:16px;border-bottom:1px solid var(--line)}}
  .pc-h{{font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;
    color:var(--muted);margin:20px 0 6px}}
  .piece p{{font-size:14.5px;line-height:1.75;color:var(--fg);margin:0 0 12px}}
  .pc-cta{{font-size:13px;line-height:1.6;color:var(--fg);margin-top:20px;padding:14px 16px;
    background:rgba(59,130,246,.08);border:1px solid var(--line);border-radius:12px}}
  .pc-cta a{{color:var(--brand);font-weight:700;text-decoration:none}}
  .pc-foot{{font-size:11.5px;color:var(--muted);margin-top:14px;padding-top:14px;border-top:1px solid var(--line)}}
  .subbox{{background:var(--grad);color:#fff;border-radius:18px;padding:20px 24px;margin-bottom:20px;
    box-shadow:var(--shadow);display:flex;align-items:center;gap:18px;flex-wrap:wrap}}
  .subbox-tx{{flex:1;min-width:220px}}
  .subbox-t{{font-size:18px;font-weight:800;letter-spacing:.2px}}
  .subbox-s{{font-size:13px;opacity:.95;margin-top:3px;line-height:1.5}}
  .subbox-b{{background:#fff;color:#1e3a8a;font-weight:800;font-size:14px;padding:11px 20px;
    border-radius:11px;text-decoration:none;white-space:nowrap}}
  .subbox-b:hover{{background:#eef2ff}}
  .subbox-form{{flex:0 0 auto;width:min(460px,100%)}}
  .subbox-form iframe{{width:100%}}
  .subbox-alt{{display:block;font-size:11px;color:#e8f1ff;margin-top:7px;text-decoration:underline}}
  .trk-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:12px;margin-bottom:8px}}
  .trk-card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 12px;
    box-shadow:var(--shadow);text-align:center}}
  .trk-h{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:700}}
  .trk-acc{{font-size:30px;font-weight:800;letter-spacing:-.5px;margin:4px 0 2px;color:var(--brand)}}
  .trk-sub{{font-size:12px;font-weight:700}}
  .trk-n{{font-size:11px;color:var(--muted);margin-top:2px}}
  .trk-note{{font-size:13px;line-height:1.6;color:var(--fg);margin:0 4px 12px}}
  .trk-clsgrid{{display:flex;flex-wrap:wrap;gap:8px;margin:2px 4px 12px}}
  .trk-cls{{display:flex;gap:8px;align-items:baseline;background:var(--panel);border:1px solid var(--line);
    border-radius:10px;padding:8px 12px;font-size:13px}}
  .trk-cls .k{{font-weight:800}} .trk-cls .v.mut{{color:var(--muted)}}
  .trk-line{{font-size:15px;line-height:1.6;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);margin-bottom:8px}}
  .revd{{border-left:3px solid var(--brand,#3b82f6);padding:2px 0 2px 12px;margin-bottom:10px;
    background:linear-gradient(90deg,rgba(59,130,246,.07),transparent)}}
  .about{{max-width:760px}}
  .about-hero{{display:flex;align-items:center;gap:16px;background:var(--grad);color:#fff;
    border-radius:18px;padding:22px 24px;margin-bottom:18px;box-shadow:var(--shadow)}}
  .about-mark{{line-height:0}}
  .about-h1{{font-size:26px;font-weight:800;letter-spacing:.3px}}
  .about-tag{{font-size:13px;opacity:.95;margin-top:3px}}
  .about-block{{background:var(--panel);border:1px solid var(--line);border-radius:14px;
    padding:16px 18px;margin-bottom:12px;box-shadow:var(--shadow)}}
  .about-block h3{{margin:0 0 6px;font-size:14px;font-weight:800;color:var(--brand)}}
  .about-block p{{margin:0;font-size:13.5px;line-height:1.7;color:var(--fg)}}
  .about-name{{font-size:12px;color:var(--muted);font-style:italic;margin:14px 4px 0}}
  .lfooter{{margin-top:34px;padding-top:20px;border-top:1px solid var(--line)}}
  .lfoot-brand{{display:flex;align-items:center;gap:12px;margin-bottom:12px}}
  .lfoot-mark svg{{width:38px;height:38px}}
  .lfoot-name{{font-size:17px;font-weight:800;line-height:1}}
  .lfoot-tag{{font-size:9.5px;font-weight:700;letter-spacing:2.2px;text-transform:uppercase;color:var(--muted);margin-top:4px}}
  .lfoot-nav{{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:12px}}
  .lfoot-nav span{{font-size:12.5px;font-weight:600;color:var(--muted);cursor:pointer}}
  .lfoot-nav span:hover{{color:var(--brand)}}
  .lfoot-sub{{color:var(--brand);font-weight:800;text-decoration:none}}
  .lfoot-note{{font-size:11.5px;color:var(--muted);line-height:1.6;max-width:720px}}
  .lfoot-copy{{font-size:11.5px;color:var(--muted);margin-top:10px;font-weight:600}}
  figure img{{cursor:zoom-in}}
  .lightbox{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:60;
    align-items:center;justify-content:center;padding:22px;cursor:zoom-out}}
  .lightbox img{{max-width:96%;max-height:96%;border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,.5)}}
  .mchart{{margin:2px 0 14px;position:relative}}
  .mchart svg{{display:block;width:100%;height:120px;border:1px solid var(--line);border-radius:10px;background:var(--bg)}}
  .mchart .ictip{{position:absolute;top:6px;right:8px;font-size:12px;font-weight:700;
    background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:3px 8px;
    pointer-events:none;opacity:0;transition:opacity .1s}}
  .tfcell{{cursor:pointer;transition:border-color .12s,background .12s}}
  .tfcell:hover{{border-color:var(--brand)}}
  .mvcell.on{{border-color:var(--brand);background:rgba(59,130,246,.12)}}
</style></head><body><div class="wrap">
  <header class="brand">
    <div class="bmark">{HEADER_MARK}</div>
    <div class="bwords"><div class="bname">Levanter</div>
      <div class="btag">Markets · Signals · Insight</div></div>
    <div class="bmeta"><span id="greet">Welcome</span> · <span class="live-dot"></span>Live
      · <span id="livedate"></span><span class="stamp">data {stamp}</span></div>
  </header>
  <nav class="tabs" id="tabs">
    <button class="tab active" data-t="home">Home</button>
    <button class="tab" data-t="crypto">Crypto</button>
    <button class="tab" data-t="fx">FX</button>
    <button class="tab" data-t="commodities">Commodities</button>
    <button class="tab" data-t="reviews">Reviews</button>
    <button class="tab" data-t="track">Track record</button>
    <button class="tab" data-t="watchlist">☆ Watchlist</button>
    {strat_btn}
    <button class="tab" data-t="about">About</button>
  </nav>
  <section class="tabpane active" id="pane-home">{home_section(cards)}</section>
  <section class="tabpane" id="pane-crypto">{crypto_section()}</section>
  <section class="tabpane" id="pane-fx">{fx_section()}</section>
  <section class="tabpane" id="pane-commodities">{commodities_tab_section()}</section>
  <section class="tabpane" id="pane-reviews">{reviews_section()}</section>
  <section class="tabpane" id="pane-track">{track_record_section()}</section>
  <section class="tabpane" id="pane-watchlist">
    <div class="subh">Your watchlist <span class="mut">(saved privately in this browser)</span></div>
    <div class="watchadd"><input id="watchAdd" list="watchOpts" autocomplete="off"
      placeholder="Add an asset, e.g. BTC, EURUSD, GOLD"
      onkeydown="if(event.key==='Enter'){{event.preventDefault();watchAddFromInput();}}">
      <datalist id="watchOpts"></datalist>
      <button class="brief-b" onclick="watchAddFromInput()">Add</button></div>
    <div id="watchBody"></div>
    <div class="mnote">Your watchlist lives only in this browser (localStorage), no account,
    nothing uploaded. Click any asset for detail; ✕ removes it. You can also star an asset
    from its detail popup.</div>
  </section>
  {strat_pane}
  <section class="tabpane" id="pane-about">{about_section()}</section>
  <footer class="lfooter">
    <div class="lfoot-brand"><div class="lfoot-mark">{HEADER_MARK}</div>
      <div><div class="lfoot-name">Levanter</div>
      <div class="lfoot-tag">Markets · Signals · Insight</div></div></div>
    <div class="lfoot-nav">
      <span onclick="levTab('home')">Home</span><span onclick="levTab('crypto')">Crypto</span>
      <span onclick="levTab('fx')">FX</span><span onclick="levTab('commodities')">Commodities</span>
      <span onclick="levTab('reviews')">Reviews</span><span onclick="levTab('about')">About</span>
      <a href="{SUBSCRIBE_URL}" target="_blank" rel="noopener" class="lfoot-sub">Subscribe &rarr;</a></div>
    <div class="lfoot-note">Educational market analysis across crypto, FX and commodities.
    Historical moves and mechanical signals only, not forecasts, not financial advice.
    Data from public sources. Updated {stamp}.</div>
    <div class="lfoot-copy">&copy; {year} Levanter. All rights reserved.</div>
  </footer>
  {MODAL_HTML}
  <div id="lightbox" class="lightbox" onclick="this.style.display='none'"><img id="lbimg" alt="chart"></div>
  {modal_data}
  <script>{TAB_JS}</script>
</div></body></html>"""

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"Dashboard written: {out_path}")

    if failed:
        raise SystemExit(
            "\nBUILD FAILED: " + " and ".join(failed) + " did not complete (traceback above).\n"
            "The dashboard HTML was written, but the pieces above are STALE or MISSING. "
            "Do not post anything from reports/substack until this is fixed.")


if __name__ == "__main__":
    main()
