"""
backend/ws_server.py
====================
SOMA Live Demo — WebSocket + HTTP server on port 8765.

HTTP routes (via process_request before WS upgrade):
  GET /                           health check
  GET /download/virus.command     serve the virus script as a download

WebSocket paths:
  /dashboard    React frontend — receives all broadcast messages, sends purge
  /virus        virus.command backdoor — bidirectional
  /honeypot     Docker container — sends telemetry here instead of HTTP POST

Background tasks:
  - Gmail IMAP polling thread (every 2s) → EMAIL_RECEIVED on new unseen email
  - psutil monitoring asyncio loop (every 1s) → node_metrics broadcast
  - Anomaly detection → ISOLATING + Docker spawn + virus redirect

State machine:
  CLEAN → EMAIL_RECEIVED → INFECTED → ISOLATING → CONTAINED → PURGED

Broadcast messages (server → dashboard):
  {"type": "email_notification", "from": ..., "subject": ..., "has_attachment": true}
  {"type": "node_metrics", "nodes": [{id, cpu, processes, anomaly_score, status}]}
  {"type": "state_change", "state": "..."}
  {"type": "honeypot_active", "port": 8766, "metrics": {cpu, processes, exfil_attempts, lan_scans}}
  {"type": "purge_complete"}

Environment variables:
  GMAIL_USER         — Gmail address to poll
  GMAIL_APP_PASSWORD — 16-char Google App Password
  PORT               — listening port (default 8765)
"""

import asyncio
import http
import imaplib
import json
import os
import pathlib
import random
import signal
import subprocess
import sys
import threading
import time
from email import message_from_bytes

import numpy as np
import psutil
import websockets
from websockets.http11 import Headers, Response as WsResponse

# Add SOMA root to path so soma.* imports resolve from the backend directory
_SOMA_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(_SOMA_ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT       = int(os.environ.get("PORT", 8765))
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")
VIRUS_PATH = pathlib.Path(__file__).parent / "virus.command"

# ---------------------------------------------------------------------------
# InnateImmunityLayer — loaded once at startup
# ---------------------------------------------------------------------------

# 30-dim feature order expected by the model (from soma/envs/cyborg_wrapper.py)
_MODEL_HOST_NAMES = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]
_FEATURES_PER_HOST = 5
_NETWORK_POS = {
    "User0": 0.10, "User1": 0.10, "User2": 0.10,
    "Enterprise0": 0.50, "Enterprise1": 0.50,
    "Op_Server0": 0.90,
}

_innate_model = None   # InnateImmunityLayer instance, or None if not loadable
_innate_baseline: float = 0.0  # clean-Mac raw score, calibrated at startup


def _load_innate_model():
    global _innate_model
    model_path = _SOMA_ROOT / "models" / "innate" / "isolation_forest.joblib"
    if not model_path.exists():
        print(f"[innate] Model not found at {model_path} — using heuristic fallback")
        return
    try:
        from soma.layers.innate import InnateImmunityLayer
        _innate_model = InnateImmunityLayer.load(model_path)
        print(f"[innate] Loaded IsolationForest  threshold={_innate_model.threshold_:.4f}")
        # Calibrate baseline from actual Mac idle readings
        _calibrate_baseline()
    except Exception as e:
        print(f"[innate] Could not load model ({e}) — using heuristic fallback")


def _calibrate_baseline(n_samples: int = 10, delay: float = 0.2):
    """
    Take N psutil samples of the clean Mac and compute the mean IF score.
    This corrects for the gap between CybORG training data (near-zero CPU)
    and real Mac baseline (~10-20% CPU), so the displayed score is meaningful.
    """
    global _innate_baseline
    psutil.cpu_percent(interval=None)   # warm up
    scores = []
    for _ in range(n_samples):
        time.sleep(delay)
        cpu = psutil.cpu_percent(interval=None) / 100
        procs_norm = min(len(psutil.pids()) / 200, 1.0)
        obs = _build_obs_30dim(cpu, procs_norm, 0.0)
        scores.append(_innate_model.anomaly_score(obs))
    _innate_baseline = float(np.mean(scores))
    print(f"[innate] Mac clean baseline: {_innate_baseline:.4f}  "
          f"(delta to threshold: {_innate_model.threshold_ - _innate_baseline:+.4f})")


def _build_obs_30dim(
    user0_cpu: float,
    user0_procs: float,
    user0_compromised: float,
) -> np.ndarray:
    """
    Build a 30-dim observation vector for the InnateImmunityLayer.
    User0 gets real psutil values; other hosts get clean simulated values.

    Feature layout per host: [activity, compromised, sessions, processes, network_pos]
    """
    obs = np.zeros(_FEATURES_PER_HOST * len(_MODEL_HOST_NAMES), dtype=np.float32)
    for i, host in enumerate(_MODEL_HOST_NAMES):
        start = i * _FEATURES_PER_HOST
        if host == "User0":
            obs[start + 0] = user0_cpu           # activity  = CPU usage
            obs[start + 1] = user0_compromised   # compromised flag
            obs[start + 2] = user0_procs         # sessions proxy
            obs[start + 3] = user0_compromised   # processes spike when compromised
            obs[start + 4] = _NETWORK_POS[host]
        else:
            # Simulated clean host: very low near-zero activity
            clean_val = max(0.0, random.gauss(0.03, 0.005))
            obs[start + 0] = clean_val
            obs[start + 1] = 0.0
            obs[start + 2] = clean_val
            obs[start + 3] = 0.0
            obs[start + 4] = _NETWORK_POS.get(host, 0.5)
    return obs


def _compute_user0_anomaly(
    cpu: float,
    procs_norm: float,
    compromised: float,
    state: str,
) -> float:
    """
    Compute User0 anomaly score using the real InnateImmunityLayer model.

    The model was trained on CybORG clean data (near-zero CPU/features), so
    a normal Mac already scores above the calibrated CybORG threshold. We
    correct for this by computing the delta above the Mac clean baseline,
    then amplifying so the infected state clearly crosses 0.65+ for the demo:

      display = 0.08 + (raw - baseline) * amplification

    - Clean state:    delta ≈ 0.0   → display ≈ 0.08  (green)
    - Infected state: delta ≈ 0.025 → display ≈ 0.83  (red) with amp=30
    """
    if _innate_model is not None:
        obs = _build_obs_30dim(cpu, procs_norm, compromised)
        raw   = _innate_model.anomaly_score(obs)
        delta = max(raw - _innate_baseline, 0.0)
        # Amplify delta; add a small floor so score is never 0 even when clean
        AMPLIFICATION = 30.0
        CLEAN_FLOOR   = 0.08
        score = CLEAN_FLOOR + delta * AMPLIFICATION
        return round(min(max(score, 0.0), 1.0), 3)
    # Heuristic fallback (no model available)
    return _score_heuristic(cpu, procs_norm, compromised, state)


def _score_heuristic(cpu: float, sess: float, proc: float, comp: float, state: str) -> float:
    base = 0.3 * cpu + 0.2 * sess + 0.2 * proc + 0.3 * comp
    if state in ("INFECTED", "ISOLATING", "CONTAINED"):
        base = min(base + 0.40, 1.0)
    return round(max(0.0, min(base, 1.0)), 3)

ANOMALY_THRESHOLD    = 0.65
INFECTED_DWELL_SECS  = 5      # stay INFECTED for at least this long before isolating

# ---------------------------------------------------------------------------
# Global state (protected by asyncio — only mutated on the event loop)
# ---------------------------------------------------------------------------

_demo_state: str         = "CLEAN"
_dashboard_clients: set  = set()
_virus_ws                = None
_virus_worker_pids: list = []
_event_loop              = None   # set in main() so threads can post to it
_infected_at: float      = 0.0   # monotonic timestamp when INFECTED state was entered
_detection_secs: float   = 0.0   # how long it took to detect (CLEAN→ISOLATING)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_state() -> str:
    return _demo_state


async def _set_state(new_state: str):
    global _demo_state, _infected_at, _detection_secs
    import time as _time
    if new_state == "INFECTED":
        _infected_at = _time.monotonic()
    elif new_state == "ISOLATING" and _infected_at:
        _detection_secs = round(_time.monotonic() - _infected_at, 1)
    _demo_state = new_state
    print(f"[soma] State → {new_state}")
    await _broadcast({"type": "state_change", "state": new_state,
                      "detection_secs": _detection_secs if new_state == "ISOLATING" else 0})


async def _broadcast(msg: dict):
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
    """Schedule a coroutine on the main event loop from any thread."""
    if _event_loop and not _event_loop.is_closed():
        asyncio.run_coroutine_threadsafe(coro, _event_loop)


# ---------------------------------------------------------------------------
# Gmail IMAP polling (background thread)
# ---------------------------------------------------------------------------

def _imap_poll_loop():
    if not GMAIL_USER or not GMAIL_PASS:
        print("[imap] GMAIL_USER/GMAIL_APP_PASSWORD not set — email polling disabled")
        return
    print(f"[imap] Polling {GMAIL_USER} for unseen emails every 2s")
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
                        print(f"[imap] New email — from: {sender}  subject: {subject}")
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
# psutil monitoring loop (asyncio task — 1-second interval)
# ---------------------------------------------------------------------------

async def _psutil_loop():
    print("[psutil] Monitoring loop started")
    _psutil_one_time_init()   # warm up cpu_percent
    await asyncio.sleep(0.5)

    while True:
        await asyncio.sleep(1)
        state = _get_state()

        # Real readings from victim machine
        cpu_raw  = psutil.cpu_percent(interval=None)   # 0-100
        procs    = len(psutil.pids())
        net_sent = psutil.net_io_counters().bytes_sent

        user0_cpu      = cpu_raw / 100
        user0_sessions = min(procs / 200, 1.0)
        user0_procs    = min(procs / 300, 1.0)

        user0_compromised = 1.0 if state in ("INFECTED", "ISOLATING", "CONTAINED") else 0.0

        nodes = []
        for i, name in enumerate(_HOST_NAMES):
            if name == "User0":
                cpu        = user0_cpu
                anom       = _compute_user0_anomaly(
                                 user0_cpu, user0_sessions,
                                 user0_compromised, state)
                real_procs = procs
            else:
                cpu        = max(0.0, min(random.gauss(0.04, 0.01), 1.0))
                anom       = max(0.0, random.gauss(0.04, 0.01))
                real_procs = int(max(0.0, min(random.gauss(0.05, 0.01), 1.0)) * 200)

            status = ("red" if anom > 0.75 else "yellow" if anom > 0.5 else "green")
            nodes.append({
                "id":            name,
                "cpu":           round(cpu, 3),
                "processes":     real_procs,
                "anomaly_score": round(anom, 3),
                "status":        status,
            })

        await _broadcast({"type": "node_metrics", "nodes": nodes})

        # Anomaly-triggered isolation — only after minimum dwell in INFECTED
        import time as _time
        if (state == "INFECTED"
                and nodes[0]["anomaly_score"] > ANOMALY_THRESHOLD
                and _infected_at > 0
                and _time.monotonic() - _infected_at >= INFECTED_DWELL_SECS):
            await _set_state("ISOLATING")
            asyncio.ensure_future(_isolate())


_HOST_NAMES = ["User0", "Enterprise0", "Op_Server0", "Contractor0", "External0", "DMZ_Server0"]


def _psutil_one_time_init():
    psutil.cpu_percent(interval=None)   # first call always returns 0.0


# ---------------------------------------------------------------------------
# Isolation: Docker honeypot + virus redirect
# ---------------------------------------------------------------------------

async def _isolate():
    global _virus_ws
    print("[soma] Spawning Docker honeypot (soma_honeypot_image → :8766)...")
    try:
        subprocess.Popen([
            "docker", "run", "-d", "--name", "soma_honeypot",
            "-p", "8766:8766",
            "soma_honeypot_image",
        ])
    except Exception as e:
        print(f"[soma] Docker error: {e}")

    await asyncio.sleep(2)  # let container start

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

async def _purge():
    global _virus_worker_pids
    print("[soma] Purging honeypot and workers...")
    # Docker cleanup (run in executor to avoid blocking)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _docker_cleanup)
    # Kill virus CPU workers
    for pid_str in _virus_worker_pids:
        try:
            os.kill(int(pid_str), signal.SIGTERM)
            print(f"[soma] Killed worker PID {pid_str}")
        except Exception:
            pass
    _virus_worker_pids = []
    await _set_state("PURGED")
    await _broadcast({"type": "purge_complete"})


def _docker_cleanup():
    subprocess.run(["docker", "stop", "soma_honeypot"], check=False, capture_output=True)
    subprocess.run(["docker", "rm",   "soma_honeypot"], check=False, capture_output=True)
    print("[soma] Docker container stopped and removed")


async def _reset_demo():
    global _demo_state, _infected_at, _detection_secs, _virus_ws, _virus_worker_pids
    print("[soma] Resetting demo → CLEAN")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _docker_cleanup)
    for pid_str in _virus_worker_pids:
        try:
            os.kill(int(pid_str), signal.SIGTERM)
        except Exception:
            pass
    _virus_worker_pids = []
    _infected_at       = 0.0
    _detection_secs    = 0.0
    _demo_state        = "CLEAN"
    await _broadcast({"type": "state_change",    "state": "CLEAN"})
    await _broadcast({"type": "demo_reset"})
    print("[soma] Demo reset complete")


# ---------------------------------------------------------------------------
# HTTP handler (intercepts requests before WebSocket upgrade)
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

    # /dashboard, /virus, /honeypot → proceed to WebSocket upgrade
    return None


# ---------------------------------------------------------------------------
# WebSocket handlers
# ---------------------------------------------------------------------------

async def _handle_client(websocket):
    global _virus_ws, _virus_worker_pids, _infected_at

    path = websocket.request.path

    # ── Dashboard ──────────────────────────────────────────────────────────
    if path == "/dashboard":
        _dashboard_clients.add(websocket)
        count = len(_dashboard_clients)
        print(f"[ws/dashboard] connected  ({count} clients)")
        try:
            # Send current state on connect
            await websocket.send(json.dumps({"type": "state_change", "state": _get_state()}))
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "purge":
                    await _purge()
                elif msg.get("type") == "set_infected":
                    # Manual shortcut: presenter marks as infected without email flow
                    if _get_state() in ("CLEAN", "EMAIL_RECEIVED"):
                        await _set_state("INFECTED")
                elif msg.get("type") == "reset":
                    # Reset demo back to CLEAN (presenter control)
                    await _reset_demo()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            _dashboard_clients.discard(websocket)
            print(f"[ws/dashboard] disconnected  ({len(_dashboard_clients)} clients)")

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
                # virus_telemetry is noted but we use psutil for User0 readings
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if _virus_ws is websocket:
                _virus_ws = None
            print("[ws/virus] Backdoor disconnected")

    # ── Honeypot (Docker container reports here via WebSocket) ─────────────
    elif path == "/honeypot":
        print("[ws/honeypot] Docker container connected")
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "honeypot_telemetry":
                    await _broadcast({
                        "type":    "honeypot_active",
                        "port":    8766,
                        "metrics": {
                            "cpu":            msg.get("cpu", 0),
                            "processes":      msg.get("processes", 0),
                            "exfil_attempts": msg.get("exfil_attempts", 0),
                            "lan_scans":      msg.get("lan_scans", 0),
                        },
                    })
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            print("[ws/honeypot] Docker container disconnected")

    else:
        await websocket.close(1008, "Unknown path")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    print(f"[soma] Starting on port {PORT}")
    if not GMAIL_USER:
        print("[soma] WARNING: GMAIL_USER not set — email trigger disabled")
        print("[soma]          Presenter can use set_infected message from dashboard to manually trigger")

    # Gmail polling background thread
    t = threading.Thread(target=_imap_poll_loop, daemon=True)
    t.start()

    # psutil monitoring asyncio task
    asyncio.ensure_future(_psutil_loop())

    async with websockets.serve(
        _handle_client,
        "0.0.0.0",
        PORT,
        process_request=_process_request,
    ):
        print(f"[soma] Ready")
        print(f"[soma]   GET  http://0.0.0.0:{PORT}/download/virus.command")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/dashboard")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/virus")
        print(f"[soma]   WS   ws://0.0.0.0:{PORT}/honeypot")
        await asyncio.Future()


if __name__ == "__main__":
    _load_innate_model()   # calibrates Mac baseline before event loop starts
    asyncio.run(main())
