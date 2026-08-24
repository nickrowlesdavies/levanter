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
  # Optional per-script cap: "run --timeout N script.py". Default 240s.
  # A hung/geo-blocked feed must never stall the build; slow-but-healthy feeds
  # (CoinGecko cold cache) get a longer budget so the tab does not vanish.
  local t=240
  if [ "$1" = "--timeout" ]; then t="$2"; shift 2; fi
  echo "::group::$1"
  if timeout "$t" python "$@"; then :; else echo "WARN: '$*' failed or timed out after ${t}s - continuing without it"; fi
  echo "::endgroup::"
}

mkdir -p reports public

run --timeout 150 crypto_map.py --force   # coins/stablecoins via CoinGecko bulk endpoint (2 calls, ~10s,
                                          # reliable on CI). --force refetches fresh each build; the
                                          # committed seed (reports/crypto_map.json) is the fallback only
                                          # if the bulk call fails, so the tab never blanks.
run fx_map.py                # 16 FX majors/crosses (yfinance)
run commodities_map.py       # 12 metals/energy/ags (yfinance)
run cycle_gauge.py --live    # power-law + halving cycle gauge (+ proj PNGs)
run vol_regime.py --live     # volatility-regime forecast
run btc_metcalfe.py          # BTC network-value gauge (adoption power-law + Metcalfe diagnostic)
run orderflow.py             # Binance taker-buy / funding (may be geo-blocked on US runners)
run predict.py               # educational directional predictions
run signal_note.py           # weekly premium Signal note (prepares Mondays 06:00 GST; idempotent per week)

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

# Static discovery files (robots.txt, llms.txt, .well-known/security.txt) into the
# site root. "static/." copies hidden files/dirs (like .well-known) too.
if [ -d static ]; then cp -R static/. public/; fi

# Brand logo referenced by JSON-LD, served at /assets/levanter-logo-square.png
mkdir -p public/assets
cp -f brand/levanter-logo-square.png public/assets/levanter-logo-square.png 2>/dev/null || true

# Per-review indexable pages under /reviews/ + the generated sitemap.xml
# (replaces any static sitemap). Reads the committed review_archive.json.
python build_reviews.py public

# Keep GitHub Pages from running the output through Jekyll.
touch public/.nojekyll

# Optional custom domain: if a CNAME file exists at repo root, publish it.
[ -f CNAME ] && cp -f CNAME public/CNAME

echo "Built public/index.html ($(wc -c < public/index.html) bytes)"
