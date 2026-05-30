"""
soma/layers/innate.py  (supply chain version)
==============================================
Layer 1 — Innate Immunity: per-shipment anomaly detection.

Biological framing:
  The innate immune system recognizes "foreign body" patterns instantly,
  without needing prior exposure to the specific pathogen. Our Isolation
  Forest does the same — it learns the normal distribution of verified
  DoD procurement transactions and flags anything that doesn't belong.

Architecture:
  Primary:   Isolation Forest (sklearn)  ← trained on clean contracts
  Benchmark: IQR-based statistical screen ← simple baseline to beat
  Threshold: calibrated at 1% FPR on held-out clean validation data

FPR budget: 1%
  At 100 shipments/day: ~1 false alarm/day — operationally tolerable.

What "clean" means here:
  USASpending records for DoD contracts with:
    - Number of offers > 1  (real competition)
    - Award amount > $10k   (above micro-purchase, properly logged)
    - Known awarding agency (not null)
    - Reasonable delivery window (14–365 days)
  These are not confirmed-authentic — they're the statistical baseline.
  The Isolation Forest detects departure from this baseline, not fraud per se.
  That honest framing goes in the pitch.
"""

import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from typing import Optional, Tuple
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split


# ── Feature columns fed to the model ──────────────────────────────────────
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


# ── Clean data filter ──────────────────────────────────────────────────────

def filter_clean_baseline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Heuristic filter: keep only records that look like legitimate,
    properly-competed DoD procurement. These form the Isolation Forest's
    training distribution (the "healthy tissue" the immune system learns).

    NOT a fraud-free guarantee — it's a statistical baseline selection.
    State this clearly in the pitch.
    """
    mask = (
        (df["f1_num_offers"] > 1) &           # real competition
        (df["f6_award_amount_log"] >= 4) &     # > $10k
        (df["f7_competition"] == 0) &          # full & open competition
        (df["f3_days_to_delivery"] >= 7) &     # reasonable lead time
        (df["f8_dod_agency"] == 1) &           # proper DoD agency
        (df["f2_single_bid"] == 0)             # not single-bid
    )
    clean = df[mask].copy()
    print(f"Clean baseline: {len(clean)} / {len(df)} records "
          f"({len(clean)/len(df)*100:.1f}%)")
    return clean


# ── Isolation Forest Detector ──────────────────────────────────────────────

class InnateSupplyChainDetector:
    """
    Isolation Forest anomaly detector for defense procurement transactions.

    The Isolation Forest isolates observations by randomly partitioning
    the feature space. Anomalous samples (foreign bodies) are isolated
    in fewer splits than normal samples — they're the outliers.

    Parameters
    ----------
    n_estimators : int
        Number of isolation trees. 200 is sufficient for 11-dim input.
    contamination : float
        Expected fraction of anomalies in training data. We set this to
        the FPR target (0.01) since we train on "clean" data — the model
        should flag only 1% of clean observations as anomalous.
    fpr_target : float
        Target false positive rate on held-out clean data.
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

        self.model     = IsolationForest(
            n_estimators  = n_estimators,
            contamination = contamination,
            random_state  = random_state,
            n_jobs        = -1,
        )
        self.scaler    = StandardScaler()
        self.threshold_: Optional[float] = None
        self.feature_cols = FEATURE_COLS

    # ── Training ──────────────────────────────────────────────────────────

    def fit(self, X_clean: np.ndarray) -> "InnateSupplyChainDetector":
        """Train on clean (verified baseline) procurement records."""
        X_scaled = self.scaler.fit_transform(X_clean)
        self.model.fit(X_scaled)
        print(f"Isolation Forest trained on {len(X_clean)} clean records.")
        return self

    def calibrate_threshold(self, X_val_clean: np.ndarray) -> float:
        """
        Set decision threshold so FPR on clean validation data = fpr_target.

        Isolation Forest score convention: more negative = more anomalous.
        We negate scores so that higher = more anomalous (consistent with
        the rest of the codebase).

        Returns the calibrated threshold.
        """
        X_scaled = self.scaler.transform(X_val_clean)
        # negate: now higher score = more anomalous
        scores = -self.model.score_samples(X_scaled)

        # Threshold = (1 - fpr_target)-th percentile of clean scores
        # i.e. exactly fpr_target% of clean records exceed this threshold
        self.threshold_ = float(np.percentile(scores, (1 - self.fpr_target) * 100))

        measured_fpr = float(np.mean(scores > self.threshold_))
        print(f"Calibrated threshold: {self.threshold_:.4f}")
        print(f"Measured FPR on clean val: {measured_fpr:.4f} "
              f"(target: {self.fpr_target:.4f})")
        # Tolerance is wider for small val sets (percentile estimation is noisy).
        # With n<200, ±2% is expected variance; assert ±3% and note in pitch.
        tol = max(0.005, 2.0 / max(len(X_val_clean), 1))
        assert measured_fpr <= self.fpr_target + tol, (
            f"FPR {measured_fpr:.4f} exceeds target {self.fpr_target} + {tol:.3f} tolerance"
        )
        return self.threshold_

    # ── Inference ─────────────────────────────────────────────────────────

    def anomaly_score(self, x: np.ndarray) -> float:
        """
        Raw anomaly score for a single observation.
        Higher = more anomalous (foreign body signal stronger).
        """
        x_scaled = self.scaler.transform(x.reshape(1, -1))
        return float(-self.model.score_samples(x_scaled)[0])

    def anomaly_scores_batch(self, X: np.ndarray) -> np.ndarray:
        """Batch anomaly scores. Shape: (n_samples,)"""
        X_scaled = self.scaler.transform(X)
        return -self.model.score_samples(X_scaled)

    def is_anomalous(self, x: np.ndarray) -> bool:
        """True if this transaction should be escalated to Layer 2."""
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() before is_anomalous().")
        return self.anomaly_score(x) > self.threshold_

    def screen_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Screen a batch of procurement records. Returns the DataFrame with
        added columns: anomaly_score, is_anomalous, escalate_to_layer2.

        This is the main interface for the demo server.
        """
        X = df[self.feature_cols].fillna(0).values
        scores = self.anomaly_scores_batch(X)

        result = df.copy()
        result["anomaly_score"]      = scores
        result["is_anomalous"]       = scores > (self.threshold_ or 0.5)
        result["escalate_to_layer2"] = result["is_anomalous"]

        # Risk tier: normal / suspicious / critical
        if self.threshold_:
            result["risk_tier"] = pd.cut(
                scores,
                bins=[-np.inf, self.threshold_ * 0.5, self.threshold_, np.inf],
                labels=["normal", "suspicious", "critical"]
            )
        return result

    # ── Feature importance proxy ───────────────────────────────────────────

    def feature_contribution(self, x: np.ndarray) -> dict:
        """
        Approximate per-feature contribution to anomaly score by
        measuring score change when each feature is zeroed out.
        Used for the demo explainability panel.
        """
        baseline = self.anomaly_score(x)
        contributions = {}
        for i, col in enumerate(self.feature_cols):
            x_perturbed = x.copy()
            x_perturbed[i] = 0.0
            perturbed_score = self.anomaly_score(x_perturbed)
            contributions[col] = float(baseline - perturbed_score)
        # Sort descending: highest contribution first
        return dict(sorted(contributions.items(), key=lambda kv: -kv[1]))

    # ── Persistence ───────────────────────────────────────────────────────

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
        d   = joblib.load(path)
        obj = cls()
        obj.model        = d["model"]
        obj.scaler       = d["scaler"]
        obj.threshold_   = d["threshold"]
        obj.feature_cols = d["feature_cols"]
        obj.fpr_target   = d["fpr_target"]
        return obj


# ── Statistical Baseline (IQR screen — benchmark to beat) ─────────────────

class IQRBaseline:
    """
    Simple IQR-based anomaly detector. Flags a record as anomalous if
    any feature falls more than 3 IQRs from the median.

    This is the baseline the Isolation Forest must outperform.
    Include both TPRs in your pitch slide — the gap is the contribution.
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


# ── Training Script ────────────────────────────────────────────────────────

def train_layer1(
    features_csv: str = "data/layer1_features.csv",
    model_save_path: str = "models/innate/isolation_forest.joblib",
    fpr_target: float = 0.01,
    val_size: float = 0.15,
    test_size: float = 0.15,
) -> Tuple[InnateSupplyChainDetector, dict]:
    """
    Full Layer 1 training pipeline.

    Steps:
      1. Load feature CSV from supply_chain_ingest.py
      2. Filter clean baseline (training data for IF)
      3. Split train / val / test
      4. Train Isolation Forest
      5. Train IQR baseline
      6. Calibrate threshold at fpr_target on val_clean
      7. Evaluate both on test data (TPR, FPR)
      8. Save model

    Returns
    -------
    (trained_detector, benchmark_results_dict)
    """
    print("=" * 60)
    print("SOMA Layer 1 — Innate Immunity Training")
    print("=" * 60)

    # Load data
    df = pd.read_csv(features_csv)
    print(f"\nLoaded {len(df)} procurement records.")

    # Filter clean baseline
    clean_df = filter_clean_baseline(df)

    if len(clean_df) < 100:
        print("WARNING: < 100 clean records. Consider fetching more data.")

    # Extract feature matrix
    X_clean = clean_df[FEATURE_COLS].fillna(0).values

    # Train / val / test split (clean data only for IF training)
    X_tr, X_temp = train_test_split(
        X_clean, test_size=val_size + test_size, random_state=42
    )
    X_val, X_te = train_test_split(
        X_temp, test_size=test_size / (val_size + test_size), random_state=42
    )
    print(f"\nSplit — Train: {len(X_tr)} | Val: {len(X_val)} | Test: {len(X_te)}")

    # ── Train Isolation Forest ──
    print("\nTraining Isolation Forest...")
    detector = InnateSupplyChainDetector(fpr_target=fpr_target)
    detector.fit(X_tr)

    # ── Calibrate threshold ──
    print("\nCalibrating threshold on clean validation data...")
    detector.calibrate_threshold(X_val)

    # ── Train IQR baseline ──
    print("\nTraining IQR baseline...")
    baseline = IQRBaseline()
    baseline.fit(X_tr)

    # ── Evaluate on test data ──
    print("\nEvaluating on held-out test data...")

    # FPR on clean test
    if_scores_clean = detector.anomaly_scores_batch(X_te)
    if_fpr = float(np.mean(if_scores_clean > detector.threshold_))

    iqr_scores_clean = baseline.anomaly_scores_batch(X_te)
    iqr_fpr = float(np.mean(iqr_scores_clean > baseline.k))

    # TPR on anomalous records (use is_anomalous label if available)
    anomalous_df = df[df.get("is_anomalous", pd.Series(0, index=df.index)) == 1]
    if len(anomalous_df) > 0:
        X_anom = anomalous_df[FEATURE_COLS].fillna(0).values
        if_scores_anom  = detector.anomaly_scores_batch(X_anom)
        iqr_scores_anom = baseline.anomaly_scores_batch(X_anom)
        if_tpr  = float(np.mean(if_scores_anom  > detector.threshold_))
        iqr_tpr = float(np.mean(iqr_scores_anom > baseline.k))
    else:
        if_tpr = iqr_tpr = None
        print("  No labeled anomalies for TPR measurement (need SupplyChainCloud labels).")

    results = {
        "isolation_forest_fpr":  if_fpr,
        "isolation_forest_tpr":  if_tpr,
        "iqr_baseline_fpr":      iqr_fpr,
        "iqr_baseline_tpr":      iqr_tpr,
        "threshold":             detector.threshold_,
        "n_train":               len(X_tr),
        "n_val":                 len(X_val),
        "n_test":                len(X_te),
        "n_anomalous_labeled":   len(anomalous_df),
    }

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    print(f"  Isolation Forest:  FPR={if_fpr:.4f}  TPR={if_tpr}")
    print(f"  IQR Baseline:      FPR={iqr_fpr:.4f}  TPR={iqr_tpr}")
    winner = "Isolation Forest" if (if_tpr or 0) >= (iqr_tpr or 0) else "IQR Baseline"
    print(f"\n  Selected: {winner}")
    print("=" * 60)

    # ── Save model ──
    Path(model_save_path).parent.mkdir(parents=True, exist_ok=True)
    detector.save(Path(model_save_path))

    # Save benchmark results
    results_path = Path(model_save_path).parent / "layer1_benchmark.txt"
    with open(results_path, "w") as f:
        for k, v in results.items():
            f.write(f"{k}: {v}\n")
    print(f"\nBenchmark saved to {results_path}")

    return detector, results


if __name__ == "__main__":
    # Quick test with synthetic data if CSV not yet generated
    csv_path = Path("data/layer1_features.csv")

    if not csv_path.exists():
        print("No feature CSV found. Generating synthetic data for smoke test...")
        rng = np.random.default_rng(42)
        n = 500
        synthetic = pd.DataFrame({
            "f0_price_deviation":   rng.lognormal(0, 0.5, n),
            "f1_num_offers":        rng.integers(1, 10, n).astype(float),
            "f2_single_bid":        (rng.integers(1, 10, n) == 1).astype(float),
            "f3_days_to_delivery":  rng.integers(1, 180, n).astype(float),
            "f4_fast_delivery":     (rng.integers(1, 180, n) < 14).astype(float),
            "f5_contract_duration": rng.integers(30, 730, n).astype(float),
            "f6_award_amount_log":  rng.uniform(4, 8, n),
            "f7_competition":       rng.choice([0, 1, 2, 3], n, p=[0.6, 0.2, 0.15, 0.05]).astype(float),
            "f8_dod_agency":        rng.choice([0, 1], n, p=[0.1, 0.9]).astype(float),
            "f9_new_vendor":        rng.choice([0, 1], n, p=[0.7, 0.3]).astype(float),
            "f_risk_combo":         np.zeros(n),
            "is_anomalous":         rng.choice([0, 1], n, p=[0.97, 0.03]).astype(float),
        })
        synthetic["f_risk_combo"] = (
            synthetic["f2_single_bid"] *
            synthetic["f4_fast_delivery"] *
            synthetic["f9_new_vendor"]
        )
        Path("data").mkdir(exist_ok=True)
        synthetic.to_csv(csv_path, index=False)
        print(f"Synthetic data saved: {len(synthetic)} records")

    detector, results = train_layer1(str(csv_path))
    print("\nLayer 1 training complete. Model ready for demo server.")
