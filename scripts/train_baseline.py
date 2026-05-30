"""
scripts/train_baseline.py
==========================
Train Layer 1 (Innate) and Layer 5 (Learned Attacks) baselines.

Collects clean CybORG (or synthetic fallback) observations,
fits the Isolation Forest baseline, and saves the model.

Usage:
  python -m scripts.train_baseline
  python -m scripts.train_baseline --n-steps 2000 --seed 0
"""

import argparse
import numpy as np
from pathlib import Path


MODELS_DIR = Path("models/innate")


def collect_clean_data(n_steps: int = 1000, seed: int = 0) -> np.ndarray:
    """Collect clean network observations (no red agent)."""
    print(f"  Collecting {n_steps} clean steps (seed={seed})...")

    # Try CybORG first; fall back to synthetic generator
    try:
        from soma.envs.cyborg_wrapper import CybORGWrapper
        env = CybORGWrapper(include_red=False)
        obs, _ = env.reset(seed=seed)
        rows = [obs]
        done = False
        step = 0
        while len(rows) < n_steps and not done:
            obs, _, done, _, _ = env.step(0)   # action 0 = Monitor
            rows.append(obs)
            step += 1
            if done:
                obs, _ = env.reset()
                rows.append(obs)
        return np.array(rows[:n_steps], dtype=np.float32)

    except (ImportError, Exception) as e:
        print(f"  CybORG not available ({e}), using synthetic fallback.")
        from soma.envs.synthetic_network_gen import generate_clean_episodes
        return generate_clean_episodes(n_steps=n_steps, seed=seed)


def main():
    parser = argparse.ArgumentParser(description="Train SOMA immune baseline")
    parser.add_argument("--n-steps",  type=int,   default=1000, help="Clean steps to collect")
    parser.add_argument("--seed",     type=int,   default=0,    help="RNG seed")
    parser.add_argument("--fpr",      type=float, default=0.01, help="Target FPR")
    parser.add_argument("--out",      type=str,   default="models/innate/baseline.joblib")
    args = parser.parse_args()

    print("=" * 60)
    print("SOMA Baseline Training — Layer 1 (Innate Immunity)")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Collect clean data
    # ------------------------------------------------------------------
    print("\n[Step 1] Collecting clean network data...")
    X = collect_clean_data(n_steps=args.n_steps + 200, seed=args.seed)

    # Train/val split
    split = args.n_steps
    X_train = X[:split]
    X_val   = X[split:]
    print(f"  Train: {len(X_train)} steps | Val: {len(X_val)} steps")
    print(f"  Obs shape: {X_train.shape}  range=[{X_train.min():.3f}, {X_train.max():.3f}]")

    # ------------------------------------------------------------------
    # 2. Fit Isolation Forest
    # ------------------------------------------------------------------
    print("\n[Step 2] Fitting Isolation Forest...")
    from soma.layers.innate import InnateImmunityLayer
    layer = InnateImmunityLayer(fpr_target=args.fpr)
    layer.fit(X_train)

    # ------------------------------------------------------------------
    # 3. Calibrate threshold
    # ------------------------------------------------------------------
    print("\n[Step 3] Calibrating threshold...")
    layer.calibrate_threshold(X_val)

    # Verify FPR on val
    scores = layer.anomaly_scores_batch(X_val)
    fpr_measured = float(np.mean(scores > layer.threshold_))
    print(f"  Measured FPR on held-out val: {fpr_measured:.4f} (target {args.fpr})")

    # ------------------------------------------------------------------
    # 4. Save model
    # ------------------------------------------------------------------
    print("\n[Step 4] Saving model...")
    out_path = Path(args.out)
    layer.save(out_path)

    # ------------------------------------------------------------------
    # 5. Fit VAE (Layer 5) on clean data
    # ------------------------------------------------------------------
    print("\n[Step 5] Fitting VAE for learned attack recognition...")
    from soma.layers.learned_attacks import LearnedAttackRecognizer
    rec = LearnedAttackRecognizer()
    rec.fit(X_train, epochs=50, verbose=True)

    vae_path = out_path.parent / "vae.joblib"
    rec.save(vae_path)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Training Complete")
    print("=" * 60)
    print(f"  Innate threshold:  {layer.threshold_:.4f}")
    print(f"  FPR on val:        {fpr_measured:.4f}")
    print(f"  VAE gallery size:  {rec.gallery_size}")
    print(f"\n  Models saved:")
    print(f"    {out_path}")
    print(f"    {vae_path}")
    print("\n  Next: python -m scripts.run_cyber_stack")


if __name__ == "__main__":
    main()
