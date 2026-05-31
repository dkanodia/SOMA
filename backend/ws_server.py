"""
backend/ws_server.py — SOMA Live Demo
WebSocket + HTTP server

HTTP routes:
  GET /         health check

WebSocket paths:
  /dashboard    React frontend clients
  /agent/{NODE} Docker container soma_agent.py connections
  /honeypot     Docker honeypot telemetry

State machine: CLEAN → INFECTED → ISOLATING → CONTAINED → PURGED

Detection: 4-signal behavioral z-score over real psutil readings.
SOMA identifies suspicious processes by their CPU usage at detection time.
No attack tool is bundled with or served by this server.

Environment variables (all optional — defaults shown):
  PORT               Listening port                  (8765)
  HONEYPOT_PORT      Port exposed by honeypot image  (8766)
  HONEYPOT_IMAGE     Docker image name               (soma_honeypot_image)
  HONEYPOT_HTTP_PORT Honeypot HTTP port mapping      (8082)
  HONEYPOT_IP        Static IP inside soma-net       (172.22.0.99)
  VICTIM_NODE        Node name for the host machine  (User0)
  HOST_NODES         Comma-separated container nodes (Enterprise0,Enterprise1,Op_Server0)
  SOMA_NET_CIDR      Network prefix for soma-net     (172.22.0.)
  ANOMALY_THRESHOLD  Score to enter INFECTED state   (0.40)
  INFECTED_DWELL     Seconds before ISOLATING fires  (5)
  WINDOW_SIZE        Rolling baseline window (ticks) (60)
"""

import asyncio
import collections
import http
import json
import os
import pathlib
import signal

# Load backend/.env if present (never committed; keeps secrets out of env exports)
_env_file = pathlib.Path(__file__).parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)
import subprocess
import time

import psutil
import websockets
from websockets.http11 import Headers, Response as WsResponse

# ---------------------------------------------------------------------------
# Config — all values from environment, sensible defaults
# ---------------------------------------------------------------------------

PORT             = int(os.environ.get("PORT", 8765))

HONEYPOT_PORT      = int(os.environ.get("HONEYPOT_PORT", 8766))
HONEYPOT_HTTP_PORT = int(os.environ.get("HONEYPOT_HTTP_PORT", 8082))
HONEYPOT_IMAGE     = os.environ.get("HONEYPOT_IMAGE", "soma_honeypot_image")
HONEYPOT_IP        = os.environ.get("HONEYPOT_IP", "172.22.0.99")

VICTIM_NODE    = os.environ.get("VICTIM_NODE", "User0")
_CONTAINER_NODES = [
    n.strip() for n in os.environ.get("HOST_NODES", "Enterprise0,Enterprise1,Op_Server0").split(",")
    if n.strip()
]
_SOMA_NET_CIDR   = os.environ.get("SOMA_NET_CIDR", "172.22.0.")

_WINDOW_SIZE       = int(os.environ.get("WINDOW_SIZE", 60))
_MIN_WINDOW        = 15   # build 15s baseline before detection starts
_ANOMALY_THRESHOLD = float(os.environ.get("ANOMALY_THRESHOLD", 0.20))
_INFECTED_DWELL    = int(os.environ.get("INFECTED_DWELL", 3))

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_demo_state: str          = "CLEAN"
_dashboard_clients: set   = set()
_infected_at: float       = 0.0
_detection_secs: float    = 0.0
_honeypot_metrics_cache   = None
_suspicious_pids: list    = []   # PIDs captured by psutil at detection time
_anomaly_streak: int      = 0    # consecutive ticks above threshold before INFECTED

# Latest metrics from Docker container agents
_agent_data: dict = {}   # node_name → latest dict

# Rolling z-score baselines (frozen when state leaves CLEAN/EMAIL_RECEIVED)
_cpu_windows  = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))
_net_windows  = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))
_proc_windows = collections.defaultdict(lambda: collections.deque(maxlen=_WINDOW_SIZE))

_host_net_prev_out: int = 0
_host_prev_procs:   int = 0

# ---------------------------------------------------------------------------
# Anomaly scoring — rolling z-score
# ---------------------------------------------------------------------------

def _z_score(val: float, window: collections.deque, min_std: float) -> float:
    if len(window) < _MIN_WINDOW:
        return 0.0
    vals = list(window)
    mean = sum(vals) / len(vals)
    var  = sum((v - mean) ** 2 for v in vals) / len(vals)
    std  = max(var ** 0.5, min_std)
    return (val - mean) / std


def _compute_anomaly(name: str, cpu: float, net_out: float, proc_count: int) -> float:
    """
    3-signal behavioral z-score using only signals readable without root on macOS.
      cpu       — sustained burn (primary signal)
      net_out   — outbound bytes delta per second
      proc      — total process count elevation (30+ extra processes from payload)
    """
    if _demo_state in ("CLEAN", "EMAIL_RECEIVED"):
        _cpu_windows[name].append(cpu)
        _net_windows[name].append(float(net_out))
        _proc_windows[name].append(float(proc_count))

    z_cpu  = _z_score(cpu,              _cpu_windows[name], min_std=3.0)
    z_net  = _z_score(float(net_out),   _net_windows[name], min_std=200_000.0)
    z_proc = _z_score(float(proc_count),_proc_windows[name],min_std=5.0)

    composite = 0.60 * z_cpu + 0.20 * z_net + 0.20 * z_proc
    display   = 0.08 + max(composite, 0.0) * 0.25
    return round(min(max(display, 0.0), 1.0), 3)


# ---------------------------------------------------------------------------
# Process identification — capture suspicious PIDs at detection time
# ---------------------------------------------------------------------------

_PAYLOAD_MARKER = "SOMA_PAYLOAD"

def _snapshot_suspicious_pids() -> list:
    """
    Find and return PIDs of payload processes by their cmdline marker.
    Only processes containing SOMA_PAYLOAD in their cmdline are targeted —
    no CPU heuristics, no safe lists, no risk of touching system processes.
    """
    found = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if _PAYLOAD_MARKER in cmdline:
                found.append(proc.info["pid"])
                print(f"[soma] Payload PID {proc.info['pid']} identified via marker")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return found


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
        "victim_node":    VICTIM_NODE,
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


# ---------------------------------------------------------------------------
# psutil monitoring loop (1-second asyncio task)
# ---------------------------------------------------------------------------

async def _psutil_loop():
    global _host_net_prev_out, _host_prev_procs, _suspicious_pids, _anomaly_streak
    print("[psutil] Monitoring loop started")
    psutil.cpu_percent(interval=None)   # warm-up
    _host_net_prev_out = psutil.net_io_counters().bytes_sent
    _host_prev_procs   = len(psutil.pids())
    await asyncio.sleep(1)

    while True:
        await asyncio.sleep(1)
        state = _get_state()

        # ── Victim host: real psutil readings ──────────────────────────────
        cpu_raw  = psutil.cpu_percent(interval=None)
        procs    = len(psutil.pids())
        net_now  = psutil.net_io_counters()
        net_out  = max(0, net_now.bytes_sent - _host_net_prev_out)
        _host_net_prev_out = net_now.bytes_sent

        _host_prev_procs = procs

        victim_anom = _compute_anomaly(VICTIM_NODE, cpu_raw, net_out, procs)

        nodes = [{
            "id":            VICTIM_NODE,
            "cpu":           round(cpu_raw / 100, 3),
            "processes":     procs,
            "anomaly_score": victim_anom,
            "status":        "red" if victim_anom > 0.75 else "yellow" if victim_anom > 0.5 else "green",
        }]

        # ── Container nodes: data from soma_agent.py ───────────────────────
        for name in _CONTAINER_NODES:
            data  = _agent_data.get(name)
            if data:
                c_cpu  = data.get("cpu_pct", 0.0)
                c_net  = data.get("net_bytes_out", 0)
                c_tcp  = data.get("tcp_conn_count", 0)
                c_proc = data.get("proc_count", 0)
                anom   = _compute_anomaly(name, c_cpu, c_net, c_tcp)
            else:
                c_cpu  = 0.0
                c_proc = 0
                anom   = 0.04

            nodes.append({
                "id":            name,
                "cpu":           round(c_cpu / 100, 3) if data else 0.0,
                "processes":     c_proc,
                "anomaly_score": round(anom, 3),
                "status":        "red" if anom > 0.75 else "yellow" if anom > 0.5 else "green",
            })

        await _broadcast({"type": "node_metrics", "nodes": nodes, "victim_node": VICTIM_NODE})

        # ── Anomaly-driven state transitions ────────────────────────────────
        if state in ("CLEAN", "EMAIL_RECEIVED"):
            if victim_anom > _ANOMALY_THRESHOLD:
                _anomaly_streak += 1
                print(f"[soma] Anomaly streak: {_anomaly_streak} (score={victim_anom:.3f})")
            else:
                _anomaly_streak = 0  # brief spikes (opening app/tab) reset the counter

            # Require 4 consecutive seconds above threshold — rules out transient spikes
            if _anomaly_streak >= 4:
                _anomaly_streak = 0
                _suspicious_pids = _snapshot_suspicious_pids()
                print(f"[soma] Sustained anomaly — suspicious PIDs: {_suspicious_pids}")
                await _set_state("INFECTED")

        elif (state == "INFECTED"
              and _infected_at > 0
              and time.monotonic() - _infected_at >= _INFECTED_DWELL):
            await _set_state("ISOLATING")
            asyncio.create_task(_isolate())


# ---------------------------------------------------------------------------
# Container agent handler
# ---------------------------------------------------------------------------

async def _handle_agent(websocket, node_name: str):
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
# Isolation — spawn Docker honeypot
# ---------------------------------------------------------------------------

async def _isolate():
    print(f"[soma] Spawning Docker honeypot ({HONEYPOT_IMAGE} → :{HONEYPOT_PORT})...")
    try:
        subprocess.Popen([
            "docker", "run", "-d",
            "--name", "soma_honeypot",
            "--network", "soma-net",
            "--ip", HONEYPOT_IP,
            "-p", f"{HONEYPOT_PORT}:{HONEYPOT_PORT}",
            "-p", f"{HONEYPOT_HTTP_PORT}:80",
            "-e", f"SOMA_HOST=host.docker.internal",
            "-e", f"SOMA_PORT={PORT}",
            "-e", "NODE_NAME=Honeypot",
            HONEYPOT_IMAGE,
        ])
    except Exception as e:
        print(f"[soma] Docker error: {e}")

    await _set_state("CONTAINED")

    # Freeze malicious processes — SIGSTOP suspends them instantly (CPU → 0)
    # They remain visible in ps but cannot execute until SIGCONT or SIGKILL
    frozen = []
    for pid in _suspicious_pids:
        try:
            os.kill(pid, signal.SIGSTOP)
            frozen.append(pid)
            print(f"[soma] SIGSTOP PID {pid} — process quarantined")
        except Exception as e:
            print(f"[soma] Could not SIGSTOP PID {pid}: {e}")

    if frozen:
        await _broadcast({
            "type":        "quarantine_update",
            "frozen_pids": frozen,
            "message":     f"SOMA quarantined {len(frozen)} malicious process(es) — execution suspended",
        })


# ---------------------------------------------------------------------------
# Purge — kill identified suspicious processes + container
# ---------------------------------------------------------------------------

def _kill_container_workers():
    for name in _CONTAINER_NODES:
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
    global _suspicious_pids, _honeypot_metrics_cache
    print("[soma] Purging honeypot and identified suspicious processes...")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _docker_cleanup)

    # Kill processes SOMA identified at detection time
    # SIGCONT first to wake stopped processes, then SIGKILL to destroy them
    for pid in _suspicious_pids:
        try:
            os.kill(pid, signal.SIGCONT)
        except Exception:
            pass
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"[soma] Killed suspicious process PID {pid}")
        except Exception:
            pass
    _suspicious_pids = []

    # Catch any stragglers left from previous sessions
    subprocess.run(["pkill", "-f", "SOMA_WORKER"], check=False)
    await loop.run_in_executor(None, _kill_container_workers)

    _honeypot_metrics_cache = None
    await _set_state("PURGED")
    await _broadcast({"type": "purge_complete"})


def _docker_cleanup():
    try:
        subprocess.run(["docker", "stop", "--time", "0", "soma_honeypot"], check=False, capture_output=True, timeout=5)
    except Exception:
        pass
    try:
        subprocess.run(["docker", "rm", "--force", "soma_honeypot"], check=False, capture_output=True, timeout=5)
    except Exception:
        pass
    print("[soma] Docker container stopped and removed")


def _clear_baselines():
    """Wipe all rolling baseline windows so next readings build a fresh baseline."""
    for d in (_cpu_windows, _net_windows, _proc_windows):
        d.clear()


async def _reset_demo():
    global _infected_at, _detection_secs, _suspicious_pids, _honeypot_metrics_cache
    global _host_prev_procs, _anomaly_streak
    print("[soma] Resetting → CLEAN")
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _docker_cleanup)
    for pid in _suspicious_pids:
        try:
            os.kill(pid, signal.SIGCONT)
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    _suspicious_pids        = []
    _infected_at            = 0.0
    _detection_secs         = 0.0
    _honeypot_metrics_cache = None
    _host_prev_procs        = len(psutil.pids())
    _anomaly_streak         = 0
    _clear_baselines()   # ← fresh baseline after reset; avoids immediate re-detection
    await _set_state("CLEAN")
    await _broadcast({"type": "demo_reset"})
    print("[soma] Demo reset complete — baselines cleared")


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

_WS_PATHS = {"/dashboard", "/honeypot"}

async def _process_request(connection, request):
    path = request.path

    if path == "/":
        return connection.respond(http.HTTPStatus.OK, "SOMA demo running\n")

    # Accept known WebSocket paths and /agent/* dynamic paths
    if path in _WS_PATHS or path.startswith("/agent/"):
        return None   # fall through to WebSocket upgrade

    # Reject everything else at the HTTP level (before upgrade)
    return connection.respond(http.HTTPStatus.NOT_FOUND, "Not found\n")


# ---------------------------------------------------------------------------
# WebSocket router
# ---------------------------------------------------------------------------

async def _handle_client(websocket):
    global _honeypot_metrics_cache

    path = websocket.request.path

    # ── Dashboard ──────────────────────────────────────────────────────────
    if path == "/dashboard":
        _dashboard_clients.add(websocket)
        print(f"[ws/dashboard] connected ({len(_dashboard_clients)} clients)")
        try:
            await websocket.send(json.dumps({
                "type":           "state_change",
                "state":          _get_state(),
                "detection_secs": _detection_secs,
                "victim_node":    VICTIM_NODE,
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
            # Auto-reset when last client leaves — browser refresh always starts fresh
            if not _dashboard_clients and _get_state() != "CLEAN":
                print("[soma] No clients — auto-resetting to CLEAN")
                await _reset_demo()

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
                        "port": HONEYPOT_PORT,
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
    print(f"[soma] Starting on :{PORT}")
    print(f"[soma] Victim node: {VICTIM_NODE}  |  Container nodes: {_CONTAINER_NODES}")
    print(f"[soma] Anomaly threshold: {_ANOMALY_THRESHOLD}  |  Infected dwell: {_INFECTED_DWELL}s")

    asyncio.create_task(_psutil_loop())

    async with websockets.serve(
        _handle_client,
        "0.0.0.0",
        PORT,
        process_request=_process_request,
    ):
        print(f"[soma] Ready")
        print(f"[soma]   GET  http://0.0.0.0:{PORT}/")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/dashboard")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/agent/{{NODE_NAME}}")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/honeypot")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
