"""
scripts/train_deception.py
===========================
Train Layer 3 signaling game RL policies and generate convergence plots.

Runs κ sweep: trains one PPO policy per κ ∈ {0.0, 5.0, 10.0}.
Compares learned mixing rates to closed-form PBE benchmark.
Saves convergence plot to results/convergence/convergence_plot.png.

Expected runtime: ~90 minutes total (3 × 30 min)

This script runs on SignalingGameEnv ONLY.
It does NOT interact with CybORG.
"""

import json
import shutil
from pathlib import Path

from soma.layers.deception import run_convergence_study
from soma.viz.plots import plot_convergence, plot_kappa_sweep
from soma.theory.pbe_solver import kappa_sweep

RESULTS_DIR    = Path("results/convergence")
MODELS_DIR     = Path("models/deception")
FRONTEND_PUBLIC = Path("frontend/public")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)

    print("Running theoretical κ sweep (pure math, fast)...")
    pbe_results = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
    plot_kappa_sweep(pbe_results, save_path=RESULTS_DIR / "kappa_sweep.png")

    print("\nRunning κ sweep on SignalingGameEnv (standalone)...")
    rl_results = run_convergence_study(V=10.0, C=3.0, L=5.0, p_real=0.4)

    for kappa, r in rl_results.items():
        r["model"].save(str(MODELS_DIR / f"signal_policy_kappa_{kappa:.1f}"))

    print("\nGenerating convergence plot (hero visual)...")
    convergence_data = {
        k: {
            "learned_r_history": r["learned_r_history"],
            "pbe_r_star":        r["pbe"].r_star,
        }
        for k, r in rl_results.items()
    }
    plot_convergence(convergence_data, save_path=RESULTS_DIR / "convergence_plot.png")

    print("\nSaving RL vs PBE comparison data...")
    comparison = {
        str(k): {
            "kappa":      k,
            "learned_q":  r["learned_q"],
            "learned_r":  r["learned_r"],
            "pbe_q_star": r["pbe"].q_star,
            "pbe_r_star": r["pbe"].r_star,
            "pbe_mu_star": r["pbe"].mu_star,
        }
        for k, r in rl_results.items()
    }
    with open(RESULTS_DIR / "comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)

    print("\nCopying assets to frontend/public/ for dashboard...")
    for fname in ["convergence_plot.png", "kappa_sweep.png", "comparison.json"]:
        shutil.copy(RESULTS_DIR / fname, FRONTEND_PUBLIC / fname)
        print(f"  Copied {fname}")

    print("\nDone.")
    print("Hero visual: results/convergence/convergence_plot.png")
    print("Comparison:  results/convergence/comparison.json")
    print("\nRL vs PBE summary:")
    for k_str, v in comparison.items():
        print(
            f"  κ={v['kappa']:.1f}:  "
            f"q={v['learned_q']:.3f} (PBE {v['pbe_q_star']:.3f})  "
            f"r={v['learned_r']:.3f} (PBE {v['pbe_r_star']:.3f})"
        )


if __name__ == "__main__":
    main()
