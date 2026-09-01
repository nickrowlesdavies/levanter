#!/bin/bash
# One-command review of all four paper strategies.
# Runs each signal (safe/idempotent - it won't double-count a bar/week/month),
# so it also catches up any cycles cron missed while the Mac was asleep.
#   ./dashboard.sh
cd "$(dirname "$0")" || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate

filter() { grep -v "NotOpenSSLWarning\|warnings.warn\|Matplotlib\|font cache"; }

echo ""
echo "################  FX  (4h mean-reversion)  ################"
python paper_trade.py --once 2>&1 | filter | tail -n +2

echo ""
echo "################  CARRY BASKET  (monthly)  ################"
python carry_signal.py 2>&1 | filter

echo ""
echo "################  CRYPTO MOMENTUM  (weekly)  ##############"
python crypto_signal.py 2>&1 | filter

echo ""
echo "################  COMBINED PORTFOLIO  (weekly)  ##########"
python combined_tracker.py 2>&1 | filter

echo ""
echo "################  VOL-TARGETED BASKET  (weekly)  #########"
python vol_basket_tracker.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  CRYPTO MARKET MAP  #####################"
python crypto_map.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  FX MARKET MAP  #########################"
python fx_map.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  COMMODITIES MARKET MAP  ################"
python commodities_map.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  CYCLE GAUGE  ###########################"
python cycle_gauge.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  VOLATILITY REGIME  #####################"
python vol_regime.py --live 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  ORDER FLOW  ############################"
python orderflow.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  PREDICTION MODEL  ######################"
python predict.py 2>&1 | filter | grep -v "delisted\|Failed download\|^\$"

echo ""
echo "################  VISUAL DASHBOARD  ######################"
python build_dashboard.py 2>&1 | filter
open reports/dashboard.html 2>/dev/null && echo "Opened reports/dashboard.html in your browser."
echo ""
echo "(Tip: full history of scheduled runs is in reports/cron.log)"
