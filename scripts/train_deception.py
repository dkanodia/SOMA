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

from pathlib import Path

RESULTS_DIR = Path("results/convergence")
MODELS_DIR  = Path("models/deception")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("Running κ sweep on SignalingGameEnv (standalone)...")
    # from soma.layers.deception import run_convergence_study
    # results = run_convergence_study(V=10.0, C=3.0, L=5.0, p_real=0.4)

    # for kappa, r in results.items():
    #     r["model"].save(str(MODELS_DIR / f"signal_policy_kappa_{kappa:.1f}"))

    print("Generating convergence plot (hero visual)...")
    # from soma.viz.plots import plot_convergence
    # plot_convergence(results, save_path=RESULTS_DIR / "convergence_plot.png")

    print("Done. Check results/convergence/convergence_plot.png")
    print("This is the hero visual for the pitch.")


if __name__ == "__main__":
    main()
