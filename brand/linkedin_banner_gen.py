"""Levanter LinkedIn banners, both standard sizes, flat RGB, rendered at 2x.

  * company-page cover  : 1128 x 191
  * personal-profile bg : 1584 x 396

LinkedIn rejects/crops the wrong aspect ratio, which is why a single size
"doesn't work" when uploaded to the other slot. This makes both.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from PIL import Image

CMAP = LinearSegmentedColormap.from_list("lev", ["#0ea5e9", "#3b82f6", "#6366f1"])


def make(W, H, out, word_frac):
    # W, H are the OUTPUT pixel dimensions; rendered natively at dpi=100.
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    # gradient background
    X, Y = np.meshgrid(np.linspace(0, 1, 160), np.linspace(0, 1, 80))
    ax.imshow(X * 0.7 + Y * 0.3, extent=[0, W, H, 0], cmap=CMAP,
              aspect="auto", interpolation="bilinear", zorder=0)

    ms = H / 120.0                 # wind-mark scale
    fs = H * word_frac             # wordmark font size
    tag = "M A R K E T S   ·   S I G N A L S   ·   I N S I G H T"
    tag_fs = fs * 0.235
    word_w = fs * 0.60 * 8         # "LEVANTER" ~= 8 chars
    tag_w = tag_fs * 0.46 * len(tag)   # spaced tagline is the wider element
    content_w = max(word_w, tag_w)
    mark_w = 80 * ms
    gap = fs * 0.30
    total = mark_w + gap + content_w
    gx = (W - total) / 2           # centre the logo + wordmark group
    mox, moy = gx - 26 * ms, H / 2 - 56 * ms

    def T(x, y):
        return (mox + x * ms, moy + y * ms)

    def gust(p0, c1, c2, p3, sw, a):
        pth = Path([T(*p0), T(*c1), T(*c2), T(*p3)],
                   [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
        ax.add_patch(patches.PathPatch(pth, fill=False, edgecolor="white",
                     lw=sw * ms * 0.9, alpha=a, capstyle="round", zorder=2))

    gust((26, 80), (50, 70), (68, 70), (90, 76), 8.5, 0.5)
    gust((26, 60), (54, 47), (76, 47), (100, 55), 9, 1.0)
    gust((26, 40), (46, 32), (62, 32), (80, 37), 8.5, 0.82)
    ax.add_patch(patches.PathPatch(
        Path([T(90, 48), T(105, 42), T(101, 57)],
             [Path.MOVETO, Path.LINETO, Path.LINETO]),
        fill=False, edgecolor="white", lw=9 * ms * 0.9,
        capstyle="round", joinstyle="round", zorder=2))

    tx = gx + mark_w + gap
    base = H / 2 + fs * 0.34
    ax.text(tx, base, "LEVANTER", color="white", fontsize=fs,
            fontweight="heavy", va="baseline", ha="left")
    ax.text(tx + fs * 0.05, base + fs * 0.42, tag,
            color="#e8f1ff", fontsize=tag_fs, fontweight="semibold",
            va="baseline", ha="left")

    os.makedirs("reports/linkedin", exist_ok=True)
    tmp = out + ".tmp.png"
    fig.savefig(tmp, dpi=100)
    plt.close(fig)
    Image.open(tmp).convert("RGB").save(out)      # flatten to RGB (no alpha)
    os.remove(tmp)
    print(f"saved {out} ({W}x{H})")


if __name__ == "__main__":
    # Company page cover: LinkedIn recommends uploading at 4200x700 (renders to 1128x191).
    make(4200, 700, "reports/linkedin/levanter-linkedin-banner.png", 0.40)
    # Personal profile background: 1584x396, rendered at 2x for sharpness.
    make(3168, 792, "reports/linkedin/levanter-linkedin-profile-banner.png", 0.26)
