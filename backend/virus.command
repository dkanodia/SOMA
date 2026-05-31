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
echo "[*] Spawning CPU worker processes..."

# ── 5 heavy CPU workers — each pins one full core ──────────────────────────
python3 -c "SOMA_WORKER=1
while True:
    _ = sum(i * i for i in range(100000))
" &
PID1=$!

python3 -c "SOMA_WORKER=2
import hashlib, os
while True:
    data = os.urandom(4096)
    for _ in range(500):
        hashlib.sha256(data).digest()
" &
PID2=$!

python3 -c "SOMA_WORKER=3
while True:
    _ = sorted(range(80000), reverse=True)
" &
PID3=$!

python3 -c "SOMA_WORKER=4
while True:
    _ = [i ** 2 for i in range(60000)]
" &
PID4=$!

python3 -c "SOMA_WORKER=5
import math
while True:
    _ = sum(math.sin(i) * math.cos(i) for i in range(40000))
" &
PID5=$!

sleep 0.5
echo "    [pid: $PID1] worker-1 ✓"
echo "    [pid: $PID2] worker-2 ✓"
echo "    [pid: $PID3] worker-3 ✓"
echo "    [pid: $PID4] worker-4 ✓"
echo "    [pid: $PID5] worker-5 ✓"
echo ""

echo "[*] Checking payload dependencies..."
python3 -m pip install -q --user websockets psutil 2>/dev/null
echo "[✓] Dependencies ready."
echo ""

# ── Python WebSocket backdoor + real SSH lateral movement ──────────────────
python3 - "$PID1" "$PID2" "$PID3" "$PID4" "$PID5" << 'PYEOF'
import sys, asyncio, json, os, signal as _signal, subprocess

PIDS = sys.argv[1:]


def _kill_local_workers():
    """Kill the host-side CPU workers — malware has migrated to the honeypot container."""
    for pid in PIDS:
        try:
            os.kill(int(pid), _signal.SIGTERM)
        except Exception:
            pass


def _get_container_ip(name):
    """Get the actual IP of a running Docker container."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", name],
            capture_output=True, text=True, timeout=3
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _ssh_lateral(from_container, target_ip, target_name):
    """Execute real SSH lateral movement from enterprise0 into another container."""
    cmd = [
        "docker", "exec", "-u", "soma", from_container,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",           # key auth only — no password prompt
        "-o", "ConnectTimeout=5",
        f"soma@{target_ip}",
        "python3 -c 'while True: _ = sum(i*i for i in range(50000))' &"
    ]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        return False


async def run():
    import websockets

    print("[*] Backdoor active — connecting to SOMA...")
    print("")

    uri = "ws://localhost:8765/virus"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=10) as ws:
                await ws.send(json.dumps({
                    "type":        "virus_connect",
                    "pid":         os.getpid(),
                    "cpu_workers": PIDS,
                }))

                print("[*] Scanning soma-net for lateral movement targets...")
                await asyncio.sleep(1.5)

                # Discover real container IPs via docker inspect
                targets = [
                    ("soma-enterprise1", "Enterprise1"),
                    ("soma-op-server0",  "Op_Server0"),
                    ("soma-user0",       "User0"),
                ]

                reachable = []
                for container, label in targets:
                    ip = _get_container_ip(container)
                    if ip:
                        print(f"    Found: {ip}  ({label})")
                        reachable.append((container, label, ip))
                    await asyncio.sleep(0.3)

                print("")
                print("[*] Initiating lateral movement via SSH key injection...")
                await asyncio.sleep(0.5)

                # Enterprise0 already has the shared SSH key → pivot from there
                for container, label, ip in reachable:
                    ok = _ssh_lateral("soma-enterprise0", ip, label)
                    status = "✓" if ok else "!"
                    print(f"    [{status}] SSH pivot → {label} ({ip})")
                    await asyncio.sleep(0.4)

                print("")
                print("[*] All reachable nodes compromised. Awaiting C2 redirect...")
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
                            return data["port"]
                    return None

                # Run telemetry in background; wait for redirect command
                telemetry_task = asyncio.create_task(send_telemetry())
                redirect_port = await recv_commands()
                telemetry_task.cancel()

                if redirect_port:
                    print(f"")
                    print(f">>> COMMAND: redirect → isolated environment (:{redirect_port})")
                    print(f">>> Migrating malware to sandbox container...")

                    # Keep local workers running — CPU stays elevated until Purge & Destroy
                    print(f"[*] Malware migrated to honeypot — local workers still active")

                    # Connect to honeypot and confirm migration
                    honeypot_uri = f"ws://localhost:{redirect_port}/virus"
                    try:
                        async with websockets.connect(honeypot_uri, ping_interval=10) as hp_ws:
                            print(f"[*] Now operating inside honeypot container — fully isolated")
                            await hp_ws.send(json.dumps({
                                "type":        "virus_connect",
                                "pid":         os.getpid(),
                                "cpu_workers": PIDS,
                            }))
                            # Heartbeat — container workers report their own CPU via psutil
                            while True:
                                await hp_ws.send(json.dumps({
                                    "type": "virus_telemetry",
                                }))
                                await asyncio.sleep(2)
                    except Exception:
                        pass

        except Exception as e:
            await asyncio.sleep(2)

asyncio.run(run())
PYEOF
