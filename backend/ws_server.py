"""
backend/ws_server.py — SOMA Live Demo
WebSocket + HTTP server on :8765

HTTP routes:
  GET /                         health check
  GET /download/virus.command   serve the virus script as a download

WebSocket paths:
  /dashboard          React frontend clients
  /virus              virus.command backdoor
  /agent/{NODE_NAME}  Docker container soma_agent.py connections
  /honeypot           Docker honeypot telemetry

State machine: CLEAN → EMAIL_RECEIVED → INFECTED → ISOLATING → CONTAINED → PURGED

Broadcast messages (server → dashboard):
  {"type": "email_notification", "from": ..., "subject": ..., "has_attachment": true}
  {"type": "node_metrics", "nodes": [{id, cpu, processes, anomaly_score, status}]}
  {"type": "state_change", "state": "...", "detection_secs": N}
  {"type": "honeypot_active", "port": 8766, "metrics": {...}}
  {"type": "lateral_movement", "from_node": ..., "src_ip": ..., "dst_ip": ..., "dst_port": N}
  {"type": "purge_complete"}

Anomaly detection (no external model — pure rolling z-score):
  Multi-signal: CPU 40% + net_bytes_out 40% + tcp_conn_count 20%
  display_score = 0.08 + max(composite_z, 0) * 0.20
  Isolation triggers when User0 display_score > 0.65 (z > 2.85σ above baseline)
  Baseline windows only updated during CLEAN / EMAIL_RECEIVED states.

Environment variables:
  GMAIL_USER         — Gmail address to poll
  GMAIL_APP_PASSWORD — 16-char Google App Password
  PORT               — listening port (default 8765)
"""

import asyncio
import collections
import http
import imaplib
import json
import os
import pathlib
import signal
import subprocess
import threading
import time
from email import message_from_bytes

import psutil
import websockets
from websockets.http11 import Headers, Response as WsResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT       = int(os.environ.get("PORT", 8765))
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")
VIRUS_PATH = pathlib.Path(__file__).parent / "virus.command"

# Nodes: User0 = host machine (psutil), rest = Docker containers (soma_agent.py)
_HOST_NAMES    = ["User0", "Enterprise0", "Enterprise1", "Op_Server0"]
_SOMA_NET_CIDR = "172.22.0."

# Anomaly detection
_WINDOW_SIZE       = 60    # rolling window ticks
_MIN_WINDOW        = 10    # min samples before scoring
_ANOMALY_THRESHOLD = 0.20  # display score that triggers isolation
_INFECTED_DWELL    = 3     # seconds in INFECTED before isolation can fire

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_demo_state: str         = "CLEAN"
_dashboard_clients: set  = set()
_virus_ws                = None
_virus_worker_pids: list = []
_event_loop              = None
_infected_at: float      = 0.0
_detection_secs: float   = 0.0
_honeypot_metrics_cache  = None   # cached for late-joining dashboard clients

# Latest metrics received from each Docker container agent
_agent_data: dict = {}   # node_name → latest agent_metrics dict

# Rolling windows for z-score baseline (separate per node)
_cpu_windows = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))
_net_windows = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))
_tcp_windows = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))

# Host net I/O delta tracking for User0
_host_net_prev_out: int = 0

# ---------------------------------------------------------------------------
# Anomaly scoring — rolling z-score (no external model)
# ---------------------------------------------------------------------------

def _z_score(val: float, window: collections.deque, min_std: float) -> float:
    if len(window) < _MIN_WINDOW:
        return 0.0
    vals = list(window)
    mean = sum(vals) / len(vals)
    var  = sum((v - mean) ** 2 for v in vals) / len(vals)
    std  = max(var ** 0.5, min_std)
    return (val - mean) / std


def _compute_anomaly(name: str, cpu: float, net_out: float, tcp_count: int) -> float:
    """
    Multi-signal z-score detector.
    Baseline windows grow only during CLEAN / EMAIL_RECEIVED states.
    At infection, baseline is frozen → z-score reflects true deviation.

    Isolation threshold 0.28 ≡ composite_z ≈ 1.0σ above clean baseline.
    """
    state = _demo_state
    if state in ("CLEAN", "EMAIL_RECEIVED"):
        _cpu_windows[name].append(cpu)
        _net_windows[name].append(float(net_out))
        _tcp_windows[name].append(float(tcp_count))

    z_cpu = _z_score(cpu,             _cpu_windows[name], min_std=0.02)
    z_net = _z_score(float(net_out),  _net_windows[name], min_std=1000.0)
    z_tcp = _z_score(float(tcp_count), _tcp_windows[name], min_std=1.0)

    composite = 0.4 * z_cpu + 0.4 * z_net + 0.2 * z_tcp
    display   = 0.08 + max(composite, 0.0) * 0.20
    return round(min(max(display, 0.0), 1.0), 3)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _get_state() -> str:
    return _demo_state


async def _set_state(new_state: str):
    global _demo_state, _infected_at, _detection_secs
    if new_state == "INFECTED":
        _infected_at = time.monotonic()
    elif new_state == "ISOLATING" and _infected_at:
        _detection_secs = round(time.monotonic() - _infected_at, 1)
    _demo_state = new_state
    print(f"[soma] State → {new_state}")
    await _broadcast({
        "type":           "state_change",
        "state":          new_state,
        "detection_secs": _detection_secs if new_state == "ISOLATING" else 0,
    })


async def _broadcast(msg: dict):
    global _dashboard_clients
    if not _dashboard_clients:
        return
    data = json.dumps(msg)
    dead = set()
    for ws in list(_dashboard_clients):
        try:
            await ws.send(data)
        except Exception:
            dead.add(ws)
    _dashboard_clients -= dead


def _post_to_loop(coro):
    if _event_loop and not _event_loop.is_closed():
        asyncio.run_coroutine_threadsafe(coro, _event_loop)


# ---------------------------------------------------------------------------
# Gmail IMAP polling (background thread)
# ---------------------------------------------------------------------------

def _imap_poll_loop():
    if not GMAIL_USER or not GMAIL_PASS:
        print("[imap] GMAIL_USER/GMAIL_APP_PASSWORD not set — email trigger disabled")
        print("[imap] Use set_infected message from dashboard to trigger manually")
        return
    print(f"[imap] Polling {GMAIL_USER} every 2s")
    while True:
        try:
            if _get_state() == "CLEAN":
                with imaplib.IMAP4_SSL("imap.gmail.com") as mail:
                    mail.login(GMAIL_USER, GMAIL_PASS)
                    mail.select("INBOX")
                    _, ids = mail.search(None, "UNSEEN")
                    uid_list = (ids[0] or b"").split()
                    if uid_list:
                        uid = uid_list[0]
                        _, raw_data = mail.fetch(uid, "(RFC822)")
                        raw = raw_data[0][1]
                        msg = message_from_bytes(raw)
                        sender  = msg.get("From",    "unknown@sender.com")
                        subject = msg.get("Subject", "(no subject)")
                        mail.store(uid, "+FLAGS", "\\Seen")
                        print(f"[imap] New email from {sender}: {subject}")
                        _post_to_loop(_on_email_received(sender, subject))
        except Exception as e:
            print(f"[imap] Error: {e}")
        time.sleep(2)


async def _on_email_received(sender: str, subject: str):
    await _set_state("EMAIL_RECEIVED")
    await _broadcast({
        "type":           "email_notification",
        "from":           sender,
        "subject":        subject,
        "has_attachment": True,
    })


# ---------------------------------------------------------------------------
# psutil monitoring loop (1-second asyncio task)
# ---------------------------------------------------------------------------

async def _psutil_loop():
    global _host_net_prev_out
    print("[psutil] Monitoring loop started")
    psutil.cpu_percent(interval=None)   # warm-up (first call always returns 0)
    _host_net_prev_out = psutil.net_io_counters().bytes_sent
    await asyncio.sleep(1)

    while True:
        await asyncio.sleep(1)
        state = _get_state()

        # ── User0: real host machine readings ──────────────────────────────
        cpu_raw = psutil.cpu_percent(interval=None)
        procs   = len(psutil.pids())
        net_now = psutil.net_io_counters()
        net_out = max(0, net_now.bytes_sent - _host_net_prev_out)
        _host_net_prev_out = net_now.bytes_sent
        try:
            tcp_count = len([c for c in psutil.net_connections() if c.status == "ESTABLISHED"])
        except Exception:
            tcp_count = 0

        user0_anom = _compute_anomaly("User0", cpu_raw, net_out, tcp_count)

        nodes = [{
            "id":            "User0",
            "cpu":           round(cpu_raw / 100, 3),
            "processes":     procs,
            "anomaly_score": user0_anom,
            "status":        "red" if user0_anom > 0.75 else "yellow" if user0_anom > 0.5 else "green",
        }]

        # ── Container nodes: data from soma_agent.py ───────────────────────
        for name in _HOST_NAMES[1:]:
            data = _agent_data.get(name)
            if data:
                c_cpu  = data.get("cpu_pct", 0.0)
                c_net  = data.get("net_bytes_out", 0)
                c_tcp  = data.get("tcp_conn_count", 0)
                c_proc = data.get("proc_count", 0)
                anom   = _compute_anomaly(name, c_cpu, c_net, c_tcp)
            else:
                c_cpu  = 0.0
                c_proc = 0
                anom   = 0.04   # show as offline/quiet

            status = "red" if anom > 0.75 else "yellow" if anom > 0.5 else "green"
            nodes.append({
                "id":            name,
                "cpu":           round(c_cpu / 100, 3) if data else 0.0,
                "processes":     c_proc,
                "anomaly_score": round(anom, 3),
                "status":        status,
            })

        await _broadcast({"type": "node_metrics", "nodes": nodes})

        # ── Anomaly-triggered isolation ─────────────────────────────────────
        if (state == "INFECTED"
                and user0_anom > _ANOMALY_THRESHOLD
                and _infected_at > 0
                and time.monotonic() - _infected_at >= _INFECTED_DWELL):
            await _set_state("ISOLATING")
            asyncio.create_task(_isolate())


# ---------------------------------------------------------------------------
# Container agent handler
# ---------------------------------------------------------------------------

async def _handle_agent(websocket, node_name: str):
    """Receive soma_agent.py metrics from a Docker container."""
    print(f"[ws/agent:{node_name}] connected")
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") != "agent_metrics":
                continue

            _agent_data[node_name] = msg

            # Lateral movement: new TCP connections between soma-net nodes
            for conn in msg.get("new_connections", []):
                src = conn.get("src_ip", "")
                dst = conn.get("dst_ip", "")
                if src.startswith(_SOMA_NET_CIDR) and dst.startswith(_SOMA_NET_CIDR):
                    print(f"[soma] Lateral movement: {src} → {dst} on {node_name}")
                    await _broadcast({
                        "type":      "lateral_movement",
                        "from_node": node_name,
                        "src_ip":    src,
                        "dst_ip":    dst,
                        "dst_port":  conn.get("dst_port", 0),
                    })

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _agent_data.pop(node_name, None)
        print(f"[ws/agent:{node_name}] disconnected")


# ---------------------------------------------------------------------------
# Isolation — Docker honeypot + virus redirect
# ---------------------------------------------------------------------------

async def _isolate():
    print("[soma] Spawning Docker honeypot (soma_honeypot_image → :8766)...")
    try:
        subprocess.Popen([
            "docker", "run", "-d",
            "--name", "soma_honeypot",
            "--network", "soma-net",
            "--ip", "172.22.0.99",
            "-p", "8766:8766",
            "-p", "8082:80",
            "-e", "SOMA_HOST=host.docker.internal",
            "-e", "SOMA_PORT=8765",
            "-e", "NODE_NAME=Honeypot",
            "soma_honeypot_image",
        ])
    except Exception as e:
        print(f"[soma] Docker error: {e}")

    await asyncio.sleep(2)

    if _virus_ws is not None:
        try:
            await _virus_ws.send(json.dumps({"type": "redirect", "port": 8766}))
            print("[soma] Redirect sent to virus → :8766")
        except Exception as e:
            print(f"[soma] Redirect error: {e}")

    await _set_state("CONTAINED")


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------

def _kill_container_workers():
    for name in _HOST_NAMES:  # include User0 container for SSH-pivoted workers
        container = "soma-" + name.lower().replace("_", "-")
        try:
            subprocess.run(
                ["docker", "exec", container, "pkill", "-f", "python3"],
                check=False, capture_output=True, timeout=5,
            )
            print(f"[soma] Killed python3 workers in {container}")
        except Exception as e:
            print(f"[soma] Could not kill workers in {container}: {e}")


async def _purge():
    global _virus_worker_pids, _honeypot_metrics_cache
    print("[soma] Purging honeypot and workers...")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _docker_cleanup)
    # Kill local CPU worker PIDs from virus.command
    for pid_str in _virus_worker_pids:
        try:
            os.kill(int(pid_str), signal.SIGTERM)
            print(f"[soma] Killed worker PID {pid_str}")
        except Exception:
            pass
    _virus_worker_pids = []
    # Kill all SOMA_WORKER-tagged processes (catches stale workers from prev sessions)
    subprocess.run(["pkill", "-f", "SOMA_WORKER"], check=False)
    # Kill SSH-spawned python3 workers inside each container and docker exec processes
    await loop.run_in_executor(None, _kill_container_workers)
    # Kill any lingering docker exec ssh processes on the host
    subprocess.run(["pkill", "-f", "docker exec.*soma.*ssh"], check=False)
    _honeypot_metrics_cache = None
    await _set_state("PURGED")
    await _broadcast({"type": "purge_complete"})


def _docker_cleanup():
    subprocess.run(["docker", "stop", "soma_honeypot"], check=False, capture_output=True)
    subprocess.run(["docker", "rm",   "soma_honeypot"], check=False, capture_output=True)
    print("[soma] Docker container stopped and removed")


async def _reset_demo():
    global _infected_at, _detection_secs, _virus_ws, _virus_worker_pids, _honeypot_metrics_cache
    print("[soma] Resetting → CLEAN")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _docker_cleanup)
    for pid_str in _virus_worker_pids:
        try:
            os.kill(int(pid_str), signal.SIGTERM)
        except Exception:
            pass
    _virus_worker_pids      = []
    _virus_ws               = None
    _infected_at            = 0.0
    _detection_secs         = 0.0
    _honeypot_metrics_cache = None
    await _set_state("CLEAN")
    await _broadcast({"type": "demo_reset"})
    print("[soma] Demo reset complete")


# ---------------------------------------------------------------------------
# HTTP handler (before WebSocket upgrade)
# ---------------------------------------------------------------------------

async def _process_request(connection, request):
    path = request.path

    if path == "/":
        return connection.respond(http.HTTPStatus.OK, "SOMA demo running\n")

    if path == "/download/virus.command":
        if VIRUS_PATH.exists():
            body = VIRUS_PATH.read_bytes()
            hdrs = Headers([
                ("Content-Type",        "application/octet-stream"),
                ("Content-Disposition", 'attachment; filename="virus.command"'),
                ("Content-Length",      str(len(body))),
                ("Access-Control-Allow-Origin", "*"),
            ])
            return WsResponse(200, "OK", hdrs, body)
        return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found\n")

    # All WebSocket paths fall through to upgrade
    return None


# ---------------------------------------------------------------------------
# WebSocket router
# ---------------------------------------------------------------------------

async def _handle_client(websocket):
    global _virus_ws, _virus_worker_pids, _honeypot_metrics_cache

    path = websocket.request.path

    # ── Dashboard ──────────────────────────────────────────────────────────
    if path == "/dashboard":
        _dashboard_clients.add(websocket)
        print(f"[ws/dashboard] connected ({len(_dashboard_clients)} clients)")
        try:
            # Catch up new client on current state
            await websocket.send(json.dumps({
                "type":           "state_change",
                "state":          _get_state(),
                "detection_secs": _detection_secs,
            }))
            if _honeypot_metrics_cache is not None:
                await websocket.send(json.dumps(_honeypot_metrics_cache))

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                t = msg.get("type")
                if t == "purge":
                    await _purge()
                elif t == "set_infected":
                    if _get_state() in ("CLEAN", "EMAIL_RECEIVED"):
                        await _set_state("INFECTED")
                elif t == "reset":
                    await _reset_demo()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            _dashboard_clients.discard(websocket)
            print(f"[ws/dashboard] disconnected ({len(_dashboard_clients)} clients)")

    # ── Virus backdoor ─────────────────────────────────────────────────────
    elif path == "/virus":
        _virus_ws = websocket
        print("[ws/virus] Backdoor connected")
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "virus_connect":
                    _virus_worker_pids = [str(p) for p in msg.get("cpu_workers", [])]
                    print(f"[ws/virus] PID={msg.get('pid')}  workers={_virus_worker_pids}")
                    if _get_state() == "EMAIL_RECEIVED":
                        await _set_state("INFECTED")
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if _virus_ws is websocket:
                _virus_ws = None
            print("[ws/virus] Backdoor disconnected")

    # ── Container agents ───────────────────────────────────────────────────
    elif path.startswith("/agent/"):
        node_name = path[len("/agent/"):]
        await _handle_agent(websocket, node_name)

    # ── Honeypot telemetry ─────────────────────────────────────────────────
    elif path == "/honeypot":
        print("[ws/honeypot] Docker honeypot connected")
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "honeypot_telemetry":
                    payload = {
                        "type": "honeypot_active",
                        "port": 8766,
                        "metrics": {
                            "cpu":         msg.get("cpu", 0),
                            "processes":   msg.get("processes", 0),
                            "connections": msg.get("connections", 0),
                        },
                    }
                    _honeypot_metrics_cache = payload
                    await _broadcast(payload)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            print("[ws/honeypot] Docker honeypot disconnected")

    else:
        await websocket.close(1008, "Unknown path")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    print(f"[soma] Starting on :{PORT}")
    if not GMAIL_USER:
        print("[soma] WARNING: GMAIL_USER not set — email trigger disabled")
        print("[soma]          Send {type:set_infected} from dashboard to trigger manually")

    threading.Thread(target=_imap_poll_loop, daemon=True).start()
    asyncio.create_task(_psutil_loop())

    async with websockets.serve(
        _handle_client,
        "0.0.0.0",
        PORT,
        process_request=_process_request,
    ):
        print(f"[soma] Ready")
        print(f"[soma]   GET http://0.0.0.0:{PORT}/download/virus.command")
        print(f"[soma]   WS  ws://0.0.0.0:{PORT}/dashboard")
        print(f"[soma]   WS  ws://0.0.0.0:{PORT}/virus")
        print(f"[soma]   WS  ws://0.0.0.0:{PORT}/agent/{{NODE_NAME}}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
