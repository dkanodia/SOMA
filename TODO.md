# SOMA Demo — Task List

## ✅ Completed

| Task | Notes |
|------|-------|
| Rewrite `ws_server.py` with rolling z-score detection | No fake flags, `/agent/{NODE_NAME}` WS path, multi-signal scorer (CPU 40% + net 40% + TCP 20%), baseline frozen during attack |
| Create `soma_agent.py` (real `/proc` Docker agent) | Reads `/proc/stat`, `/proc/meminfo`, `/proc/net/dev`, `/proc/net/tcp` every 1s, diffs TCP connections |
| Build all Dockerfiles, entrypoints, configs | `Dockerfile.{node,enterprise0,enterprise1,op_server0,honeypot}`, all entrypoints, `sshd_config`, nginx confs, `vsftpd.conf` |
| SSH key pair baked into all images | `configs/soma_id_rsa` — enables real key-based cross-container SSH lateral movement |
| Create `docker-compose.yml` (soma-net `172.22.0.0/24`) | 4-node network, SSH port mappings (2220–2223), honeypot spawned dynamically |
| Update `virus.command` — 5 heavy CPU workers + real SSH lateral movement | No sleep workers (~65% load), `docker inspect` for real container IPs, SSH via key auth |
| Remove all `fake_data/` theatrical files | No simulated employees, payroll, credentials, or redis seed data |
| Rewrite `useWebSocket.js` — new message router | Handles `lateral_movement`, `honeypot_active`, `purge_complete`, `demo_reset` |
| Add lateral movement panel to `App.jsx` | Shows real SSH lateral movement events as they arrive with source/dest IPs |
| Rebuild all Docker images and verify end-to-end | All 4 agents connect, real `/proc` metrics flowing, clean anomaly score = 0.080 |

---

## 🔴 To Do

### High Priority

#### Fix `virus.command` asyncio.gather bug — redirect never fires
**File:** `backend/virus.command` (Python backdoor section)

**Problem:** The current code uses:
```python
_, redirect_port = await asyncio.gather(send_telemetry(), recv_commands())
```
`send_telemetry()` is an infinite loop. `asyncio.gather` waits for **all** coroutines to finish, so even when `recv_commands()` receives the `{"type":"redirect"}` message and returns, the gather never resolves — the virus never switches to port 8766.

**Fix:**
```python
telemetry_task = asyncio.create_task(send_telemetry())
redirect_port = await recv_commands()
telemetry_task.cancel()
# reconnect to ws://localhost:{redirect_port}/virus
```

---

#### Integrate `LiveNetworkGraph.jsx` into `App.jsx`
**File:** `frontend/src/App.jsx`

`LiveNetworkGraph.jsx` exists in `frontend/src/components/` but is never imported or rendered. It needs to:
- Be imported at the top of `App.jsx`
- Receive props: `nodes`, `somaState`, `lateralMovements`
- Be placed in the `live-demo-body` section (above or below the node grid)
- Animate edges during lateral movement events
- Expand to show honeypot decoy zone during `ISOLATING` / `CONTAINED` states

---

### Medium Priority

#### Fix purge — kill SSH-spawned workers inside containers
**File:** `backend/ws_server.py` → `_purge()`

`_purge()` kills virus.command's local CPU worker PIDs but does **not** kill the `python3` workers spawned inside containers via SSH lateral movement.

**Fix:** On purge, for each container in `_HOST_NAMES[1:]`, run:
```python
subprocess.run(["docker", "exec", name_to_container(n), "pkill", "-f", "python3"], ...)
```
Or broadcast a `purge` command via the agent WS and have containers self-clean.

---

#### Verify honeypot panel appears during CONTAINED state
**Files:** `backend/honeypot_server.py`, `frontend/src/components/HoneypotPanel.jsx`

`honeypot_server.py` runs inside the Docker honeypot and forwards virus telemetry to `ws://host.docker.internal:8765/honeypot`. `ws_server.py` receives it and broadcasts `honeypot_active`. 

Needs a live run to confirm: honeypot container starts → soma_agent connects → `honeypot_active` appears on dashboard → `HoneypotPanel` renders with real container metrics.

---

### Must-Do Before Demo

#### Full end-to-end demo run (email → PURGED)
Complete walkthrough of every state transition:

1. Start backend: `GMAIL_USER=... GMAIL_APP_PASSWORD=... python3 backend/ws_server.py`
2. Start nodes: `docker-compose up -d soma-user0 soma-enterprise0 soma-enterprise1 soma-op-server0`
3. Start frontend: `cd frontend && npm start`
4. Send email to `soma.demo.inbox@gmail.com` → dashboard shows **EMAIL_RECEIVED** banner
5. Click Download → `virus.command` saved → double-click → Terminal opens
6. Watch CPU spike in Activity Monitor → dashboard turns red → **INFECTED**
7. Anomaly score crosses 0.65 → **ISOLATING** → Docker honeypot spawns
8. Virus terminal shows `>>> COMMAND: redirect → :8766`
9. Dashboard shows **CONTAINED** + honeypot panel with real metrics
10. Click **Purge & Destroy** → Docker stopped, workers killed → **PURGED**
