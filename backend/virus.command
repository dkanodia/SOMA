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
echo "[*] Spawning CPU worker processes (stealth mining mode)..."

# ── 5 heavy CPU workers — each pins one full core (~65-70% total on 8-core) ──
python3 -c "
while True:
    _ = sum(i * i for i in range(100000))
" &
PID1=$!

python3 -c "
import hashlib, os
while True:
    data = os.urandom(4096)
    for _ in range(500):
        hashlib.sha256(data).digest()
" &
PID2=$!

python3 -c "
while True:
    _ = sorted(range(80000), reverse=True)
" &
PID3=$!

python3 -c "
while True:
    _ = [i ** 2 for i in range(60000)]
" &
PID4=$!

python3 -c "
import math
while True:
    _ = sum(math.sin(i) * math.cos(i) for i in range(40000))
" &
PID5=$!

sleep 0.5
echo "    [pid: $PID1] CryptoMiner-Alpha  ✓"
echo "    [pid: $PID2] CryptoMiner-Beta   ✓"
echo "    [pid: $PID3] CryptoMiner-Gamma  ✓"
echo "    [pid: $PID4] CryptoMiner-Delta  ✓"
echo "    [pid: $PID5] CryptoMiner-Epsilon ✓"
echo ""
sleep 0.3
echo "[*] CPU stress initiated — $(sysctl -n hw.ncpu 2>/dev/null || echo '?') cores targeted..."
sleep 0.3
echo "[*] Scanning exfiltration targets..."
echo "    /Users/$(whoami)/Documents/   → queued ($(ls ~/Documents/ 2>/dev/null | wc -l | tr -d ' ') files)"
echo "    /Users/$(whoami)/Desktop/     → queued"
echo ""
sleep 0.5

echo "[*] Checking payload dependencies..."
python3 -m pip install -q --user websockets psutil 2>/dev/null
echo "[✓] Dependencies ready."
echo ""

# ── Python WebSocket backdoor ──────────────────────────────────────────────
python3 - "$PID1" "$PID2" "$PID3" "$PID4" "$PID5" << 'PYEOF'
import sys, asyncio, json, os, signal, subprocess

PIDS = sys.argv[1:]

async def run():
    import websockets
    uri = "ws://localhost:8765/virus"

    print("[*] Backdoor active — awaiting C2 commands...")
    print("")

    while True:
        try:
            async with websockets.connect(uri, ping_interval=10) as ws:
                await ws.send(json.dumps({
                    "type":        "virus_connect",
                    "pid":         os.getpid(),
                    "cpu_workers": PIDS,
                }))

                print("[*] Scanning LAN for lateral movement targets...")
                await asyncio.sleep(1.5)

                # Phase 2 — lateral movement via docker exec (real CPU injection into containers)
                targets = [
                    ("soma-enterprise0", "Enterprise0",  "10.0.0.5"),
                    ("soma-enterprise1", "Enterprise1",  "10.0.0.6"),
                    ("soma-op-server0",  "Op_Server0",   "10.0.0.8"),
                ]
                for container, label, ip in targets:
                    print(f"    Found: {ip}  ({label})")
                    await asyncio.sleep(0.3)

                print("")
                print("[*] Initiating lateral movement...")
                await asyncio.sleep(0.5)

                for container, label, ip in targets:
                    try:
                        subprocess.Popen(
                            ["docker", "exec", "-d", container,
                             "python3", "-c",
                             "while True: _ = sum(i*i for i in range(50000))"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        print(f"    [✓] Payload deployed → {label} ({ip})")
                    except Exception as e:
                        print(f"    [!] {label}: {e}")
                    await asyncio.sleep(0.4)

                print("")
                print("[*] All systems compromised. Awaiting C2 redirect...")
                print("")

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
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "redirect":
                            new_port = data["port"]
                            print(f"")
                            print(f">>> COMMAND: redirect → isolated environment (:{new_port})")
                            print(f">>> Switching C2 channel...")
                            print(f"[*] Operating in decoy environment — SOMA cannot see us here")
                            return new_port
                    return None

                _, result = await asyncio.gather(
                    send_telemetry(),
                    recv_commands(),
                )

        except Exception as e:
            await asyncio.sleep(2)

asyncio.run(run())
PYEOF
