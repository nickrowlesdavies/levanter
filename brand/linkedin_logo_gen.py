"""Levanter Signal logo, at the sizes LinkedIn actually uses.

  * company/showcase page logo : 300 x 300  (LinkedIn's stated size, 268 minimum)
  * profile / high-DPI spare   : 400 x 400

Two finishes of each, because the master has transparent corners:

  * "-rounded" keeps them, which is right on LinkedIn's white surfaces
  * "-square" fills them with the same gradient, so the mark does not show
    notches anywhere the logo lands on a dark or coloured background

Gradient stops are taken from levanter-signal-logo-square.svg so the filled
corners meet the mark's own edge seamlessly. Run from brand/:

    python linkedin_logo_gen.py
"""
import os

import numpy as np
from PIL import Image

SRC = os.path.join("out", "levanter-signal-logo-square.png")
OUT = "out"
SIZES = (300, 400)

# levanter-signal-logo-square.svg: linearGradient x1,y1 = 0,0 -> x2,y2 = 1,1
STOPS = ((0.00, (0x0E, 0xA5, 0xE9)),
         (0.55, (0x3B, 0x82, 0xF6)),
         (1.00, (0x63, 0x66, 0xF1)))


def _gradient(size):
    """The SVG's diagonal gradient, rebuilt at an arbitrary size."""
    y, x = np.mgrid[0:size, 0:size]
    t = ((x / (size - 1)) + (y / (size - 1))) / 2.0
    offs = np.array([s[0] for s in STOPS])
    cols = np.array([s[1] for s in STOPS], dtype=float)
    out = np.zeros((size, size, 3))
    for ch in range(3):
        out[..., ch] = np.interp(t, offs, cols[:, ch])
    return Image.fromarray(out.round().astype("uint8"), "RGB")


def main():
    master = Image.open(SRC).convert("RGBA")
    made = []
    for size in SIZES:
        mark = master.resize((size, size), Image.LANCZOS)

        rounded = os.path.join(OUT, f"levanter-signal-linkedin-{size}-rounded.png")
        mark.save(rounded)
        made.append(rounded)

        # Flatten onto the same gradient: the corners fill in, everything else
        # is covered by the mark, so no seam.
        square = _gradient(size)
        square.paste(mark, (0, 0), mark)
        square_path = os.path.join(OUT, f"levanter-signal-linkedin-{size}-square.png")
        square.save(square_path)
        made.append(square_path)

    for p in made:
        im = Image.open(p)
        print(f"  {p}  {im.size[0]}x{im.size[1]}  {im.mode}  {os.path.getsize(p):,} bytes")


if __name__ == "__main__":
    main()
