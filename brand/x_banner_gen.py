"""Levanter Signal X/Twitter header, 1500 x 500, flat RGB, rendered at 2x.

X crops the header per device and overlaps the avatar at bottom-left, so the
logo group is centred and kept clear of the corners. Text widths are measured
(not estimated) so the group centres exactly.
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

CMAP = LinearSegmentedColormap.from_list("lev", ["#38bdf8", "#3b82f6", "#4f6ef2"])


def make(W, H, out):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    X, Y = np.meshgrid(np.linspace(0, 1, 160), np.linspace(0, 1, 80))
    ax.imshow(X * 0.7 + Y * 0.3, extent=[0, W, H, 0], cmap=CMAP,
              aspect="auto", interpolation="bilinear", zorder=0)
    rnd = fig.canvas.get_renderer()

    def measure(s, **kw):
        t = ax.text(0, 0, s, **kw)
        w = t.get_window_extent(renderer=rnd).width
        t.remove()
        return w

    ms = H / 120.0 * 0.74           # wind-mark scale
    fs = H * 0.185                  # "LEVANTER"
    sig_fs = fs * 0.50             # "SIGNAL" (tracked)
    tag_fs = fs * 0.205
    tag = "V O L A T I L I T Y   Y E S   ·   D I R E C T I O N   N O"

    word_w = measure("LEVANTER", fontsize=fs, fontweight="heavy")
    sig_w = measure("S I G N A L", fontsize=sig_fs, fontweight="bold")
    tag_w = measure(tag, fontsize=tag_fs, fontweight="semibold")
    mark_w = 118 * ms
    gap = fs * 0.34
    total = mark_w + gap + word_w
    gx = (W - total) / 2
    mox, moy = gx, H / 2 - 57 * ms

    def T(x, y):
        return (mox + x * ms, moy + y * ms)

    def gust(p0, c1, c2, p3, sw, a):
        pth = Path([T(*p0), T(*c1), T(*c2), T(*p3)],
                   [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4])
        ax.add_patch(patches.PathPatch(pth, fill=False, edgecolor="white",
                     lw=sw * ms * 0.9, alpha=a, capstyle="round", zorder=2))

    gust((20, 78), (44, 70), (62, 70), (82, 74), 8, 0.5)
    gust((20, 58), (48, 47), (68, 47), (86, 53), 9, 1.0)
    gust((20, 40), (42, 33), (58, 33), (76, 38), 8, 0.82)
    ax.add_patch(patches.Polygon([T(80, 55), T(112, 30), T(96, 57), T(90, 44)],
                 closed=True, facecolor="white", edgecolor="white",
                 linewidth=1.5 * ms, joinstyle="round", zorder=3))

    tx = gx + mark_w + gap
    c = H / 2
    ax.text(tx, c - fs * 0.06, "LEVANTER", color="white", fontsize=fs,
            fontweight="heavy", va="baseline", ha="left")
    # SIGNAL centred under LEVANTER
    ax.text(tx + (word_w - sig_w) / 2, c + sig_fs * 1.02, "S I G N A L",
            color="#dbe8ff", fontsize=sig_fs, fontweight="bold",
            va="baseline", ha="left")
    # tagline centred under the wordmark block, clear of the mark on the left
    ax.text(tx + word_w / 2, c + sig_fs * 1.02 + tag_fs * 2.0, tag,
            color="#e8f1ff", fontsize=tag_fs, fontweight="semibold",
            va="baseline", ha="center")

    os.makedirs("brand/out", exist_ok=True)
    tmp = out + ".tmp.png"
    fig.savefig(tmp, dpi=100)
    plt.close(fig)
    Image.open(tmp).convert("RGB").save(out)
    os.remove(tmp)
    print(f"saved {out} ({W}x{H})")


if __name__ == "__main__":
    make(3000, 1000, "brand/out/levanter-signal-x-banner.png")
