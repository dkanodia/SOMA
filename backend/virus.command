#!/bin/bash
# SOMA Demo — virus.command
# Double-click in macOS Finder → opens in Terminal

clear
echo "╔══════════════════════════════════════════════════════╗"
echo "║        [SOMA_PAYLOAD v2.1] Attack Sequence           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
sleep 0.3
echo "[*] Initializing payload..."
sleep 0.5
echo "[*] Establishing C2 connection to 185.234.219.43:4444..."
sleep 0.8
echo "[✓] Connection established."
echo ""
sleep 0.3
echo "[*] Fingerprinting system..."
sleep 0.4
echo "    OS:   macOS Darwin $(sw_vers -productVersion 2>/dev/null || echo 'Unknown')"
echo "    CPU:  $(sysctl -n hw.ncpu 2>/dev/null || echo '?') cores"
echo "    RAM:  $(( $(sysctl -n hw.memsize 2>/dev/null || echo 8589934592) / 1073741824 ))GB"
echo "    User: $(whoami)"
echo ""
sleep 0.3
echo "[*] Spawning stealth worker processes..."

# --- 3 real CPU workers (light load: ~2-4% each) ---
python3 -c "
import time, math
while True:
    _ = sum(math.sqrt(i) for i in range(30000))
    time.sleep(0.05)
" &
PID1=$!

python3 -c "
import time
while True:
    _ = [i**2 for i in range(20000)]
    time.sleep(0.05)
" &
PID2=$!

python3 -c "
import time
while True:
    _ = sorted(range(15000), reverse=True)
    time.sleep(0.05)
" &
PID3=$!

sleep 0.3
echo "    [pid: $PID1] worker-1 ✓"
echo "    [pid: $PID2] worker-2 ✓"
echo "    [pid: $PID3] worker-3 ✓"
echo ""
sleep 0.3
echo "[*] CPU stress initiated (stealth mode)..."
sleep 0.3
echo "[*] Scanning exfiltration targets..."
echo "    /Users/$(whoami)/Documents/   → queued"
echo "    /Users/$(whoami)/Desktop/     → queued"
echo ""
sleep 0.5
echo "[*] Scanning LAN for lateral movement targets..."
sleep 0.5
echo "    Found: 10.0.0.1   (gateway)"
echo "    Found: 10.0.0.5   (Enterprise0)"
echo "    Found: 10.0.0.8   (Op_Server0)"
echo ""
echo "[*] Backdoor active — awaiting C2 commands..."
echo ""

# --- Python WebSocket backdoor (inline) ---
python3 - "$PID1" "$PID2" "$PID3" << 'PYEOF'
import sys, asyncio, json, os, signal

PIDS = sys.argv[1:]

async def run():
    import websockets
    uri = "ws://localhost:8765/virus"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "type":        "virus_connect",
                    "pid":         os.getpid(),
                    "cpu_workers": PIDS,
                }))

                async def send_telemetry():
                    import psutil
                    while True:
                        await ws.send(json.dumps({
                            "type":      "virus_telemetry",
                            "cpu":       psutil.cpu_percent(interval=None) / 100,
                            "processes": len(psutil.pids()),
                        }))
                        await asyncio.sleep(2)

                async def recv_commands():
                    nonlocal uri
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "redirect":
                            new_port = data["port"]
                            print(f"\n>>> COMMAND: redirect → decoy environment (port {new_port})")
                            print(">>> Switching connections...")
                            print("[*] Now operating in isolated environment (undetected)")
                            uri = f"ws://localhost:{new_port}/virus"
                            return  # exit inner loop to reconnect on new port

                await asyncio.gather(send_telemetry(), recv_commands())
        except Exception as e:
            await asyncio.sleep(2)

asyncio.run(run())
PYEOF
