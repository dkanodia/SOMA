"""
backend/honeypot_server.py
==========================
Runs inside the soma_honeypot Docker container on port 8766.

Accepts virus WebSocket connections on :8766/virus.
All metrics reported to SOMA are derived directly from what the virus sends —
no synthetic counters.

Forwarded to SOMA backend at ws://host.docker.internal:8765/honeypot:
  type:       "honeypot_telemetry"
  cpu:        float    virus-reported CPU (real psutil from the host)
  processes:  int      virus-reported process count (real psutil)
  connections: int     total virus_telemetry messages received (real activity count)
"""

import asyncio
import json
import os
import websockets

SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = int(os.environ.get("SOMA_PORT", 8765))

_telemetry_queue: asyncio.Queue = None


async def _virus_handler(ws):
    """Accept virus connection and forward real telemetry to SOMA."""
    print("[honeypot] Malware connected on :8766")
    connections = 0

    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        if msg.get("type") == "virus_connect":
            print(f"[honeypot] virus_connect pid={msg.get('pid')} workers={msg.get('cpu_workers')}")

        elif msg.get("type") == "virus_telemetry":
            connections += 1
            payload = {
                "type":        "honeypot_telemetry",
                "cpu":         msg.get("cpu", 0),
                "processes":   msg.get("processes", 0),
                "connections": connections,
            }
            print(f"[honeypot] telemetry cpu={payload['cpu']:.2f} procs={payload['processes']} conn={connections}")
            await _telemetry_queue.put(payload)

        await ws.send(json.dumps({"type": "ack", "status": "ok"}))

    print("[honeypot] Malware disconnected")


async def _soma_reporter():
    """Connect to SOMA backend /honeypot and forward queued telemetry."""
    uri = f"ws://{SOMA_HOST}:{SOMA_PORT}/honeypot"
    delay = 3
    while True:
        try:
            async with websockets.connect(uri) as soma_ws:
                print(f"[honeypot] Reporting to SOMA at {uri}")
                delay = 3
                while True:
                    payload = await _telemetry_queue.get()
                    await soma_ws.send(json.dumps(payload))
        except Exception as e:
            print(f"[honeypot] SOMA connection error: {e} — retrying in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def main():
    global _telemetry_queue
    _telemetry_queue = asyncio.Queue()

    print(f"[honeypot] Listening on 0.0.0.0:8766")
    print(f"[honeypot] Will report to ws://{SOMA_HOST}:{SOMA_PORT}/honeypot")

    asyncio.ensure_future(_soma_reporter())

    async with websockets.serve(_virus_handler, "0.0.0.0", 8766):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
