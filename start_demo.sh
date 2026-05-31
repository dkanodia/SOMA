#!/bin/bash
# SOMA Demo Launcher
# Starts the local backend, tunnels it via ngrok, then opens the
# Vercel frontend pointed at YOUR machine's live psutil data.
#
# First-time setup:
#   1. Sign up at https://ngrok.com (free)
#   2. Run: ngrok authtoken <your-token>
#   Then just run: ./start_demo.sh

set -e

BACKEND_PORT=8765
VERCEL_URL="https://frontend-nu-six-43.vercel.app"
BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
ENV_FILE="$BACKEND_DIR/.env"

# ── 1. Kill anything already on the port ────────────────────────────────────
lsof -ti tcp:$BACKEND_PORT | xargs kill -9 2>/dev/null || true

# ── 2. Start the backend ─────────────────────────────────────────────────────
echo "▶ Starting SOMA backend on :$BACKEND_PORT ..."
if [ -f "$ENV_FILE" ]; then
  # Load .env for Gmail credentials
  export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

cd "$BACKEND_DIR"
python3 ws_server.py &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for it to be ready
for i in $(seq 1 10); do
  if curl -sf --max-time 1 http://localhost:$BACKEND_PORT/ >/dev/null 2>&1; then
    echo "  Backend ready ✅"
    break
  fi
  sleep 0.5
done

# ── 3. Start ngrok tunnel ────────────────────────────────────────────────────
echo "▶ Starting ngrok tunnel ..."
pkill -f "ngrok http $BACKEND_PORT" 2>/dev/null || true
ngrok http $BACKEND_PORT --log=stdout --log-level=warn > /tmp/ngrok_soma.log 2>&1 &
NGROK_PID=$!

# Poll ngrok's local API until the tunnel URL appears
NGROK_URL=""
for i in $(seq 1 20); do
  sleep 0.5
  NGROK_URL=$(curl -sf http://localhost:4040/api/tunnels 2>/dev/null \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
tunnels = data.get('tunnels', [])
for t in tunnels:
    url = t.get('public_url','')
    if url.startswith('https'):
        print(url.replace('https://','wss://'))
        break
" 2>/dev/null)
  if [ -n "$NGROK_URL" ]; then
    break
  fi
done

if [ -z "$NGROK_URL" ]; then
  echo "❌ ngrok failed to start. Check /tmp/ngrok_soma.log"
  echo "   Make sure you ran: ngrok authtoken <your-token>"
  kill $BACKEND_PID 2>/dev/null
  exit 1
fi

echo "  Tunnel: $NGROK_URL ✅"

# ── 4. Build the dashboard URL ───────────────────────────────────────────────
DASHBOARD_URL="${VERCEL_URL}?ws=${NGROK_URL}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SOMA Dashboard (live data from YOUR machine):"
echo "  $DASHBOARD_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Open browser
open "$DASHBOARD_URL"

# ── 5. Wait / cleanup ────────────────────────────────────────────────────────
echo "Press Ctrl+C to stop backend + tunnel."
trap "kill $BACKEND_PID $NGROK_PID 2>/dev/null; echo 'Stopped.'" EXIT INT TERM
wait $BACKEND_PID
