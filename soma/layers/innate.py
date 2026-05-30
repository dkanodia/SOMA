"""
soma/layers/innate.py  (supply chain version)
==============================================
Layer 1 — Innate Immunity: per-shipment anomaly detection.

Biological framing:
  The innate immune system recognizes foreign body patterns instantly,
  without needing prior exposure to the specific pathogen. The Isolation
  Forest learns the normal distribution of verified DoD procurement
  transactions and flags anything that does not belong.

Architecture:
  Primary:   Isolation Forest (sklearn)    trained on clean contracts
  Benchmark: IQR-based statistical screen  simple baseline to beat
  Threshold: calibrated at 1% FPR on held-out clean validation data

FPR budget: 1%
  At 100 shipments/day: ~1 false alarm/day — operationally tolerable.

What "clean" means:
  USASpending records with > 1 offer, > $10k award, full & open competition,
  reasonable delivery window, proper DoD agency. Not fraud-free — it is the
  statistical baseline. The IF detects departure from this baseline.
  State this clearly in the pitch.
"""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional, Tuple
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split


FEATURE_COLS = [
    "f0_price_deviation",
    "f1_num_offers",
    "f2_single_bid",
    "f3_days_to_delivery",
    "f4_fast_delivery",
    "f5_contract_duration",
    "f6_award_amount_log",
    "f7_competition",
    "f8_dod_agency",
    "f9_new_vendor",
    "f_risk_combo",
]


def filter_clean_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only records that look like legitimate, properly-competed DoD
    procurement. Forms the Isolation Forest training distribution.
    NOT a fraud-free guarantee — state this in the pitch.
    """
    mask = (
        (df["f1_num_offers"] > 1) &
        (df["f6_award_amount_log"] >= 4) &
        (df["f7_competition"] == 0) &
        (df["f3_days_to_delivery"] >= 7) &
        (df["f8_dod_agency"] == 1) &
        (df["f2_single_bid"] == 0)
    )
    clean = df[mask].copy()
    print(f"Clean baseline: {len(clean)} / {len(df)} records "
          f"({len(clean)/len(df)*100:.1f}%)")
    return clean


class InnateSupplyChainDetector:
    """
    Isolation Forest anomaly detector for defense procurement transactions.
    Replaces the CybORG-based network intrusion detector.
    Interface is identical: fit(), calibrate_threshold(), is_anomalous(),
    anomaly_score(), screen_batch(), save(), load().
    """

    def __init__(
        self,
        n_estimators: int = 200,
        contamination: float = 0.01,
        fpr_target: float = 0.01,
        random_state: int = 42,
    ):
        self.n_estimators  = n_estimators
        self.contamination = contamination
        self.fpr_target    = fpr_target
        self.random_state  = random_state
        self.model         = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
            n_jobs=-1,
        )
        self.scaler       = StandardScaler()
        self.threshold_: Optional[float] = None
        self.feature_cols = FEATURE_COLS

    def fit(self, X_clean: np.ndarray) -> "InnateSupplyChainDetector":
        """Train on clean (verified baseline) procurement records."""
        X_scaled = self.scaler.fit_transform(X_clean)
        self.model.fit(X_scaled)
        print(f"Isolation Forest trained on {len(X_clean)} clean records.")
        return self

    def calibrate_threshold(self, X_val_clean: np.ndarray) -> float:
        """
        Set threshold so FPR on clean validation data equals fpr_target.
        Scores are negated so higher = more anomalous.
        """
        X_scaled = self.scaler.transform(X_val_clean)
        scores = -self.model.score_samples(X_scaled)
        self.threshold_ = float(np.percentile(scores, (1 - self.fpr_target) * 100))
        measured_fpr = float(np.mean(scores > self.threshold_))
        print(f"Calibrated threshold: {self.threshold_:.4f}")
        print(f"Measured FPR on clean val: {measured_fpr:.4f} "
              f"(target: {self.fpr_target:.4f})")
        # Wider tolerance for small val sets (percentile estimation is noisy)
        tol = max(0.005, 2.0 / max(len(X_val_clean), 1))
        assert measured_fpr <= self.fpr_target + tol, (
            f"FPR {measured_fpr:.4f} exceeds target {self.fpr_target} + {tol:.3f}"
        )
        return self.threshold_

    def anomaly_score(self, x: np.ndarray) -> float:
        """Raw anomaly score. Higher = more anomalous (foreign body)."""
        x_scaled = self.scaler.transform(x.reshape(1, -1))
        return float(-self.model.score_samples(x_scaled)[0])

    def anomaly_scores_batch(self, X: np.ndarray) -> np.ndarray:
        """Batch anomaly scores. Shape: (n_samples,)"""
        X_scaled = self.scaler.transform(X)
        return -self.model.score_samples(X_scaled)

    def is_anomalous(self, x: np.ndarray) -> bool:
        """True if this shipment should be escalated to Layer 2."""
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() before is_anomalous().")
        return self.anomaly_score(x) > self.threshold_

    def screen_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Screen a batch of procurement records.
        Adds: anomaly_score, is_anomalous, escalate_to_layer2, risk_tier.
        Main interface for the demo server.
        """
        X = df[self.feature_cols].fillna(0).values
        scores = self.anomaly_scores_batch(X)
        result = df.copy()
        result["anomaly_score"]      = scores
        result["is_anomalous"]       = scores > (self.threshold_ or 0.5)
        result["escalate_to_layer2"] = result["is_anomalous"]
        if self.threshold_:
            result["risk_tier"] = pd.cut(
                scores,
                bins=[-np.inf, self.threshold_ * 0.5, self.threshold_, np.inf],
                labels=["normal", "suspicious", "critical"]
            )
        return result

    def feature_contribution(self, x: np.ndarray) -> dict:
        """
        Per-feature contribution to anomaly score via leave-one-out ablation.
        Used for the demo explainability panel.
        """
        baseline = self.anomaly_score(x)
        contributions = {}
        for i, col in enumerate(self.feature_cols):
            x_p = x.copy()
            x_p[i] = 0.0
            contributions[col] = float(baseline - self.anomaly_score(x_p))
        return dict(sorted(contributions.items(), key=lambda kv: -kv[1]))

    def save(self, path: Path) -> None:
        joblib.dump({
            "model":        self.model,
            "scaler":       self.scaler,
            "threshold":    self.threshold_,
            "feature_cols": self.feature_cols,
            "fpr_target":   self.fpr_target,
        }, path)
        print(f"Model saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "InnateSupplyChainDetector":
        d = joblib.load(path)
        obj = cls()
        obj.model        = d["model"]
        obj.scaler       = d["scaler"]
        obj.threshold_   = d["threshold"]
        obj.feature_cols = d["feature_cols"]
        obj.fpr_target   = d["fpr_target"]
        return obj


class IQRBaseline:
    """
    IQR-based anomaly detector. Flags if any feature is > k IQRs from median.
    This is the baseline the Isolation Forest must outperform.
    Report both TPRs in the pitch — the gap is the contribution.
    """

    def __init__(self, k: float = 3.0):
        self.k = k
        self.medians_: Optional[np.ndarray] = None
        self.iqrs_:    Optional[np.ndarray] = None

    def fit(self, X_clean: np.ndarray) -> "IQRBaseline":
        q25 = np.percentile(X_clean, 25, axis=0)
        q75 = np.percentile(X_clean, 75, axis=0)
        self.medians_ = np.median(X_clean, axis=0)
        self.iqrs_    = np.maximum(q75 - q25, 1e-6)
        return self

    def is_anomalous(self, x: np.ndarray) -> bool:
        if self.medians_ is None:
            raise RuntimeError("Call fit() first.")
        z = np.abs(x - self.medians_) / self.iqrs_
        return bool(np.any(z > self.k))

    def anomaly_scores_batch(self, X: np.ndarray) -> np.ndarray:
        z = np.abs(X - self.medians_) / self.iqrs_
        return z.max(axis=1)


def train_layer1(
    features_csv: str = "data/layer1_features.csv",
    model_save_path: str = "models/innate/isolation_forest.joblib",
    fpr_target: float = 0.01,
    val_size: float = 0.15,
    test_size: float = 0.15,
) -> Tuple[InnateSupplyChainDetector, dict]:
    """
    Full Layer 1 training pipeline.
    1. Load feature CSV
    2. Filter clean baseline
    3. Train/val/test split
    4. Train Isolation Forest + IQR baseline
    5. Calibrate threshold at fpr_target
    6. Evaluate TPR and FPR
    7. Save model and benchmark results
    """
    print("=" * 60)
    print("SOMA Layer 1 — Innate Immunity Training")
    print("=" * 60)

    df = pd.read_csv(features_csv)
    print(f"\nLoaded {len(df)} procurement records.")

    clean_df = filter_clean_baseline(df)
    if len(clean_df) < 100:
        print("WARNING: < 100 clean records. Consider fetching more data.")

    X_clean = clean_df[FEATURE_COLS].fillna(0).values

    X_tr, X_temp = train_test_split(
        X_clean, test_size=val_size + test_size, random_state=42
    )
    X_val, X_te = train_test_split(
        X_temp, test_size=test_size / (val_size + test_size), random_state=42
    )
    print(f"\nSplit — Train: {len(X_tr)} | Val: {len(X_val)} | Test: {len(X_te)}")

    print("\nTraining Isolation Forest...")
    detector = InnateSupplyChainDetector(fpr_target=fpr_target)
    detector.fit(X_tr)

    print("\nCalibrating threshold on clean validation data...")
    detector.calibrate_threshold(X_val)

    print("\nTraining IQR baseline...")
    baseline = IQRBaseline()
    baseline.fit(X_tr)

    print("\nEvaluating on held-out test data...")
    if_scores_clean  = detector.anomaly_scores_batch(X_te)
    iqr_scores_clean = baseline.anomaly_scores_batch(X_te)
    if_fpr  = float(np.mean(if_scores_clean  > detector.threshold_))
    iqr_fpr = float(np.mean(iqr_scores_clean > baseline.k))

    anomalous_df = df[df.get("is_anomalous", pd.Series(0, index=df.index)) == 1]
    if len(anomalous_df) > 0:
        X_anom = anomalous_df[FEATURE_COLS].fillna(0).values
        if_tpr  = float(np.mean(detector.anomaly_scores_batch(X_anom) > detector.threshold_))
        iqr_tpr = float(np.mean(baseline.anomaly_scores_batch(X_anom) > baseline.k))
    else:
        if_tpr = iqr_tpr = None
        print("  No labeled anomalies for TPR (need SupplyChainCloud labels).")

    results = {
        "isolation_forest_fpr": if_fpr,
        "isolation_forest_tpr": if_tpr,
        "iqr_baseline_fpr":     iqr_fpr,
        "iqr_baseline_tpr":     iqr_tpr,
        "threshold":            detector.threshold_,
        "n_train":              len(X_tr),
        "n_val":                len(X_val),
        "n_test":               len(X_te),
        "n_anomalous_labeled":  len(anomalous_df),
    }

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Isolation Forest:  FPR={if_fpr:.4f}  TPR={if_tpr}")
    print(f"  IQR Baseline:      FPR={iqr_fpr:.4f}  TPR={iqr_tpr}")
    winner = "Isolation Forest" if (if_tpr or 0) >= (iqr_tpr or 0) else "IQR Baseline"
    print(f"\n  Selected: {winner}")
    print("=" * 60)

    Path(model_save_path).parent.mkdir(parents=True, exist_ok=True)
    detector.save(Path(model_save_path))

    results_path = Path(model_save_path).parent / "layer1_benchmark.txt"
    with open(results_path, "w") as f:
        for k, v in results.items():
            f.write(f"{k}: {v}\n")
    print(f"\nBenchmark saved to {results_path}")

    return detector, results
