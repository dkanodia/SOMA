#!/usr/bin/env python3
"""
SOMA node agent — runs inside each Docker container.
Reads real /proc data every second and reports to the SOMA backend:
  ws://{SOMA_HOST}:{SOMA_PORT}/agent/{NODE_NAME}

Message format (type=agent_metrics):
  cpu_pct          float   user+system % from /proc/stat
  mem_pct          float   used % from /proc/meminfo
  proc_count       int     processes visible in /proc
  proc_list        list    [{pid, name}] top 15 by pid
  net_bytes_out    int     bytes sent on eth0 since last tick
  net_bytes_in     int     bytes received on eth0 since last tick
  tcp_conn_count   int     established TCP connections
  new_connections  list    [{src_ip, src_port, dst_ip, dst_port}] new this tick
"""

import asyncio
import json
import os
import socket
import time

NODE_NAME = os.environ.get("NODE_NAME", "Unknown")
SOMA_HOST = os.environ.get("SOMA_HOST", "host.docker.internal")
SOMA_PORT = int(os.environ.get("SOMA_PORT", 8765))
WS_URI    = f"ws://{SOMA_HOST}:{SOMA_PORT}/agent/{NODE_NAME}"
IFACE     = "eth0"

# ---------------------------------------------------------------------------
# /proc/stat — CPU
# ---------------------------------------------------------------------------

_prev_busy:  int = 0
_prev_total: int = 1


def _cpu_pct() -> float:
    global _prev_busy, _prev_total
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
        # user nice system idle iowait irq softirq
        vals   = list(map(int, parts[1:8]))
        user, nice, system, idle, iowait, irq, softirq = vals
        busy   = user + nice + system + irq + softirq
        total  = busy + idle + iowait
        db     = busy  - _prev_busy
        dt     = total - _prev_total
        _prev_busy, _prev_total = busy, total
        return round(db / dt * 100, 2) if dt > 0 else 0.0
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# /proc/meminfo — memory
# ---------------------------------------------------------------------------

def _mem_pct() -> float:
    try:
        vals: dict = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                vals[k.strip()] = int(v.strip().split()[0])
        total = vals.get("MemTotal", 1)
        avail = vals.get("MemAvailable", total)
        return round((total - avail) / total * 100, 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# /proc — process list
# ---------------------------------------------------------------------------

def _proc_list() -> list:
    procs = []
    try:
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                with open(f"/proc/{pid}/comm") as f:
                    name = f.read().strip()
                procs.append({"pid": int(pid), "name": name})
            except OSError:
                pass
    except Exception:
        pass
    return procs


# ---------------------------------------------------------------------------
# /proc/net/dev — network I/O delta
# ---------------------------------------------------------------------------

_prev_bytes_out: int = 0
_prev_bytes_in:  int = 0


def _net_delta() -> tuple:
    """Returns (bytes_out_delta, bytes_in_delta) since last call."""
    global _prev_bytes_out, _prev_bytes_in
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                if IFACE not in line:
                    continue
                # Format: iface: rx_bytes rx_pkts ... tx_bytes tx_pkts ...
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


# ---------------------------------------------------------------------------
# /proc/net/tcp — TCP connections
# ---------------------------------------------------------------------------

def _parse_addr(hex_str: str) -> tuple:
    ip_hex, port_hex = hex_str.split(":")
    ip   = socket.inet_ntoa(bytes.fromhex(ip_hex)[::-1])
    port = int(port_hex, 16)
    return ip, port


def _tcp_conns() -> list:
    """Return list of (src_ip, src_port, dst_ip, dst_port) for ESTABLISHED conns."""
    conns = []
    try:
        with open("/proc/net/tcp") as f:
            lines = f.readlines()[1:]   # skip header row
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or parts[3] != "01":   # 01 = ESTABLISHED
                continue
            try:
                src_ip, src_port = _parse_addr(parts[1])
                dst_ip, dst_port = _parse_addr(parts[2])
                conns.append((src_ip, src_port, dst_ip, dst_port))
            except Exception:
                pass
    except Exception:
        pass
    return conns


_prev_conn_set: set = set()


def _diff_connections(current: list) -> list:
    """Return connections that weren't present last tick."""
    global _prev_conn_set
    cur_set  = set(current)
    new_raw  = cur_set - _prev_conn_set
    _prev_conn_set = cur_set
    return [
        {"src_ip": s, "src_port": sp, "dst_ip": d, "dst_port": dp}
        for s, sp, d, dp in new_raw
    ]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run():
    import websockets

    print(f"[agent:{NODE_NAME}] target={WS_URI}")

    # Warm-up: first /proc/stat and net reads always return 0
    _cpu_pct()
    _net_delta()
    _tcp_conns()
    await asyncio.sleep(1)

    while True:
        try:
            async with websockets.connect(WS_URI, ping_interval=10, open_timeout=10) as ws:
                print(f"[agent:{NODE_NAME}] connected")
                while True:
                    cpu   = _cpu_pct()
                    mem   = _mem_pct()
                    procs = _proc_list()
                    out_b, in_b = _net_delta()
                    conns = _tcp_conns()
                    new_c = _diff_connections(conns)

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
            print(f"[agent:{NODE_NAME}] disconnected ({e}), retry in 3s")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(run())
