"""
backend/honeypot_server.py
==========================
Runs inside the soma_honeypot Docker container on port 8766.

When the virus connects (redirected from SOMA's :8765/virus):
  1. Spawn real CPU worker processes INSIDE this container
  2. Measure real container CPU/processes with psutil
  3. Report to SOMA backend at ws://host.docker.internal:8765/honeypot

The malware genuinely runs inside the isolated Docker sandbox.
Killing the container (docker stop/rm on purge) destroys all workers.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys

import psutil
import websockets

SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = int(os.environ.get("SOMA_PORT", 8765))

_telemetry_queue: asyncio.Queue = None
_worker_procs: list = []

# ---------------------------------------------------------------------------
# CPU workers — same patterns as virus.command so Activity Monitor matches
# ---------------------------------------------------------------------------

_WORKER_SCRIPTS = [
    "SOMA_WORKER=1\nwhile True: _ = sum(i*i for i in range(100000))",
    (
        "SOMA_WORKER=2\nimport hashlib,os\n"
        "while True:\n"
        " data=os.urandom(4096)\n"
        " [hashlib.sha256(data).digest() for _ in range(500)]"
    ),
    "SOMA_WORKER=3\nwhile True: _ = sorted(range(80000),reverse=True)",
    "SOMA_WORKER=4\nwhile True: _ = [i**2 for i in range(60000)]",
    "SOMA_WORKER=5\nimport math\nwhile True: _ = sum(math.sin(i)*math.cos(i) for i in range(40000))",
]


def _spawn_workers():
    global _worker_procs
    if _worker_procs:
        return
    for script in _WORKER_SCRIPTS:
        p = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _worker_procs.append(p)
        print(f"[honeypot] Spawned container worker PID {p.pid}", flush=True)


# ---------------------------------------------------------------------------
# WebSocket handler — virus connects here after SOMA redirect
# ---------------------------------------------------------------------------

async def _virus_handler(ws):
    print("[honeypot] Malware connected — spawning container CPU workers", flush=True)
    _spawn_workers()

    connections = 0
    psutil.cpu_percent(interval=None)  # seed so first reading is meaningful

    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        if msg.get("type") == "virus_connect":
            print(f"[honeypot] virus_connect pid={msg.get('pid')}", flush=True)

        elif msg.get("type") == "virus_telemetry":
            connections += 1
            # Real container CPU and process count — not the host values
            cpu   = psutil.cpu_percent(interval=None) / 100.0
            procs = len(psutil.pids())
            payload = {
                "type":        "honeypot_telemetry",
                "cpu":         round(cpu, 3),
                "processes":   procs,
                "connections": connections,
            }
            print(
                f"[honeypot] container cpu={cpu:.2f} procs={procs} conn={connections}",
                flush=True,
            )
            await _telemetry_queue.put(payload)

        await ws.send(json.dumps({"type": "ack", "status": "ok"}))

    print("[honeypot] Malware disconnected — workers keep running until container purge", flush=True)


# ---------------------------------------------------------------------------
# SOMA reporter — forward queued telemetry upstream
# ---------------------------------------------------------------------------

async def _soma_reporter():
    uri = f"ws://{SOMA_HOST}:{SOMA_PORT}/honeypot"
    delay = 3
    while True:
        try:
            async with websockets.connect(uri) as soma_ws:
                print(f"[honeypot] Reporting to SOMA at {uri}", flush=True)
                delay = 3
                while True:
                    payload = await _telemetry_queue.get()
                    await soma_ws.send(json.dumps(payload))
        except Exception as e:
            print(f"[honeypot] SOMA connection error: {e} — retrying in {delay}s", flush=True)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    global _telemetry_queue
    _telemetry_queue = asyncio.Queue()

    print(f"[honeypot] Listening on 0.0.0.0:8766", flush=True)
    print(f"[honeypot] Will report to ws://{SOMA_HOST}:{SOMA_PORT}/honeypot", flush=True)

    asyncio.ensure_future(_soma_reporter())

    async with websockets.serve(_virus_handler, "0.0.0.0", 8766):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
