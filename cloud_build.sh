#!/usr/bin/env bash
# Levanter cloud build: regenerate market data, then build the market-only
# tabbed site into ./public for GitHub Pages.
#
# Every data step is BEST-EFFORT: a single feed failing (e.g. Binance being
# geo-blocked on a US CI runner, or a rate-limit) must never abort the whole
# build - the page just renders without that one panel. Only the final
# build_dashboard step is required.
set -u

run() {
  echo "::group::$1"
  # Hard 4-minute cap per script: a hung/geo-blocked feed must never stall the build.
  if timeout 240 python "$@"; then :; else echo "WARN: '$*' failed or timed out - continuing without it"; fi
  echo "::endgroup::"
}

mkdir -p reports public

run crypto_map.py            # coins, stablecoins, treemap, commodities (CoinGecko + yfinance)
run fx_map.py                # 16 FX majors/crosses (yfinance)
run commodities_map.py       # 12 metals/energy/ags (yfinance)
run cycle_gauge.py --live    # power-law + halving cycle gauge (+ proj PNGs)
run vol_regime.py --live     # volatility-regime forecast
run orderflow.py             # Binance taker-buy / funding (may be geo-blocked on US runners)
run predict.py               # educational directional predictions

# Marketing landing page at the root; the live dashboard app under /app.
mkdir -p public/app
python build_dashboard.py --market-only --out public/app/index.html
cp -f landing.html public/index.html

# Ship the Substack-ready writeups alongside the site so they can be pulled
# from anywhere (build_dashboard.py wrote them to reports/substack).
mkdir -p public/substack public/substack/docx
cp -f reports/substack/*.md public/substack/ 2>/dev/null || true
cp -f reports/substack/docx/*.docx public/substack/docx/ 2>/dev/null || true

# Social share image (Open Graph) served at /og.png
cp -f brand/og.png public/og.png 2>/dev/null || true

# Keep GitHub Pages from running the output through Jekyll.
touch public/.nojekyll

# Optional custom domain: if a CNAME file exists at repo root, publish it.
[ -f CNAME ] && cp -f CNAME public/CNAME

echo "Built public/index.html ($(wc -c < public/index.html) bytes)"
