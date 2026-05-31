"""
backend/ws_server.py
=====================
WebSocket server for SOMA demo — streams the pre-recorded episode JSON
to connected frontend clients.

Since CybORG cannot run in a cloud environment, this server replays
the pre-generated demo_episode.json over WebSocket so the frontend
shows "● LIVE" and receives real-time step updates.

Usage:
  python ws_server.py

Environment variables:
  PORT      — listening port (default 8765)
  EPISODE   — path to episode JSON (default data/demo_episode.json)
  STEP_DELAY — seconds between steps (default 0.3)
"""

import asyncio
import http
import json
import os
import pathlib
import websockets

PORT       = int(os.environ.get("PORT", 8765))
EPISODE    = os.environ.get("EPISODE", "data/demo_episode.json")
STEP_DELAY = float(os.environ.get("STEP_DELAY", 0.3))

_episode_cache: dict | None = None


def load_episode() -> dict:
    global _episode_cache
    if _episode_cache is None:
        ep_path = pathlib.Path(EPISODE)
        if not ep_path.exists():
            raise FileNotFoundError(f"Episode file not found: {ep_path.resolve()}")
        _episode_cache = json.loads(ep_path.read_text())
        print(f"[ws_server] Loaded episode: {len(_episode_cache['steps'])} steps")
    return _episode_cache


async def handle_client(websocket):
    """Stream episode steps one at a time to the connected client."""
    addr = websocket.remote_address
    print(f"[ws_server] Client connected: {addr}")
    try:
        episode = load_episode()
        meta    = episode["meta"]
        steps   = episode["steps"]

        for i, step in enumerate(steps):
            payload = {"meta": meta, "step_index": i, **step}
            await websocket.send(json.dumps(payload))
            await asyncio.sleep(STEP_DELAY)

        # Send completion signal
        await websocket.send(json.dumps({"done": True, "total_steps": len(steps)}))
        print(f"[ws_server] Episode complete for {addr}")
    except websockets.exceptions.ConnectionClosedOK:
        print(f"[ws_server] Client disconnected: {addr}")
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"[ws_server] Connection error {addr}: {e}")
    except Exception as e:
        print(f"[ws_server] Error serving {addr}: {e}")
        try:
            await websocket.send(json.dumps({"error": str(e)}))
        except Exception:
            pass


async def process_request(connection, request):
    """Intercept GET /health before WebSocket upgrade — prevents Render free-tier sleep.
    Ping this endpoint every 14 min with UptimeRobot or cron-job.org to keep the server warm."""
    if request.path == "/health":
        return connection.respond(http.HTTPStatus.OK, "OK\n")
    return None  # proceed with WebSocket handshake


async def main():
    print(f"[ws_server] Starting on port {PORT}")
    print(f"[ws_server] Episode: {EPISODE}")
    print(f"[ws_server] Step delay: {STEP_DELAY}s")
    async with websockets.serve(handle_client, "0.0.0.0", PORT,
                                process_request=process_request):
        print(f"[ws_server] Ready — ws://0.0.0.0:{PORT}")
        print(f"[ws_server] Health check — http://0.0.0.0:{PORT}/health")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
