"""
scripts/train_innate.py
========================
End-to-end Layer 1 training. Run this first, before train_adaptive.py.

Usage:
    python scripts/train_innate.py
    python scripts/train_innate.py --records 5000
    python scripts/train_innate.py --attack-csv data/supplychaincloud.csv
    python scripts/train_innate.py --skip-fetch   # reuse existing data CSV

Expected runtime: ~10 minutes (mostly API fetching)
Output:
    data/layer1_features.csv               raw feature matrix (11 features)
    models/innate/isolation_forest.joblib  trained Isolation Forest
    models/innate/layer1_benchmark.txt     TPR / FPR results
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma.envs.supply_chain_ingest import build_layer1_dataset
from soma.layers.innate import train_layer1


def main():
    parser = argparse.ArgumentParser(description="Train SOMA Layer 1 innate detector")
    parser.add_argument("--records",    type=int,   default=2000)
    parser.add_argument("--attack-csv", type=str,   default=None)
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--fpr-target", type=float, default=0.01)
    args = parser.parse_args()

    features_csv = "data/layer1_features.csv"

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

    print("\n── Step 2: Model Training ────────────────────────────────")
    detector, results = train_layer1(
        features_csv=features_csv,
        model_save_path="models/innate/isolation_forest.joblib",
        fpr_target=args.fpr_target,
    )

    print("\n── Step 3: Smoke Test ────────────────────────────────────")
    import numpy as np

    # Normal: full competition, 5 bids, 45-day delivery, established vendor
    normal_tx = np.array([1.0, 5.0, 0.0, 45.0, 0.0, 365.0, 6.5, 0.0, 1.0, 0.0, 0.0])
    # Suspicious: sole-source, 1 bid, 3-day delivery, new vendor, cheap price
    suspicious_tx = np.array([0.3, 1.0, 1.0, 3.0, 1.0, 30.0, 4.2, 2.0, 0.0, 1.0, 1.0])

    n_score = detector.anomaly_score(normal_tx)
    s_score = detector.anomaly_score(suspicious_tx)

    print(f"  Normal score:     {n_score:.4f} → "
          f"{'ANOMALOUS ⚠' if detector.is_anomalous(normal_tx) else 'CLEAN ✓'}")
    print(f"  Suspicious score: {s_score:.4f} → "
          f"{'ANOMALOUS ⚠' if detector.is_anomalous(suspicious_tx) else 'CLEAN ✓'}")

    print("\n  Top anomaly drivers (suspicious transaction):")
    for feat, contrib in list(detector.feature_contribution(suspicious_tx).items())[:5]:
        bar = "█" * max(0, int(contrib * 20))
        print(f"    {feat:32s}  {contrib:+.4f}  {bar}")

    print(f"\n✓ Layer 1 complete. Threshold={detector.threshold_:.4f} "
          f"(FPR target {args.fpr_target:.1%})")
    print("  Next: python scripts/train_adaptive.py")


if __name__ == "__main__":
    main()
