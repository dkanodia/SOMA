"""
backend/honeypot_server.py
==========================
Runs inside the soma_honeypot Docker container on port 8766.

Accepts virus WebSocket connections on :8766/virus,
captures telemetry, and forwards it to the SOMA backend
by connecting to ws://host.docker.internal:8765/honeypot.
"""

import asyncio
import json
import os
import websockets

SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = int(os.environ.get("SOMA_PORT", 8765))

# Queue for forwarding telemetry to SOMA backend
_telemetry_queue: asyncio.Queue = None


async def _virus_handler(ws):
    """Accept incoming virus connection, count and forward telemetry."""
    print("[honeypot] Malware connected on :8766")
    exfil_attempts = 0
    lan_scans = 0

    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        if msg.get("type") == "virus_telemetry":
            exfil_attempts += 1
            if exfil_attempts % 3 == 0:
                lan_scans += 1

            print(f"[honeypot] telemetry cpu={msg.get('cpu', 0):.2f} "
                  f"exfil={exfil_attempts} lan={lan_scans}")

            await _telemetry_queue.put({
                "type":           "honeypot_telemetry",
                "cpu":            msg.get("cpu", 0),
                "processes":      msg.get("processes", 0),
                "exfil_attempts": exfil_attempts,
                "lan_scans":      lan_scans,
            })

        # Acknowledge so virus thinks C2 is alive
        await ws.send(json.dumps({"type": "ack", "status": "ok"}))


async def _soma_reporter():
    """Connect to SOMA backend /honeypot and forward queued telemetry."""
    uri = f"ws://{SOMA_HOST}:{SOMA_PORT}/honeypot"
    while True:
        try:
            async with websockets.connect(uri) as soma_ws:
                print(f"[honeypot] Reporting to SOMA at {uri}")
                while True:
                    payload = await _telemetry_queue.get()
                    await soma_ws.send(json.dumps(payload))
        except Exception as e:
            print(f"[honeypot] SOMA connection error: {e} — retrying in 3s")
            await asyncio.sleep(3)


async def main():
    global _telemetry_queue
    _telemetry_queue = asyncio.Queue()

    print(f"[honeypot] Listening on 0.0.0.0:8766")
    print(f"[honeypot] Reporting to ws://{SOMA_HOST}:{SOMA_PORT}/honeypot")

    # Reporter runs in background
    asyncio.ensure_future(_soma_reporter())

    async with websockets.serve(_virus_handler, "0.0.0.0", 8766):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
