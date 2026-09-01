#!/bin/bash
# Serve the auto-refreshing dashboard to your phone over your home Wi-Fi.
#   ./serve.sh          start (server + auto-regeneration, both in background)
#   ./serve.sh stop     stop everything
#
# Your Mac and phone must be on the SAME Wi-Fi, and the Mac must stay awake.
# While running, this regenerates the dashboard every 30 min AND the page
# itself reloads every 5 min, so your phone always shows current numbers.
# Local network only - nothing leaves your network.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/reports" || exit 1
PORT=8137

if [ "$1" = "stop" ]; then
    for f in .server.pid .regen.pid; do
        [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null
        rm -f "$f"
    done
    echo "Dashboard server + auto-refresh stopped."
    exit 0
fi

# Clean restart.
for f in .server.pid .regen.pid; do
    [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null
done

# 1) Static file server, reachable from the phone.
nohup python3 -m http.server "$PORT" --bind 0.0.0.0 >/dev/null 2>&1 &
echo $! > .server.pid

# 2) Background loop: rebuild the dashboard every 30 min so data stays fresh.
nohup bash -c "while true; do \"$DIR/run.sh\" build_dashboard.py >/dev/null 2>&1; sleep 1800; done" >/dev/null 2>&1 &
echo $! > .regen.pid

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "YOUR-MAC-IP")
echo "Dashboard is live and auto-refreshing."
echo "  On this Mac : http://localhost:$PORT/dashboard.html"
echo "  On your PHONE (same Wi-Fi): http://$IP:$PORT/dashboard.html"
echo ""
echo "Tip: bookmark that phone URL. Keep the Mac awake to stay reachable."
echo "Stop with: ./serve.sh stop"
