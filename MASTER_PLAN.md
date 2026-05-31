# SOMA Live Demo — Master Plan

## What We're Building

A live, end-to-end security demo:
1. Attacker sends a **real email** to the demo Gmail inbox
2. SOMA detects it, dashboard shows a notification with a download button
3. Victim clicks download → `virus.command` lands in Downloads → double-click → Terminal opens
4. Terminal prints theatrical hacking output; script spawns **real CPU worker subprocesses** (visible in Activity Monitor)
5. SOMA reads **real psutil data** (CPU%, process count) from the victim machine → anomaly score crosses threshold → dashboard turns red
6. SOMA spins up a **Docker honeypot container** and sends a redirect command to the malware
7. Malware silently switches from port 8765 → 8766 (Docker container), believing it's still connected to C2
8. Dashboard: User0 goes back to green; new "Honeypot" panel appears showing captured malicious activity
9. Presenter clicks "Purge & Destroy" → Docker container killed, CPU workers killed, all clear

---

## Architecture

```
Victim's MacBook (everything local)
├── SOMA Backend          ws_server.py      :8765  WebSocket + HTTP
├── React Dashboard       npm run dev       :3000
├── Docker Honeypot       soma_honeypot     :8766  (spun up mid-demo)
└── Terminal (virus)      virus.command     ← runs in macOS Terminal
         │
         ├─ 3× Python CPU-worker subprocesses (real, visible in Activity Monitor)
         └─ WebSocket backdoor → :8765 (then redirected to :8766)
```

**Node mapping:**
- `User0` = victim's real machine (live psutil readings)
- `Enterprise0`, `Op_Server0`, `Contractor0`, `External0`, `DMZ_Server0` = simulated idle values

---

## State Machine

```
CLEAN → EMAIL_RECEIVED → INFECTED → ISOLATING → CONTAINED → PURGED
```

Each transition broadcasts `{"type": "state_change", "state": "..."}` to all dashboard WebSocket clients.

---

## File-by-File Plan

---

### File 1: `backend/ws_server.py` — complete rewrite

Replace the existing episode-streaming server with a real-time, multi-purpose server.

**Single port 8765 serves both HTTP and WebSocket.**
Use `websockets.serve(process_request=http_handler)` to handle HTTP on the same port.

#### HTTP routes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/download/virus.command` | Serve the virus script as a file download |
| POST | `/honeypot-report` | Docker container POSTs malware telemetry here |
| GET | `/` | Health check |

#### WebSocket paths

| Path | Client | Purpose |
|------|--------|---------|
| `/dashboard` | React frontend | Receives all broadcast messages |
| `/virus` | virus.command | Bidirectional: receives redirect, sends telemetry |

#### Background threads/tasks

**Gmail IMAP polling** (runs every 2 seconds, background thread):
```python
import imaplib, email as emaillib, os

GMAIL_USER = os.environ["GMAIL_USER"]           # soma.demo.inbox@gmail.com
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]   # 16-char Google app password

# Connect with IMAP SSL, select INBOX, search UNSEEN, parse first match,
# mark as read, transition state → EMAIL_RECEIVED, broadcast email_notification
```

**psutil monitoring loop** (asyncio task, 1-second interval):
```python
import psutil

# Real readings for User0:
cpu    = psutil.cpu_percent(interval=None)        # 0–100
procs  = len(psutil.pids())                       # integer
net    = psutil.net_io_counters().bytes_sent      # bytes

# Normalise to 0–1 for SOMA layers:
activity = cpu / 100
sessions  = min(procs / 200, 1.0)
processes = min(procs / 300, 1.0)

# Simulated values for other 5 nodes: random.gauss(0.05, 0.01) clamped to [0,1]

# Assemble 30-dim vector (6 hosts × 5 features), run InnateImmunityLayer
# Broadcast node_metrics to dashboard clients every second
```

**Anomaly detection** (inside psutil loop):
- If `User0` anomaly score > 0.65 AND state == `INFECTED`:
  - Transition → `ISOLATING`
  - Spawn Docker honeypot (see below)
  - Send `{"type": "redirect", "port": 8766}` to connected virus WebSocket client

**Docker management**:
```python
import subprocess

def spawn_honeypot():
    subprocess.Popen([
        "docker", "run", "-d", "--name", "soma_honeypot",
        "-p", "8766:8766",
        "--add-host=host.docker.internal:host-gateway",
        "soma_honeypot_image"
    ])

def purge_honeypot(virus_pids: list[int]):
    subprocess.run(["docker", "stop", "soma_honeypot"], check=False)
    subprocess.run(["docker", "rm",   "soma_honeypot"], check=False)
    for pid in virus_pids:
        try: os.kill(pid, signal.SIGTERM)
        except ProcessLookupError: pass
```

**Purge handler**: triggered by `{"type": "purge"}` from dashboard WebSocket → calls `purge_honeypot`, transitions → `PURGED`, broadcasts `purge_complete`.

#### Broadcast messages (server → dashboard)

```jsonc
// On email arrival
{"type": "email_notification", "from": "attacker@protonmail.com",
 "subject": "SOMA Security Update — Patch Required", "has_attachment": true}

// Every 1 second during demo
{"type": "node_metrics", "nodes": [
  {"id": "User0", "cpu": 0.42, "processes": 37, "anomaly_score": 0.91, "status": "red"},
  {"id": "Enterprise0", "cpu": 0.04, "processes": 12, "anomaly_score": 0.03, "status": "green"},
  ...
]}

// State transitions
{"type": "state_change", "state": "EMAIL_RECEIVED"}
{"type": "state_change", "state": "INFECTED"}
{"type": "state_change", "state": "ISOLATING"}
{"type": "state_change", "state": "CONTAINED"}
{"type": "purge_complete"}

// When Docker container starts reporting in
{"type": "honeypot_active", "port": 8766, "metrics": {
  "cpu": 0.38, "processes": 35, "exfil_attempts": 3, "lan_scans": 2
}}
```

---

### File 2: `backend/virus.command` — the malware executable

Executable shell script (`chmod +x`). macOS opens `.command` files in Terminal on double-click.

```bash
#!/bin/bash
# --- theatrical output ---
echo "[SOMA_PAYLOAD v2.1] Initializing attack sequence..."
sleep 0.5
echo "Establishing C2 connection to 185.234.219.43:4444..."
sleep 0.8
echo "Connection established. ✓"
echo ""
echo "[*] Fingerprinting system..."
echo "    OS: macOS Darwin"
echo "    CPU cores: $(sysctl -n hw.ncpu)  |  RAM: $(( $(sysctl -n hw.memsize) / 1073741824 ))GB"
echo "    Current user: $(whoami)"
echo ""
echo "[*] Spawning stealth worker processes..."

# --- spawn 3 real CPU workers (light load: ~2-3% each) ---
python3 -c "
import time, math
while True:
    _ = sum(math.sqrt(i) for i in range(30000))
    time.sleep(0.05)
" &
PID1=$!

python3 -c "
import time, math
while True:
    _ = [i**2 for i in range(20000)]
    time.sleep(0.05)
" &
PID2=$!

python3 -c "
import time, math
while True:
    _ = sorted(range(15000), reverse=True)
    time.sleep(0.05)
" &
PID3=$!

echo "    [pid: $PID1] worker-1 ✓"
echo "    [pid: $PID2] worker-2 ✓"
echo "    [pid: $PID3] worker-3 ✓"
echo ""
echo "[*] Initiating CPU stress (stealth mode)..."
echo "[*] Scanning for exfiltration targets..."
echo "    /Users/$(whoami)/Documents/  → queued"
echo "    /Users/$(whoami)/Desktop/    → queued"
echo ""
echo "[*] Scanning LAN for lateral movement targets..."
sleep 0.5
echo "    Found: 10.0.0.1  (router)"
echo "    Found: 10.0.0.5  (Enterprise0)"
echo "    Found: 10.0.0.8  (Op_Server0)"
echo ""
echo "[*] Backdoor active — awaiting C2 commands..."

# --- Python WebSocket backdoor (inline) ---
python3 - "$PID1" "$PID2" "$PID3" << 'PYEOF'
import sys, asyncio, json, os

PIDS = sys.argv[1:]

async def run():
    import websockets
    uri = "ws://localhost:8765/virus"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({
                    "type": "virus_connect",
                    "pid": os.getpid(),
                    "cpu_workers": PIDS
                }))

                async def send_telemetry():
                    import psutil
                    while True:
                        await ws.send(json.dumps({
                            "type": "virus_telemetry",
                            "cpu": psutil.cpu_percent(interval=None) / 100,
                            "processes": len(psutil.pids())
                        }))
                        await asyncio.sleep(2)

                async def recv_commands():
                    nonlocal uri
                    async for msg in ws:
                        data = json.loads(msg)
                        if data.get("type") == "redirect":
                            new_port = data["port"]
                            print(f"\n>>> COMMAND RECEIVED: redirect → decoy environment")
                            print(f">>> Switching to port {new_port}...")
                            print("[*] Now operating in isolated environment (undetected)")
                            uri = f"ws://localhost:{new_port}/virus"
                            return  # exit to reconnect on new port

                await asyncio.gather(send_telemetry(), recv_commands())
        except Exception:
            await asyncio.sleep(2)

asyncio.run(run())
PYEOF
```

**Key property:** The 3 `python3` worker processes will be visible in Activity Monitor under the process names `Python` or `python3`, with mild but visible CPU spikes. Each does computation + `sleep(0.05)` to keep load at ~2-4% per process, totalling ~6-12% CPU spike on the victim machine.

---

### File 3: `backend/honeypot_server.py` — runs inside Docker container

```python
import asyncio, json, os, aiohttp, websockets

SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = 8765

async def handler(ws):
    print("[honeypot] Malware connected")
    exfil_attempts = 0
    lan_scans = 0

    async for msg in ws:
        data = json.loads(msg)
        if data.get("type") == "virus_telemetry":
            exfil_attempts += 1
            async with aiohttp.ClientSession() as s:
                await s.post(f"http://{SOMA_HOST}:{SOMA_PORT}/honeypot-report",
                             json={"cpu": data["cpu"], "processes": data["processes"],
                                   "exfil_attempts": exfil_attempts, "lan_scans": lan_scans})
        # Send fake ack so malware thinks C2 is alive
        await ws.send(json.dumps({"type": "ack", "status": "ok"}))

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8766):
        print("[honeypot] Listening on :8766")
        await asyncio.Future()

asyncio.run(main())
```

---

### File 4: `backend/Dockerfile.honeypot`

```dockerfile
FROM python:3.11-slim
RUN pip install --no-cache-dir websockets aiohttp
WORKDIR /app
COPY honeypot_server.py .
CMD ["python", "honeypot_server.py"]
```

**One-time build** (run before demo day):
```bash
cd backend
docker build -t soma_honeypot_image -f Dockerfile.honeypot .
```

---

### File 5: `frontend/src/hooks/useWebSocket.js` — rewrite for new message types

Replace episode-streaming logic with live-state hook.

**State exposed to `App.jsx`:**
```javascript
{
  connected,          // bool
  somaState,          // "CLEAN"|"EMAIL_RECEIVED"|"INFECTED"|"ISOLATING"|"CONTAINED"|"PURGED"
  emailNotification,  // null | {from, subject}
  nodes,              // array of 6 {id, cpu, processes, anomaly_score, status}
  honeypotMetrics,    // null | {cpu, processes, exfil_attempts, lan_scans}
  sendMessage,        // (obj) => void  — used for purge
}
```

**Message routing:**
```javascript
switch (msg.type) {
  case "email_notification": setEmailNotification(msg); break;
  case "node_metrics":       setNodes(msg.nodes); break;
  case "state_change":       setSomaState(msg.state); break;
  case "honeypot_active":    setHoneypotMetrics(msg.metrics); break;
  case "purge_complete":     setHoneypotMetrics(null); setSomaState("PURGED"); break;
}
```

WebSocket connects to `ws://localhost:8765/dashboard`.

---

### File 6: `frontend/src/App.jsx` — new panels

Replace episode-replay UI with live-demo UI. Keep the existing node grid layout but power it from live `nodes` data.

#### A. Email notification banner

Shown when `emailNotification !== null`. Appears at top of main content area.

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠  NEW EMAIL   From: attacker@protonmail.com               │
│     Subject: SOMA Security Update — Patch Required          │
│     Attachment: soma_security_patch.command                 │
│                                          [Download File]    │
└─────────────────────────────────────────────────────────────┘
```

"Download File" → `window.location.href = "http://localhost:8765/download/virus.command"`.
After click → set `emailNotification` to null (banner disappears), sets local state `downloaded = true`.

#### B. Node cards — powered by live `nodes` array

Each node card (User0 through DMZ_Server0) shows:
- CPU bar (0–100%)
- Process count
- Anomaly score gauge (0.0–1.0)
- Border colour: green (score < 0.5), yellow (0.5–0.75), red (> 0.75)
- User0 pulses red and shows tooltip when `somaState === "INFECTED"`:
  `"CPU spike detected | Processes: +N | Anomaly score: 0.91 | Unexpected outbound connection"`

#### C. SOMA status bar

```
SOMA IMMUNE SYSTEM  ●  State: ISOLATING  |  Threat detected in 3.1s
```

State colour: green = CLEAN/PURGED, yellow = EMAIL_RECEIVED, red = INFECTED/ISOLATING/CONTAINED.

#### D. Honeypot panel

Shown when `honeypotMetrics !== null` (i.e. after `honeypot_active` message). Rendered below node grid.

```
┌────────────────────────────────────────────┐
│  HONEYPOT ACTIVE  :8766                    │
│  ┌──────────────────────────────────────┐  │
│  │  Malware captured in Docker sandbox  │  │
│  │  CPU telemetry:      38%             │  │
│  │  Process count:      35              │  │
│  │  Exfil attempts:     3               │  │
│  │  LAN scan attempts:  2               │  │
│  └──────────────────────────────────────┘  │
│                    [Purge & Destroy]        │
└────────────────────────────────────────────┘
```

"Purge & Destroy" → `sendMessage({type: "purge"})`.

---

## Demo Day Setup

```bash
# 1. Set credentials
export GMAIL_USER="soma.demo.inbox@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"   # Google App Password

# 2. Build Docker image (one-time, ~30 seconds)
cd backend
docker build -t soma_honeypot_image -f Dockerfile.honeypot .

# 3. Start SOMA backend
python ws_server.py

# 4. Start frontend (separate terminal)
cd frontend && npm run dev

# 5. Open http://localhost:3000 on projector
```

**Attacker script:** Send any email (from any address) to `soma.demo.inbox@gmail.com`.
No real attachment needed — the backend serves `virus.command` when the dashboard button is clicked.

---

## Dependencies

**Backend (pip):** `websockets`, `psutil`, `aiohttp`, `scikit-learn` (for SOMA layers)
**System:** Docker Desktop installed and running on demo MacBook
**Gmail:** 2FA enabled, App Password generated
**Frontend:** no new npm packages

---

## Implementation Order

1. `backend/honeypot_server.py` + `Dockerfile.honeypot` — standalone, test first
2. `backend/virus.command` — test CPU spike in Activity Monitor independently
3. `backend/ws_server.py` — IMAP thread, psutil loop, HTTP routes, WebSocket routing, state machine, Docker management
4. `frontend/src/hooks/useWebSocket.js` — new message router
5. `frontend/src/App.jsx` — email banner, live node cards, status bar, honeypot panel
6. End-to-end: send email → download → run virus → watch dashboard → purge
