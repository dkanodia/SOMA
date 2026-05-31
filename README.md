# SOMA — Signaling-Optimal Memory Architecture

Autonomous cyber defense using reinforcement learning and signaling game theory. Research prototype — not an operational product.

---

## What SOMA Is

SOMA is a research prototype demonstrating that RL agents can learn game-theoretically optimal deception policies in a cyber defense setting. It is built around the observation that biological immune systems operate across multiple timescales — fast non-specific innate responses, slower adaptive learned responses, and long-term memory — and asks whether the same layered architecture can improve autonomous network defense.

The system implements four detection layers that operate in parallel across different timescales: a fast unsupervised anomaly detector (Innate), a reinforcement-learned tactical defender (Adaptive), a game-theoretic deception mechanism that learns to optimally mix real and honeypot signals (Deception), and a long-dwell behavioral drift alarm (Memory). Responses are fused by a rule-based orchestrator and visualized in a live Security Operations Center (SOC) dashboard.

**Transfer to real networks is an open research problem and is not claimed.** All training and evaluation is conducted in simulation against a scripted, deterministic attacker (B_lineAgent from CybORG CAGE 2).

---

## Live Demo Overview

The frontend is a real-time SOC dashboard built with React 18 and D3. It visualizes a live or replayed attack scenario as it unfolds across a simulated enterprise network.

**What you see:**
- **Network graph** — D3 force-directed topology of all hosts (User0, Enterprise0/1, Op_Server0) and a decoy honeypot zone that appears when deception activates
- **Host cards** — per-node CPU %, process count, and anomaly score, color-coded green/yellow/red
- **Lateral movement log** — real-time source → destination connections as the attack spreads
- **Honeypot panel** — CPU, process count, and C2 connections inside the active honeypot container
- **Incident log** — cumulative events with severity labels (critical / high / info)
- **Assets view** — tabular summary of all hosts with current metrics

**State machine** (the user watches this progression):

```
CLEAN → EMAIL_RECEIVED → INFECTED → ISOLATING → CONTAINED → PURGED
```

**Offline replay:** If the backend is unreachable, the frontend falls back automatically after 3 connection retries to a static episode replay (`frontend/build/demo_episode.json`) at 7 FPS. No server needed.

---

## Architecture

```
  soma-net Docker bridge (172.22.0.0/24)
  ┌─────────────────────────────────────────────┐
  │  [Enterprise0]  [Enterprise1]  [Op_Server0] │
  │  soma_agent.py  soma_agent.py  soma_agent.py │
  └────────────────────┬────────────────────────┘
                       │ WS /agent/{NODE}  (metrics every 1s)
                       ▼
  [virus.command] ──── WS /virus
  [Honeypot container] WS /honeypot          ┌─────────────────────┐
                       │                     │  soma Python library │
                       ▼                     │  ├── layers/         │
              ┌─────────────────┐            │  ├── envs/           │
              │  ws_server.py   │◀──────────▶│  ├── theory/         │
              │    :8765        │            │  ├── fusion/         │
              └────────┬────────┘            │  └── eval/           │
                       │ WS /dashboard       └─────────────────────┘
                       ▼
              ┌─────────────────┐
              │  React Frontend │
              │    :3000        │
              └─────────────────┘
```

| Component | Role |
|---|---|
| `backend/ws_server.py` | WebSocket server + state machine + Docker honeypot orchestration |
| `backend/soma_agent.py` | Runs in each Docker node; streams psutil metrics to the server |
| `backend/honeypot_server.py` | Runs in the dynamically-spawned honeypot container |
| `soma/` | Core Python library: detection layers, environments, theory, fusion |
| `frontend/` | React + D3 SOC dashboard; connects to server via WebSocket |

---

## Four Detection Layers

| Layer | Method | Timescale | FPR Budget |
|---|---|---|---|
| **Innate** | Isolation Forest on host metrics (6 hosts × 5 features) | Per-step | 1% |
| **Adaptive** | PPO defender on CybORG CAGE 2 | Per-episode | 1% |
| **Deception** | Signaling game RL + heuristic honeypot trigger | Theoretical | n/a |
| **Long-Dwell** | PCA centroid drift detection on rolling baseline | 100-episode window | 0.1% |

**Innate (Layer 1):** Isolation Forest trained on clean episodes (no attack labels needed). Input is a 30-dimensional flat vector (6 hosts × CPU, memory, outbound bytes, process count, TCP connections). Threshold calibrated to 1% FPR on held-out validation data.

**Adaptive (Layer 2):** PPO agent (Stable Baselines3, 200K steps) trained on CybORG CAGE 2 against B_lineAgent. Action space: Discrete(54) — Monitor/Analyze/Remove/Restore for each host. Guards against reward hacking with a −2 penalty for repeated Analyze on clean hosts. Policy is **frozen at deployment** — "adaptive" refers to detecting adaptive attack moves, not online self-adaptation.

**Deception (Layer 3):** Two separate systems deliberately decoupled. *(i)* A signaling game RL policy trained on `SignalingGameEnv` (standalone 2-type Bayesian game) that learns optimal mixing rates (q\*, r\*) for hiding real assets and baiting honeypots — validated against closed-form PBE. *(ii)* A heuristic bridge to CybORG: if PPO suspicion score > 0.7, activate the honeypot. The game-theoretic policy is **not** applied to CybORG because B_lineAgent is scripted and does not respond to signals.

**Long-Dwell (Layer 4):** PCA centroid drift detection over a 100-episode rolling baseline. Calibrated to catch injected 2%/step behavioral drift at 0.1% FPR.

---

## Claims & Limitations

### What Is Claimed (with evidence)

- RL recovers PBE mixing rates across κ ∈ {0, V/2, V} — convergence plot is the evidence
- PPO detection rate: lateral movement ≥ 50%, impact stage ≥ 80%
- Isolation Forest benchmarked at 1% FPR on clean simulation data
- Drift alarm catches injected 2%/step behavioral drift at 0.1% FPR

### What Is NOT Claimed

- Transfer to real networks at any validated performance level
- Operational readiness
- Real adversary behavioral characterization
- Formal rational inattention (utility-cost approximation used — not Sims 2003 / Matějka & McKay 2015)
- Self-play convergence guarantees
- Evaluation on real endpoint data
- B_lineAgent responds to defender signals (it does not — it is scripted and deterministic)

---

## Requirements

**Python environment:**
- Python 3.10+
- PyTorch 2.x
- Stable Baselines3
- CybORG CAGE 2 (separate install — see below)

**Demo / network simulation:**
- Docker + docker-compose

**Frontend:**
- Node 18+

---

## Installation

### 1. Install CybORG (prerequisite)

```bash
git clone https://github.com/cage-challenge/cage-challenge-2
cd cage-challenge-2 && pip install -e . && cd ..
```

### 2. Install SOMA

```bash
pip install -e .
```

### 3. Verify the environment

```bash
python scripts/verify_env.py
```

---

## Training the Layers

Training runs sequentially and takes approximately 3.5 hours total on a GPU.

**Layer 1 — Innate (Isolation Forest, ~5 min):**
```bash
# Fetch DoD contract data from USASpending API (~10 min, ~2000 records)
python scripts/train_innate.py --records 2000

# Or skip the API fetch if data/layer1_features.csv already exists
python scripts/train_innate.py --skip-fetch
```

**Layer 2 — Adaptive (PPO, ~2 hours on GPU):**
```bash
python scripts/train_adaptive.py
```

**Layer 3 — Deception (signaling game RL + κ sweep, ~1.5 hours):**
```bash
python scripts/train_deception.py   # runs κ sweep internally
```

**Evaluation and FPR calibration:**
```bash
python scripts/evaluate.py
```

---

## Running the Live Demo

### Option A — Full Docker network simulation (recommended)

Builds four node containers on an isolated `soma-net` bridge (172.22.0.0/24). Each runs `soma_agent.py` to stream metrics to the WebSocket server.

```bash
# Copy and configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env as needed (see Environment Variables below)

# Build container images
docker-compose build

# Start network nodes
docker-compose up

# In a separate terminal — start the WebSocket server
python backend/ws_server.py
```

### Option B — Backend only (host machine as victim)

Skips Docker. The server monitors the host machine directly via psutil and treats it as the victim node.

```bash
python backend/ws_server.py
```

### Frontend

```bash
cd frontend && npm install && npm start
# Opens at http://localhost:3000
```

If the backend is running on a non-default host or port, set the environment variable before starting:

```bash
REACT_APP_WS_URL=ws://your-host:8765 npm start
```

**Offline replay:** If the WebSocket connection fails after 3 retries, the frontend automatically switches to offline mode and replays `frontend/build/demo_episode.json` at 7 FPS. No backend required in this mode.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and adjust as needed.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8765` | WebSocket server listen port |
| `VICTIM_NODE` | `User0` | Host machine node name |
| `HOST_NODES` | `Enterprise0,Enterprise1,Op_Server0` | Docker container node names |
| `HONEYPOT_IMAGE` | `soma_honeypot_image` | Docker image for the dynamically-spawned honeypot |
| `HONEYPOT_IP` | `172.22.0.99` | Static IP assigned to honeypot in soma-net |
| `HONEYPOT_PORT` | `8766` | WebSocket port the honeypot listens on |
| `HONEYPOT_HTTP_PORT` | `8082` | HTTP port exposed by honeypot |
| `SOMA_NET_CIDR` | `172.22.0.` | Subnet prefix for the Docker bridge |
| `ANOMALY_THRESHOLD` | `0.40` | Composite display_score above which INFECTED is triggered |
| `INFECTED_DWELL` | `5` | Seconds in INFECTED before ISOLATING fires |
| `WINDOW_SIZE` | `60` | Rolling baseline window size (ticks/seconds) |
| `GMAIL_USER` | — | Gmail address for real email trigger (optional) |
| `GMAIL_APP_PASSWORD` | — | Gmail app password (optional) |

---

## Testing

```bash
# Run all tests with verbose output
pytest tests/ -v

# With coverage report
pytest tests/ --cov=soma --cov-report=term-missing
```

| Test file | What it covers |
|---|---|
| `tests/test_innate.py` | InnateImmunityLayer fit/predict, threshold calibration at 1% FPR |
| `tests/test_adaptive.py` | PPO training loop, lateral movement and impact detection rates |
| `tests/test_signal_game.py` | SignalingGameEnv step mechanics, reward structure |
| `tests/test_pbe_solver.py` | PBE closed-form solution vs. RL convergence across κ values |
| `tests/test_fpr_calibration.py` | FPR threshold calibration on clean validation data |

---

## Tech Stack

| Component | Technology |
|---|---|
| ML / RL | PyTorch 2.x, Stable Baselines3 (PPO), scikit-learn (Isolation Forest) |
| Environments | CybORG CAGE 2, custom `SignalingGameEnv` |
| Backend | Python `websockets`, `psutil`, `asyncio` |
| Frontend | React 18, D3 7.8, Recharts |
| Containers | Docker, docker-compose |
| Utilities | NumPy, SciPy, Pandas, joblib, PyYAML, river |
| Testing | pytest, pytest-cov |
| Notebooks | Jupyter |

---

## Project Structure

```
SOMA/
├── soma/                  # Core Python package
│   ├── layers/            # Four detection layers (innate, adaptive, deception, memory, ...)
│   ├── envs/              # CybORG wrapper + SignalingGameEnv + synthetic network gen
│   ├── eval/              # FPR calibration, detection metrics
│   ├── theory/            # PBE solver, κ sweep
│   ├── fusion/            # Response orchestrator, network correlator
│   └── viz/               # Matplotlib plot generation
├── backend/               # WebSocket server + Docker support files
│   ├── ws_server.py       # Main demo server — state machine, honeypot, broadcast
│   ├── soma_agent.py      # Metrics agent that runs inside each Docker node
│   ├── honeypot_server.py # Telemetry agent for the honeypot container
│   ├── dockerfiles/       # Per-node Dockerfiles (node, enterprise0/1, op_server, honeypot)
│   ├── configs/           # Node-specific configuration files
│   └── .env.example       # Environment variable template
├── frontend/              # React + D3 SOC dashboard
│   ├── src/
│   │   ├── App.jsx        # Root component + state machine + WebSocket wiring
│   │   ├── components/    # Network graph, anomaly panels, incident log, honeypot panel, ...
│   │   ├── hooks/
│   │   │   └── useWebSocket.js  # WS connection + offline replay fallback
│   │   └── styles/
│   └── build/
│       └── demo_episode.json    # Static episode for offline replay
├── scripts/               # Training + evaluation + demo entry points
│   ├── train_innate.py
│   ├── train_adaptive.py
│   ├── train_deception.py
│   ├── evaluate.py
│   └── demo.py
├── tests/                 # Unit + integration tests
├── notebooks/             # Development and analysis notebooks
├── docs/                  # Implementation plan, architecture diagram, theory notes
├── models/                # Saved model weights (gitignored)
├── data/                  # Collected episode data (gitignored)
├── results/               # Evaluation outputs and plots
├── docker-compose.yml     # Four-node soma-net simulation
└── Dockerfile             # Production image for ws_server.py
```

---

## Theory Reference

The signaling game framework follows Carroll & Grosu (2011) and Pawlick & Zhu (2019). The attention parameter κ is a utility-cost approximation — not formal rational inattention (Sims 2003; Matějka & McKay, AER 2015). The PBE derivation and κ-sweep methodology are documented in `docs/theory/pbe_derivation.md`.

---

## Docs

- [`docs/SOMA_implementation_plan_v2.md`](docs/SOMA_implementation_plan_v2.md) — full build plan with layer-by-layer rationale
- [`docs/SOMA_architecture_v2.mermaid`](docs/SOMA_architecture_v2.mermaid) — system architecture diagram
- [`docs/theory/pbe_derivation.md`](docs/theory/pbe_derivation.md) — PBE math and κ-sweep methodology
