# SOMA Demo — Task List

## ✅ All Tasks Complete

| Task | Notes |
|------|-------|
| Rewrite `ws_server.py` with rolling z-score detection | No fake flags, `/agent/{NODE_NAME}` WS path, multi-signal scorer (CPU 40% + net 40% + TCP 20%), baseline frozen during attack |
| Create `soma_agent.py` (real `/proc` Docker agent) | Reads `/proc/stat`, `/proc/meminfo`, `/proc/net/dev`, `/proc/net/tcp` every 1s, diffs TCP connections |
| Build all Dockerfiles, entrypoints, configs | `Dockerfile.{node,enterprise0,enterprise1,op_server0,honeypot}`, all entrypoints, `sshd_config`, nginx confs, `vsftpd.conf` |
| SSH key pair baked into all images | `configs/soma_id_rsa` — enables real key-based cross-container SSH lateral movement |
| Create `docker-compose.yml` (soma-net `172.22.0.0/24`) | 4-node network, SSH port mappings (2220–2223), honeypot spawned dynamically |
| Update `virus.command` — 5 heavy CPU workers + real SSH lateral movement | No sleep workers, `docker inspect` for real container IPs, SSH via key auth, `SOMA_WORKER` tag for cleanup |
| Remove all `fake_data/` theatrical files | No simulated employees, payroll, credentials, or redis seed data |
| Rewrite `useWebSocket.js` — new message router | Handles `lateral_movement`, `honeypot_active`, `purge_complete`, `demo_reset` |
| Add lateral movement panel to `App.jsx` | Shows real SSH lateral movement events as they arrive with source/dest IPs |
| Integrate `LiveNetworkGraph.jsx` into `App.jsx` | Imported on App.jsx:4, rendered at App.jsx:395 with `nodes`, `somaState`, `honeypotMetrics` props |
| Rebuild all Docker images and verify end-to-end | All 4 agents connect, real `/proc` metrics flowing, clean anomaly score ~0.08 |
| Fix `virus.command` asyncio.gather bug | Replaced `asyncio.gather` with `create_task` + `cancel` — redirect now fires correctly |
| Fix `ws_server.py` async API deprecations | `ensure_future` → `create_task`; `get_event_loop()` → `get_running_loop()` |
| Fix `_reset_demo()` not clearing `_virus_ws` | Added `_virus_ws = None` so stale connection is dropped on reset |
| Fix purge — kill SSH-spawned workers inside all containers | `_kill_container_workers()` runs `pkill -f python3` in all 4 containers including `soma-user0`; host workers killed via `pkill -f SOMA_WORKER` |
| Implement malware migration to honeypot container | `honeypot_server.py` spawns 5 real CPU workers inside Docker on `virus_connect`; `virus.command` kills local workers on redirect; `Dockerfile.honeypot` adds `psutil` |
| Verify honeypot panel during CONTAINED state | Confirmed: container workers spawn at 100% CPU (`cpu=1.00`), telemetry flows to dashboard via `honeypot_telemetry` messages |
| Full end-to-end demo run verified | CLEAN → INFECTED → ISOLATING → CONTAINED (container CPU 100%) → PURGED (host CPU back to baseline, 0 SOMA_WORKER procs, honeypot container destroyed) |

---

## Demo Runbook

```bash
# 1. Start backend
GMAIL_USER=soma.demo.inbox@gmail.com \
GMAIL_APP_PASSWORD="avgn irfi busu ctvg" \
python3 backend/ws_server.py

# 2. Start nodes
docker-compose up -d soma-user0 soma-enterprise0 soma-enterprise1 soma-op-server0

# 3. Start frontend
cd frontend && npm start

# 4. Send phishing email to soma.demo.inbox@gmail.com
#    → dashboard shows EMAIL_RECEIVED banner with Download button

# 5. Click Download → double-click virus.command in Terminal

# 6. Watch: INFECTED → ISOLATING → CONTAINED (honeypot panel appears)

# 7. Click Purge & Destroy → PURGED
```

**Backup trigger** (if email is slow): send `{"type":"set_infected"}` via dashboard WS:
```bash
python3 -c "import asyncio,json,websockets; asyncio.run((lambda: websockets.connect('ws://localhost:8765/dashboard')).__call__())"
# or open browser console on dashboard and send manually
```
