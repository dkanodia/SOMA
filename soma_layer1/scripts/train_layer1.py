"""
scripts/train_layer1.py
========================
End-to-end Layer 1 training script. Run this first, before anything else.

Usage:
    python scripts/train_layer1.py
    python scripts/train_layer1.py --records 5000
    python scripts/train_layer1.py --attack-csv data/supplychaincloud.csv

What it does:
    1. Pulls DoD contract records from USASpending.gov (free, no auth)
    2. Engineers 11-feature vector per procurement transaction
    3. Filters a clean baseline (verified-looking contracts)
    4. Trains Isolation Forest on the clean baseline
    5. Benchmarks against IQR baseline
    6. Calibrates threshold at 1% FPR
    7. Saves model to models/innate/isolation_forest.joblib

Expected runtime: ~10 minutes (mostly API fetching)
Expected output:
    data/layer1_features.csv         — raw feature matrix
    models/innate/isolation_forest.joblib  — trained model
    models/innate/layer1_benchmark.txt     — TPR/FPR results
"""

import argparse
import sys
from pathlib import Path

# Make sure soma package is importable from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from soma.envs.supply_chain_ingest import build_layer1_dataset
from soma.layers.innate import train_layer1


def main():
    parser = argparse.ArgumentParser(description="Train SOMA Layer 1 innate detector")
    parser.add_argument(
        "--records", type=int, default=2000,
        help="Number of USASpending records to fetch (default: 2000)"
    )
    parser.add_argument(
        "--attack-csv", type=str, default=None,
        help="Path to SupplyChainCloud CSV for ground-truth labels (optional)"
    )
    parser.add_argument(
        "--skip-fetch", action="store_true",
        help="Skip API fetch and use existing data/layer1_features.csv"
    )
    parser.add_argument(
        "--fpr-target", type=float, default=0.01,
        help="Target false positive rate (default: 0.01)"
    )
    args = parser.parse_args()

    features_csv = "data/layer1_features.csv"

    # Step 1: Data ingestion
    if not args.skip_fetch or not Path(features_csv).exists():
        print("\n── Step 1: Data Ingestion ─────────────────────────────")
        df = build_layer1_dataset(
            n_records=args.records,
            attack_csv=args.attack_csv,
            save_path=features_csv,
        )
        if df.empty:
            print("ERROR: Failed to build dataset. Exiting.")
            sys.exit(1)
    else:
        print(f"\n── Step 1: Skipping fetch, using {features_csv} ──────")

    # Step 2: Train model
    print("\n── Step 2: Model Training ────────────────────────────────")
    detector, results = train_layer1(
        features_csv=features_csv,
        model_save_path="models/innate/isolation_forest.joblib",
        fpr_target=args.fpr_target,
    )

    # Step 3: Quick smoke test
    print("\n── Step 3: Smoke Test ────────────────────────────────────")
    import numpy as np

    # Normal transaction (full competition, multiple bids, reasonable timing)
    normal_tx = np.array([1.0, 5.0, 0.0, 45.0, 0.0, 365.0, 6.5, 0.0, 1.0, 0.0, 0.0])
    # Suspicious transaction (sole source, 1 bid, fast delivery, new vendor)
    suspicious_tx = np.array([0.3, 1.0, 1.0, 3.0, 1.0, 30.0, 4.2, 2.0, 0.0, 1.0, 1.0])

    normal_score    = detector.anomaly_score(normal_tx)
    suspicious_score = detector.anomaly_score(suspicious_tx)

    print(f"  Normal transaction score:     {normal_score:.4f} → "
          f"{'ANOMALOUS ⚠' if detector.is_anomalous(normal_tx) else 'CLEAN ✓'}")
    print(f"  Suspicious transaction score: {suspicious_score:.4f} → "
          f"{'ANOMALOUS ⚠' if detector.is_anomalous(suspicious_tx) else 'CLEAN ✓'}")

    # Feature contribution for suspicious transaction
    print("\n  Top anomaly drivers for suspicious transaction:")
    contributions = detector.feature_contribution(suspicious_tx)
    for feat, contrib in list(contributions.items())[:5]:
        bar = "█" * max(0, int(contrib * 20))
        print(f"    {feat:30s}  {contrib:+.4f}  {bar}")

    print("\n✓ Layer 1 training complete.")
    print(f"  Model: models/innate/isolation_forest.joblib")
    print(f"  Threshold: {detector.threshold_:.4f} (FPR target: {args.fpr_target:.1%})")
    print(f"\n  Next step: python scripts/train_layer2.py")


if __name__ == "__main__":
    main()
