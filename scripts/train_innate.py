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

import json
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from tqdm import tqdm

from soma.envs.cyborg_wrapper import CybORGWrapper
from soma.layers.innate import InnateIsolationForest, InnateVAE


CLEAN_EPISODES  = 200
RED_EPISODES    = 50
STEPS_PER_EP    = 100
SPLIT           = (0.7, 0.15, 0.15)   # train / val / test
FPR_TARGET      = 0.01
RESULTS_DIR     = Path("results/fpr_calibration")
MODELS_DIR      = Path("models/innate")


def collect_clean_data(n_episodes: int) -> np.ndarray:
    """Run CybORG with no red agent; collect flat observation vectors."""
    env = CybORGWrapper(include_red=False)
    all_obs = []
    for _ in tqdm(range(n_episodes), desc="Clean episodes"):
        obs, _ = env.reset()
        all_obs.append(obs)
        for _ in range(STEPS_PER_EP - 1):
            obs, _, done, _, _ = env.step(0)  # action 0 = Monitor
            all_obs.append(obs)
            if done:
                break
    return np.array(all_obs, dtype=np.float32)


def collect_red_data(n_episodes: int):
    """Run CybORG with B_lineAgent; return (obs_array, step_labels)."""
    env = CybORGWrapper(include_red=True)
    all_obs, all_labels = [], []
    for _ in tqdm(range(n_episodes), desc="Red-agent episodes"):
        obs, _ = env.reset()
        all_obs.append(obs)
        all_labels.append(0)
        for _ in range(199):
            obs, _, done, _, info = env.step(0)  # Monitor — blue doesn't interfere
            all_obs.append(obs)
            all_labels.append(info.get("red_agent_step", 0))
            if done:
                break
    return np.array(all_obs, dtype=np.float32), np.array(all_labels, dtype=np.int32)


def train_vae(vae: InnateVAE, X_tr: np.ndarray, epochs: int = 50) -> InnateVAE:
    """Train VAE with ELBO loss (reconstruction + KL divergence)."""
    vae.train()
    optimizer = torch.optim.Adam(vae.parameters(), lr=1e-3)
    dataset   = torch.tensor(X_tr, dtype=torch.float32)
    batch_sz  = 64

    for epoch in range(epochs):
        idx    = torch.randperm(len(dataset))
        losses = []
        for start in range(0, len(dataset), batch_sz):
            batch = dataset[idx[start:start + batch_sz]]
            recon, mu, logvar = vae(batch)
            recon_loss = nn.functional.mse_loss(recon, batch)
            kl_loss    = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
            loss       = recon_loss + kl_loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        if (epoch + 1) % 10 == 0:
            print(f"  VAE epoch {epoch + 1}/{epochs}  loss={np.mean(losses):.4f}")

    vae.eval()
    return vae


def eval_tpr(is_anomalous_fn, obs: np.ndarray, step_labels: np.ndarray) -> float:
    """TPR at lateral movement phase (steps 4–8) using calibrated threshold."""
    mask = (step_labels >= 4) & (step_labels <= 8)
    lateral_obs = obs[mask]
    if len(lateral_obs) == 0:
        print("  WARNING: no lateral movement steps found in red data")
        return 0.0
    detected = sum(1 for x in lateral_obs if is_anomalous_fn(x))
    return detected / len(lateral_obs)


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Data collection ---
    print("Collecting clean episode data...")
    X = collect_clean_data(CLEAN_EPISODES)
    print(f"Clean data shape: {X.shape}")

    n     = len(X)
    n_tr  = int(n * SPLIT[0])
    n_val = int(n * SPLIT[1])
    X_tr, X_val, X_te = X[:n_tr], X[n_tr:n_tr + n_val], X[n_tr + n_val:]
    print(f"Train: {len(X_tr)}  Val: {len(X_val)}  Test: {len(X_te)}")

    # --- Isolation Forest ---
    print("\nTraining Isolation Forest...")
    iso = InnateIsolationForest()
    iso.fit(X_tr)
    iso.calibrate_threshold(X_val)
    iso.save(MODELS_DIR / "isolation_forest.joblib")
    print(f"  IF threshold: {iso.threshold_:.4f}")

    # --- VAE ---
    print("\nTraining VAE benchmark...")
    vae = InnateVAE()
    train_vae(vae, X_tr)
    vae.calibrate_threshold(X_val, fpr_target=FPR_TARGET)
    torch.save(vae.state_dict(), MODELS_DIR / "vae.pt")
    (MODELS_DIR / "vae_threshold.json").write_text(
        json.dumps({"threshold": vae.threshold_})
    )
    print(f"  VAE threshold: {vae.threshold_:.4f}")

    # --- Red-agent evaluation ---
    print("\nCollecting red-agent data for TPR evaluation...")
    X_red, red_labels = collect_red_data(RED_EPISODES)

    print("\nEvaluating TPR at lateral movement phase...")
    iso_tpr = eval_tpr(iso.is_anomalous, X_red, red_labels)
    vae_tpr = eval_tpr(vae.is_anomalous, X_red, red_labels)
    print(f"  IF  TPR = {iso_tpr:.3f}")
    print(f"  VAE TPR = {vae_tpr:.3f}")

    # --- Decision ---
    winner = "isolation_forest" if iso_tpr >= vae_tpr else "vae"
    print(f"\nBenchmark result: IF TPR={iso_tpr:.3f}  VAE TPR={vae_tpr:.3f}")
    print(f"Selected: {winner}")

    benchmark_text = (
        f"IF TPR={iso_tpr:.3f}  VAE TPR={vae_tpr:.3f}  Selected={winner}\n"
    )
    (RESULTS_DIR / "layer1_benchmark.txt").write_text(benchmark_text)

    # Copy winner to canonical path for downstream use
    if winner == "isolation_forest":
        import shutil
        shutil.copy(MODELS_DIR / "isolation_forest.joblib",
                    MODELS_DIR / "layer1_winner.joblib")
        (MODELS_DIR / "layer1_winner_type.txt").write_text("isolation_forest\n")
    else:
        import shutil
        shutil.copy(MODELS_DIR / "vae.pt", MODELS_DIR / "layer1_winner.pt")
        shutil.copy(MODELS_DIR / "vae_threshold.json",
                    MODELS_DIR / "layer1_winner_threshold.json")
        (MODELS_DIR / "layer1_winner_type.txt").write_text("vae\n")

    print(f"\nDone. Check results/fpr_calibration/layer1_benchmark.txt")


if __name__ == "__main__":
    main()
