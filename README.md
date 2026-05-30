# SOMA — Signaling-Optimal Memory Architecture

Autonomous cyber defense via reinforcement learning and signaling game theory.

## What This Is

SOMA is a research prototype demonstrating that RL agents can recover game-theoretically optimal deception policies in a cyber defense setting. It is **not** an operational product. Transfer to real networks is an open research problem and is not claimed.

Four detection layers operate across different timescales:

| Layer | Method | Timescale | FPR Budget |
|---|---|---|---|
| Innate | Isolation Forest (benchmarked vs VAE) | Per-step | 1% |
| Adaptive | PPO defender on CAGE 2 | Per-episode | 1% |
| Deception | Signaling game + RL (standalone) | Theoretical | n/a |
| Long-Dwell | PCA centroid drift detection | 100-episode rolling | 0.1% |

## What Is Claimed (with evidence)

- RL recovers PBE mixing rates across κ ∈ {0, V/2, V} — convergence plot is the evidence
- PPO detection rate: lateral movement ≥ 0.5, impact stage ≥ 0.8
- Anomaly detector benchmarked at fixed 1% FPR (Isolation Forest vs VAE)
- Drift alarm catches injected 2%/step behavioral drift at 0.1% FPR

## What Is NOT Claimed

- Transfer to real networks at any validated performance level
- Operational readiness
- Real adversary behavioral characterization
- Formal rational inattention (utility-cost approximation is used)
- Self-play convergence guarantees

## Signaling Game — Key Architectural Note

The deception layer (Layer 3) runs on `SignalingGameEnv`, a custom 2-type signaling game environment that is **separate from CybORG**. The RL policy trained there is validated against the closed-form PBE benchmark. Connection to CybORG is via an explicitly labeled heuristic trigger — not the game-theoretic policy — because B_lineAgent does not respond to signals.

## Quick Start

```bash
# 1. Install CybORG (CAGE 2)
git clone https://github.com/cage-challenge/cage-challenge-2
cd cage-challenge-2 && pip install -e . && cd ..

# 2. Install SOMA
pip install -e .

# 3. Verify environment
python scripts/verify_env.py

# 4. Train all layers (runs in sequence, ~3.5 hours total on GPU)
python scripts/train_innate.py
python scripts/train_adaptive.py
python scripts/train_deception.py   # runs kappa sweep internally

# 5. Run evaluation and calibration
python scripts/evaluate.py

# 6. Launch demo
python scripts/demo.py
# Open frontend: cd frontend && npm install && npm start
```

## Project Structure

```
soma/
├── soma/              # Core Python package
│   ├── layers/        # Four detection layers
│   ├── envs/          # CybORG wrapper + SignalingGameEnv
│   ├── eval/          # FPR calibration, detection metrics, benchmarks
│   ├── theory/        # PBE solver, κ sweep
│   └── viz/           # Matplotlib plot generation
├── scripts/           # Training + demo entry points
├── frontend/          # React + D3 visualization
├── tests/             # Unit + integration tests
├── notebooks/         # Development and analysis notebooks
├── docs/              # Implementation plan, architecture diagram, theory notes
├── models/            # Saved model weights (gitignored by default)
├── data/              # Collected episode data (gitignored)
└── results/           # Evaluation outputs and plots
```

## Theory Reference

The signaling game framework follows Carroll & Grosu (2011) and Pawlick & Zhu (2019). The attention parameter κ is a utility-cost approximation — not formal rational inattention (Sims 2003; Matějka & McKay, AER 2015). PBE derivation is in `docs/theory/pbe_derivation.md`.

## Environment

- Python 3.10+
- PyTorch 2.x
- Stable Baselines3
- CybORG (CAGE 2 — see installation above)
- Node 18+ (frontend only)

## Honest Limitations

- Trained in simulation against B_lineAgent (scripted, deterministic attack chain)
- B_lineAgent does not respond to defender signals — signaling game result is separate
- No evaluation on real endpoint data
- FPR budgets calibrated on simulation data only

## Docs

- [`docs/SOMA_implementation_plan_v2.md`](docs/SOMA_implementation_plan_v2.md) — full build plan
- [`docs/SOMA_architecture_v2.mermaid`](docs/SOMA_architecture_v2.mermaid) — architecture diagram
- [`docs/theory/pbe_derivation.md`](docs/theory/pbe_derivation.md) — PBE math
