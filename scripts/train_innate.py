"""
scripts/train_innate.py
========================
Train Layer 1 anomaly detectors and choose the best one.

Steps
-----
1. Collect clean episodes from CybORG (no red agent)
2. Train Isolation Forest and VAE on train split
3. Calibrate both at 1% FPR on val split
4. Evaluate TPR at fixed 1% FPR on test split (with red agent)
5. Save whichever wins — state result in results/fpr_calibration/layer1_benchmark.txt

Expected runtime: < 30 minutes
"""

import numpy as np
from pathlib import Path

# TODO: from soma.envs.cyborg_wrapper import CybORGWrapper, HOST_NAMES
# TODO: from soma.layers.innate import InnateIsolationForest, InnateVAE
# TODO: from soma.eval.fpr_calibration import calibrate_layer1


CLEAN_EPISODES  = 200
SPLIT           = (0.7, 0.15, 0.15)   # train / val / test
FPR_TARGET      = 0.01
RESULTS_DIR     = Path("results/fpr_calibration")
MODELS_DIR      = Path("models/innate")


def collect_clean_data(n_episodes: int) -> np.ndarray:
    """Run CybORG with no red agent; collect flat observation vectors."""
    # TODO: implement
    raise NotImplementedError


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("Collecting clean episode data...")
    X = collect_clean_data(CLEAN_EPISODES)

    n     = len(X)
    n_tr  = int(n * SPLIT[0])
    n_val = int(n * SPLIT[1])
    X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr+n_val], X[n_tr+n_val:]

    print(f"Train: {len(X_tr)}  Val: {len(X_val)}  Test: {len(X_te)}")

    # --- Isolation Forest ---
    print("\nTraining Isolation Forest...")
    # iso = InnateIsolationForest()
    # iso.fit(X_tr)
    # iso.calibrate_threshold(X_val)
    # iso.save(MODELS_DIR / "isolation_forest.joblib")
    # iso_tpr = eval_tpr(iso.is_anomalous, X_te_red)

    # --- VAE ---
    print("Training VAE benchmark...")
    # vae = InnateVAE()
    # train_vae(vae, X_tr)
    # vae.calibrate_threshold(X_val)
    # torch.save(vae.state_dict(), MODELS_DIR / "vae.pt")
    # vae_tpr = eval_tpr(vae.is_anomalous, X_te_red)

    # --- Decision ---
    # winner = "isolation_forest" if iso_tpr >= vae_tpr else "vae"
    # print(f"\nBenchmark result: IF TPR={iso_tpr:.3f}  VAE TPR={vae_tpr:.3f}")
    # print(f"Selected: {winner}")
    # (RESULTS_DIR / "layer1_benchmark.txt").write_text(
    #     f"IF TPR={iso_tpr:.3f}  VAE TPR={vae_tpr:.3f}  Selected={winner}\n"
    # )

    print("\nDone. Check results/fpr_calibration/layer1_benchmark.txt")


if __name__ == "__main__":
    main()
