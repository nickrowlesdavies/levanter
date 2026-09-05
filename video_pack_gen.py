#!/usr/bin/env python3
"""Levanter weekly video pack: branded PNG cards + insert graphics for the weekly
YouTube/Shorts, rendered from live data so the on-screen figures match the script.

Writes a dated pack to reports/video/pack-<YYYY-MM-DD>/ containing the title card,
CTA card, disclaimer card, a persistent lower-third, and one insert card per beat
(volatility skill, this-week map, bitcoin valuation with callouts, direction
scoreboard), plus a caption strip. All 1920x1080 (16:9) unless noted; the title
and CTA also render 1080x1920 (9:16) for the Shorts.

    python video_pack_gen.py [--date YYYY-MM-DD]

Cards are flat RGB (or RGBA where transparency is needed), matplotlib-rendered so
there is no headless-browser dependency on CI.
"""
import datetime as dt
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from PIL import Image

CMAP = LinearSegmentedColormap.from_list("lev", ["#0ea5e9", "#3b82f6", "#6366f1"])
BRAND = "#3b82f6"
INK = "#0f172a"
MUT = "#64748b"


def _read(p):
    try:
        return json.load(open(os.path.join("reports", p)))
    except Exception:
        return {}


def _gradient(ax, W, H):
    X, Y = np.meshgrid(np.linspace(0, 1, 200), np.linspace(0, 1, 120))
    ax.imshow(X * 0.7 + Y * 0.3, extent=[0, W, H, 0], cmap=CMAP,
              aspect="auto", interpolation="bilinear", zorder=0)


def _windmark(ax, x, y, s, color="#ffffff"):
    """Wind-mark + send-arrow at (x,y), scale s (px per 120-unit)."""
    def T(px, py):
        return (x + px * s, y + py * s)

    def gust(p0, c1, c2, p3, sw, a):
        pth = Path([T(*p0), T(*c1), T(*c2), T(*p3)],
                   [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
        ax.add_patch(patches.PathPatch(pth, fill=False, edgecolor=color,
                     lw=sw * s, alpha=a, capstyle="round", zorder=5))
    gust((20, 78), (44, 70), (62, 70), (82, 74), 8, 0.5)
    gust((20, 58), (48, 47), (68, 47), (86, 53), 9, 1.0)
    gust((20, 40), (42, 33), (58, 33), (76, 38), 8, 0.82)
    ax.add_patch(patches.Polygon([T(80, 55), T(112, 30), T(96, 57), T(90, 44)],
                 closed=True, facecolor=color, edgecolor=color,
                 linewidth=1.2 * s, joinstyle="round", zorder=6))


def _fig(W, H, transparent=False):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    if not transparent:
        ax.add_patch(patches.Rectangle((0, 0), W, H, facecolor="#ffffff", zorder=-1))
    return fig, ax


def _save(fig, out, transparent=False):
    tmp = out + ".tmp.png"
    fig.savefig(tmp, dpi=100, transparent=transparent)
    plt.close(fig)
    im = Image.open(tmp)
    (im if transparent else im.convert("RGB")).save(out)
    os.remove(tmp)
    print("  wrote", os.path.basename(out))


def _header(ax, W, H, title, hbar=150):
    """Gradient header bar with wind-mark + LEVANTER + section title; white body."""
    ax.imshow(np.tile(np.linspace(0, 1, 200), (10, 1)), extent=[0, W, 0, hbar],
              cmap=CMAP, aspect="auto", interpolation="bilinear", zorder=1)
    _windmark(ax, 40, hbar / 2 - 42 * (hbar / 130), (hbar / 130) * 0.9)
    ax.text(150, hbar * 0.42, "LEVANTER", color="#fff", fontsize=hbar * 0.20,
            fontweight="heavy", va="center")
    ax.text(150, hbar * 0.72, title.upper(), color="#e8f1ff", fontsize=hbar * 0.13,
            fontweight="semibold", va="center")


def title_card(W, H, out, date_txt):
    fig, ax = _fig(W, H)
    _gradient(ax, W, H)
    vertical = H > W
    cx = W / 2
    _windmark(ax, cx - 42 * (H / 260), H * (0.20 if vertical else 0.22),
              (H / 260) * (1.1 if not vertical else 1.4))
    ax.text(cx, H * (0.42 if vertical else 0.46), "LEVANTER", color="#fff",
            fontsize=H * (0.075 if vertical else 0.12), fontweight="heavy", ha="center", va="center")
    ax.text(cx, H * (0.50 if vertical else 0.58), "THE WEEKLY MARKET READ", color="#e8f1ff",
            fontsize=H * (0.028 if vertical else 0.040), fontweight="semibold", ha="center", va="center")
    ax.text(cx, H * (0.57 if vertical else 0.68), date_txt, color="#dbeafe",
            fontsize=H * (0.024 if vertical else 0.034), ha="center", va="center")
    ax.text(cx, H * 0.93, "Volatility yes.  Direction no.  And the receipts.", color="#eff6ff",
            fontsize=H * (0.020 if vertical else 0.028), style="italic", ha="center", va="center")
    _save(fig, out)


def cta_card(W, H, out):
    fig, ax = _fig(W, H)
    _gradient(ax, W, H)
    vertical = H > W
    cx = W / 2
    ax.text(cx, H * 0.30, "Keep the honest read coming", color="#fff",
            fontsize=H * (0.036 if vertical else 0.055), fontweight="heavy", ha="center", va="center")
    ax.text(cx, H * 0.46, "Free dashboard", color="#dbeafe",
            fontsize=H * (0.022 if vertical else 0.030), ha="center", va="center")
    ax.text(cx, H * 0.52, "levantermarkets.com", color="#fff",
            fontsize=H * (0.030 if vertical else 0.044), fontweight="bold", ha="center", va="center")
    ax.text(cx, H * 0.64, "The Signal, weekly", color="#dbeafe",
            fontsize=H * (0.022 if vertical else 0.030), ha="center", va="center")
    ax.text(cx, H * 0.70, "read.levantermarkets.com", color="#fff",
            fontsize=H * (0.030 if vertical else 0.044), fontweight="bold", ha="center", va="center")
    _save(fig, out)


def disclaimer_card(W, H, out):
    fig, ax = _fig(W, H)
    _gradient(ax, W, H)
    ax.text(W / 2, H * 0.46, "Educational market analysis,", color="#fff",
            fontsize=H * 0.045, fontweight="bold", ha="center", va="center")
    ax.text(W / 2, H * 0.56, "not financial advice.", color="#fff",
            fontsize=H * 0.045, fontweight="bold", ha="center", va="center")
    _windmark(ax, W / 2 - 30, H * 0.72, 0.6)
    _save(fig, out)


def lower_third(W, H, out):
    fig, ax = _fig(W, H, transparent=True)
    pill_w, pill_h, m = 470, 110, 60
    y0 = H - m - pill_h
    ax.imshow(np.tile(np.linspace(0, 1, 100), (8, 1)), extent=[m, m + pill_w, y0, y0 + pill_h],
              cmap=CMAP, aspect="auto", interpolation="bilinear", zorder=1)
    _windmark(ax, m + 22, y0 + pill_h / 2 - 34, 0.62)
    ax.text(m + 120, y0 + pill_h * 0.40, "LEVANTER", color="#fff", fontsize=34,
            fontweight="heavy", va="center")
    ax.text(m + 121, y0 + pill_h * 0.74, "MARKETS · SIGNALS · INSIGHT", color="#e8f1ff",
            fontsize=13, fontweight="semibold", va="center")
    _save(fig, out, transparent=True)


def insert_volatility(W, H, out, bt):
    fig, ax = _fig(W, H)
    _header(ax, W, H, "Volatility model: the forecast that works")
    rows = [(h, bt.get(h, {})) for h in ("7d", "30d", "90d") if bt.get(h)]
    y = 340
    for h, d in rows:
        ax.text(120, y, h, color=INK, fontsize=68, fontweight="heavy", va="center", ha="left")
        ax.text(620, y, f"{d.get('acc')}%", color=BRAND, fontsize=80, fontweight="heavy",
                va="center", ha="right")           # right-aligned column, never collides
        ax.text(700, y, f"+{d.get('edge')} vs coin flip", color=INK, fontsize=40, va="center", ha="left")
        ci = d.get("ci")
        if ci:
            ax.text(700, y + 50, f"95% CI {ci[0]}–{ci[1]}", color=MUT, fontsize=30, va="center", ha="left")
        y += 230
    ax.text(120, H - 70, "Five-year point-in-time backtest, non-overlapping. Volatility clusters, so it carries real skill.",
            color=MUT, fontsize=26, va="center")
    _save(fig, out)


def insert_map(W, H, out, turbulent, calm_n):
    import textwrap
    fig, ax = _fig(W, H)
    _header(ax, W, H, "This week's map: where the ranges are")
    ax.text(120, 290, "TURBULENT", color="#dc2626", fontsize=48, fontweight="heavy", va="center", ha="left")
    ax.text(120, 355, f"{len(turbulent)} commodities flagged high-vol for the week ahead",
            color=INK, fontsize=32, va="center", ha="left")
    lines = textwrap.wrap(", ".join(turbulent), width=52) or [""]
    yy = 445
    for ln in lines[:3]:
        ax.text(140, yy, ln, color=INK, fontsize=40, va="top", ha="left")
        yy += 66
    ax.text(120, 700, "CALM", color="#059669", fontsize=48, fontweight="heavy", va="center", ha="left")
    ax.text(120, 765, f"Crypto and foreign exchange  ·  {calm_n} markets reading quiet",
            color=INK, fontsize=32, va="center", ha="left")
    ax.text(120, H - 60, "Same board, very different weather. We flag the ranges, not the direction.",
            color=MUT, fontsize=28, va="center", ha="left")
    _save(fig, out)


def insert_scoreboard(W, H, out, byc):
    fig, ax = _fig(W, H)
    _header(ax, W, H, "Direction: the honest scoreboard")
    y = 320
    for c in byc:
        if c.get("acc") is None:
            continue
        ax.text(120, y, c["label"], color=INK, fontsize=48, fontweight="heavy", va="center", ha="left")
        ax.text(900, y, f"{c['acc']}%", color=BRAND, fontsize=68, fontweight="heavy",
                va="center", ha="right")           # right-aligned column, never collides
        ax.text(960, y, f"over {c['n']:,} calls", color=MUT, fontsize=34, va="center", ha="left")
        y += 165
    ax.text(120, y + 10, "A coin flip. We publish it anyway. Read the rows, not the blend.",
            color=INK, fontsize=34, fontweight="bold", va="center")
    ax.text(120, H - 60, "Backtested May–August 2026, point-in-time. Volatility is forecastable. Direction is not, so we do not sell it.",
            color=MUT, fontsize=24, va="center")
    _save(fig, out)


def bitcoin_callouts(out, price, fair, floor, ou):
    """Annotate the existing btc_metcalfe.png with two pointer callouts."""
    src = "reports/btc_metcalfe.png"
    if not os.path.exists(src):
        print("  (btc_metcalfe.png missing, skipping callouts)")
        return
    im = Image.open(src).convert("RGB")
    W, H = im.size
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    ax.imshow(np.asarray(im), extent=[0, W, H, 0], zorder=0)
    # Boxes sit in the open lower-right of the chart; arrows point up to the
    # right-end features (current-price dot high, floor line just below it).
    ax.annotate(f"Bitcoin ≈ ${price/1000:.0f}k\nabout {abs(ou):.0f}% below the valuation fit",
                xy=(W * 0.955, H * 0.12), xytext=(W * 0.60, H * 0.52),
                fontsize=26, fontweight="bold", color="#0f172a", ha="center",
                bbox=dict(boxstyle="round,pad=0.6", fc="#ffffff", ec=BRAND, lw=2.5),
                arrowprops=dict(arrowstyle="->", color=BRAND, lw=3,
                                connectionstyle="arc3,rad=-0.2"))
    ax.annotate(f"fit floor ≈ ${floor/1000:.0f}k",
                xy=(W * 0.955, H * 0.185), xytext=(W * 0.62, H * 0.70),
                fontsize=24, fontweight="bold", color="#065f46", ha="center",
                bbox=dict(boxstyle="round,pad=0.5", fc="#ecfdf5", ec="#10b981", lw=2),
                arrowprops=dict(arrowstyle="->", color="#10b981", lw=2.5,
                                connectionstyle="arc3,rad=-0.2"))
    tmp = out + ".tmp.png"; fig.savefig(tmp, dpi=100); plt.close(fig)
    Image.open(tmp).convert("RGB").save(out); os.remove(tmp)
    print("  wrote", os.path.basename(out))


def caption_strip(W, H, out, turbulent, calm_n):
    fig, ax = _fig(W, H, transparent=True)
    y0 = H - 150
    ax.add_patch(patches.FancyBboxPatch((60, y0), W - 120, 90,
                 boxstyle="round,pad=0.02,rounding_size=18", fc=INK, ec="none", alpha=0.9, zorder=1))
    ax.text(90, y0 + 45, f"Turbulent: {len(turbulent)} commodities", color="#fff",
            fontsize=34, fontweight="bold", va="center")
    ax.text(W - 90, y0 + 45, "Calm: crypto + FX", color="#93c5fd",
            fontsize=34, fontweight="bold", va="center", ha="right")
    _save(fig, out, transparent=True)


def main():
    argv = sys.argv[1:]
    date = argv[argv.index("--date") + 1] if "--date" in argv else dt.date.today().isoformat()
    date_h = dt.date.fromisoformat(date).strftime("Week of %-d %B %Y")
    pack = os.path.join("reports", "video", f"pack-{date}")
    os.makedirs(pack, exist_ok=True)

    vr = _read("vol_regime.json"); nv = _read("btc_metcalfe.json")
    try:
        dbt = json.load(open("direction_backtest.json"))
    except Exception:
        dbt = {}
    bt = vr.get("backtest", {})
    cls, assets = vr.get("classes", {}), vr.get("assets", {})
    turbulent = [s for s, c in cls.items()
                 if c == "commodity" and assets.get(s, {}).get("7d", {}).get("regime") == "HIGH"]
    turbulent = [t.title() if t.isupper() else t for t in turbulent]
    calm_n = sum(1 for s in assets if assets.get(s, {}).get("7d", {}).get("regime") == "LOW")

    P = lambda n: os.path.join(pack, n)
    print(f"Rendering video pack -> {pack}/")
    title_card(1920, 1080, P("01-title-16x9.png"), date_h)
    title_card(1080, 1920, P("01-title-9x16.png"), date_h)
    lower_third(1920, 1080, P("02-lower-third.png"))
    insert_volatility(1920, 1080, P("03-insert-volatility.png"), bt)
    insert_map(1920, 1080, P("04-insert-map.png"), turbulent, calm_n)
    bitcoin_callouts(P("05-insert-bitcoin-callouts.png"),
                     nv.get("price", 0), nv.get("fair_value", 0),
                     nv.get("floor", 0), nv.get("over_under_pct", 0))
    insert_scoreboard(1920, 1080, P("06-insert-scoreboard.png"), dbt.get("by_class", []))
    caption_strip(1920, 1080, P("07-caption-strip.png"), turbulent, calm_n)
    cta_card(1920, 1080, P("08-cta-16x9.png"))
    cta_card(1080, 1920, P("08-cta-9x16.png"))
    disclaimer_card(1920, 1080, P("09-disclaimer-16x9.png"))
    # the raw bitcoin chart, and the crypto maps, copied in for the editor
    for src in ("btc_metcalfe.png", "crypto_map_treemap.png", "crypto_map_correlation.png"):
        s = os.path.join("reports", src)
        if os.path.exists(s):
            Image.open(s).convert("RGB").save(P("chart-" + src))
    print("Done.")


if __name__ == "__main__":
    main()
