"""
scripts/train_innate.py
========================
Layer 1 training — Innate Immunity (anomaly detection on CybORG observations).

Steps
-----
1. Collect clean CybORG episodes (no red agent) → X_train, X_val
2. Train InnateImmunityLayer (Isolation Forest, primary)
3. [--benchmark] Also train VAE; pick whichever wins TPR at fixed 1% FPR
4. Calibrate threshold: 99th percentile of clean val scores → 1% FPR
5. Smoke test on a fabricated anomalous obs
6. Save model to models/innate/isolation_forest.joblib

Expected runtime: ~5 minutes (no GPU needed)

Usage:
    python scripts/train_innate.py
    python scripts/train_innate.py --n-episodes 300 --val-episodes 100
    python scripts/train_innate.py --benchmark       # adds VAE comparison
    python scripts/train_innate.py --skip-collect    # reuse saved clean_data.npy
"""

import argparse
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

MODELS_DIR  = Path("models/innate")
DATA_DIR    = Path("data")
RESULTS_DIR = Path("results/fpr_calibration")


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_clean_episodes(
    n_episodes: int = 200,
    steps_per_episode: int = 100,
) -> np.ndarray:
    """
    Run CybORG with no red agent and collect flat observation vectors.

    Returns shape (n_episodes * steps_per_ep, 30).
    Each step the blue agent issues Monitor (action 0) — minimal interference.
    """
    from soma.envs.cyborg_wrapper import CybORGWrapper

    print(f"  Collecting {n_episodes} clean episodes ({steps_per_episode} steps each)…")
    env = CybORGWrapper(include_red=False)
    rows = []

    for ep in range(n_episodes):
        obs, _ = env.reset()
        rows.append(obs)
        for _ in range(steps_per_episode - 1):
            obs, _, done, _, _ = env.step(0)   # Monitor
            rows.append(obs)
            if done:
                obs, _ = env.reset()
                rows.append(obs)

        if (ep + 1) % 50 == 0:
            print(f"    …{ep + 1}/{n_episodes} episodes collected")

    X = np.array(rows, dtype=np.float32)
    print(f"  Clean data: {X.shape}  range=[{X.min():.3f}, {X.max():.3f}]")
    return X


# ---------------------------------------------------------------------------
# Optional VAE benchmark
# ---------------------------------------------------------------------------

def _train_vae_benchmark(X_train: np.ndarray, X_val: np.ndarray, fpr_target: float):
    """
    Train a minimal VAE for comparison.  Returns (threshold, score_fn).
    Failure mode: reconstruction error is not a reliable anomaly score
    (typicality gap — Nalisnick et al. ICLR 2019).  We include it as a
    benchmark, not a default.
    """
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError:
        print("  [skip] torch not available — skipping VAE benchmark")
        return None, None

    class VAE(nn.Module):
        def __init__(self, d=30, z=8):
            super().__init__()
            self.enc = nn.Sequential(nn.Linear(d, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU())
            self.mu  = nn.Linear(32, z)
            self.lv  = nn.Linear(32, z)
            self.dec = nn.Sequential(nn.Linear(z, 32), nn.ReLU(), nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, d))

        def forward(self, x):
            h = self.enc(x)
            mu, lv = self.mu(h), self.lv(h)
            z = mu + torch.exp(0.5 * lv) * torch.randn_like(mu)
            return self.dec(z), mu, lv

        def recon_error(self, x):
            with torch.no_grad():
                r, _, _ = self.forward(x)
                return F.mse_loss(r, x, reduction="none").mean(-1).numpy()

    vae = VAE(d=X_train.shape[1])
    opt = torch.optim.Adam(vae.parameters(), lr=1e-3)
    Xt  = torch.tensor(X_train)

    print("  Training VAE (30 epochs)…")
    for ep in range(30):
        opt.zero_grad()
        r, mu, lv = vae(Xt)
        recon = F.mse_loss(r, Xt)
        kld   = -0.5 * (1 + lv - mu.pow(2) - lv.exp()).mean()
        (recon + 0.001 * kld).backward()
        opt.step()

    Xv      = torch.tensor(X_val)
    val_err = vae.recon_error(Xv)
    thr     = float(np.percentile(val_err, (1 - fpr_target) * 100))
    score_fn = lambda x: float(vae.recon_error(torch.tensor(x.reshape(1, -1)))[0])
    return thr, score_fn


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train SOMA Layer 1 — Innate Immunity")
    parser.add_argument("--n-episodes",   type=int,   default=200,
                        help="Clean episodes to collect for training (default 200)")
    parser.add_argument("--val-episodes", type=int,   default=50,
                        help="Clean episodes to collect for validation (default 50)")
    parser.add_argument("--steps-per-ep", type=int,   default=100,
                        help="Steps per episode (default 100)")
    parser.add_argument("--fpr-target",   type=float, default=0.01,
                        help="Target false positive rate (default 0.01 = 1%%)")
    parser.add_argument("--benchmark",    action="store_true",
                        help="Also train VAE and compare TPR at fpr_target")
    parser.add_argument("--skip-collect", action="store_true",
                        help="Reuse data/clean_train.npy and data/clean_val.npy if they exist")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SOMA Layer 1 — Innate Immunity Training")
    print(f"  FPR target:    {args.fpr_target:.1%}")
    print(f"  Train episodes: {args.n_episodes}  ×  {args.steps_per_ep} steps")
    print(f"  Val   episodes: {args.val_episodes}  ×  {args.steps_per_ep} steps")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Step 1 — Collect (or reload) clean data
    # ------------------------------------------------------------------
    train_cache = DATA_DIR / "clean_train.npy"
    val_cache   = DATA_DIR / "clean_val.npy"

    if args.skip_collect and train_cache.exists() and val_cache.exists():
        print("\n[Step 1] Loading cached clean data…")
        X_train = np.load(train_cache)
        X_val   = np.load(val_cache)
        print(f"  Train: {X_train.shape}  Val: {X_val.shape}")
    else:
        print("\n[Step 1] Collecting clean CybORG episodes…")
        X_train = collect_clean_episodes(args.n_episodes,   args.steps_per_ep)
        X_val   = collect_clean_episodes(args.val_episodes, args.steps_per_ep)
        np.save(train_cache, X_train)
        np.save(val_cache,   X_val)
        print(f"  Saved to {train_cache}, {val_cache}")

    # ------------------------------------------------------------------
    # Step 2 — Train Isolation Forest
    # ------------------------------------------------------------------
    print("\n[Step 2] Training Isolation Forest…")
    from soma.layers.innate import InnateImmunityLayer

    iso = InnateImmunityLayer(n_estimators=200, fpr_target=args.fpr_target)
    iso.fit(X_train)

    # ------------------------------------------------------------------
    # Step 3 — Calibrate threshold on clean val data
    # ------------------------------------------------------------------
    print("\n[Step 3] Calibrating threshold on clean validation data…")
    iso.calibrate_threshold(X_val)

    iso_scores_val = iso.anomaly_scores_batch(X_val)
    iso_fpr_measured = float(np.mean(iso_scores_val > iso.threshold_))
    print(f"  Isolation Forest  threshold={iso.threshold_:.4f}  "
          f"FPR={iso_fpr_measured:.4f} (target {args.fpr_target:.4f})")

    # ------------------------------------------------------------------
    # Step 4 — [Optional] VAE benchmark
    # ------------------------------------------------------------------
    winner = iso
    winner_name = "isolation_forest"

    if args.benchmark:
        print("\n[Step 4] VAE benchmark…")
        vae_thr, vae_score_fn = _train_vae_benchmark(X_train, X_val, args.fpr_target)

        if vae_score_fn is not None:
            # Collect red-agent observations for TPR measurement
            print("  Collecting red-agent episodes for TPR benchmark…")
            from soma.envs.cyborg_wrapper import CybORGWrapper
            red_env = CybORGWrapper(include_red=True)
            red_rows = []
            for _ in range(20):
                obs, _ = red_env.reset()
                for _ in range(100):
                    obs, _, done, _, _ = red_env.step(0)
                    red_rows.append(obs)
                    if done:
                        break
            X_red = np.array(red_rows, dtype=np.float32)

            iso_scores_red = iso.anomaly_scores_batch(X_red)
            iso_tpr = float(np.mean(iso_scores_red > iso.threshold_))

            vae_scores_red = np.array([vae_score_fn(x) for x in X_red])
            vae_tpr = float(np.mean(vae_scores_red > vae_thr))

            print(f"  Isolation Forest  TPR={iso_tpr:.4f} at {args.fpr_target:.1%} FPR")
            print(f"  VAE               TPR={vae_tpr:.4f} at {args.fpr_target:.1%} FPR")
            print(f"  → Winner: {'Isolation Forest' if iso_tpr >= vae_tpr else 'VAE'}")

            # Regardless of VAE result, always use Isolation Forest:
            # VAE reconstruction error is not a reliable anomaly score (typicality
            # gap — Nalisnick et al. ICLR 2019). If VAE wins, it warrants investigation
            # of the specific failure mode before trusting the result.
            if vae_tpr > iso_tpr:
                print("  [NOTE] VAE wins, but Isolation Forest is still saved as primary.")
                print("         VAE reconstruction error has known failure modes on this")
                print("         input dimensionality — verify before switching.")
    else:
        print("\n[Step 4] Skipping VAE benchmark (pass --benchmark to enable)")

    # ------------------------------------------------------------------
    # Step 5 — Save
    # ------------------------------------------------------------------
    print(f"\n[Step 5] Saving model…")
    save_path = MODELS_DIR / "isolation_forest.joblib"
    winner.save(save_path)

    # Write benchmark summary
    bench_path = RESULTS_DIR / "layer1_benchmark.txt"
    bench_path.write_text(
        f"winner: {winner_name}\n"
        f"threshold: {winner.threshold_:.6f}\n"
        f"fpr_target: {args.fpr_target}\n"
        f"fpr_measured_val: {iso_fpr_measured:.6f}\n"
        f"n_train: {len(X_train)}\n"
        f"n_val: {len(X_val)}\n"
    )
    print(f"  Model → {save_path}")
    print(f"  Benchmark → {bench_path}")

    # ------------------------------------------------------------------
    # Step 6 — Smoke test
    # ------------------------------------------------------------------
    print("\n[Step 6] Smoke test…")
    obs_clean    = X_val[0]
    # Fabricate an anomalous observation: spike activity + compromise on all hosts
    obs_anomalous = obs_clean.copy()
    obs_anomalous[0::5] = 1.0   # activity=1 on every host
    obs_anomalous[1::5] = 1.0   # compromised=1 on every host

    clean_score = winner.anomaly_score(obs_clean)
    anom_score  = winner.anomaly_score(obs_anomalous)

    print(f"  Clean obs score:    {clean_score:.4f} → "
          f"{'ANOMALOUS ⚠' if winner.is_anomalous(obs_clean) else 'CLEAN ✓'}")
    print(f"  Anomalous obs score: {anom_score:.4f} → "
          f"{'ANOMALOUS ⚠' if winner.is_anomalous(obs_anomalous) else 'CLEAN ✓'}")

    if not winner.is_anomalous(obs_anomalous):
        print("  [WARN] Fabricated anomaly not detected — check feature scaling.")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"✓ Layer 1 complete.  Threshold={winner.threshold_:.4f}  "
          f"FPR={iso_fpr_measured:.4f} (target {args.fpr_target:.1%})")
    print("  Next: python scripts/train_adaptive.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
