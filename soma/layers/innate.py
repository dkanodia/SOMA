"""
soma/layers/innate.py
======================
Layer 1 — Innate Immunity: fast, non-specific anomaly detection.

Biological framing:
  The innate immune system has pattern-recognition receptors (PRRs) that
  detect anything foreign — without needing to have seen this specific
  pathogen before. SOMA's innate layer learns "self" (normal host behavior)
  from clean network episodes and flags anything that deviates.

Mechanism:
  Isolation Forest trained on clean CybORG observations.
  Input: 30-dim flat observation (6 hosts × 5 features).
  Output: per-observation anomaly score; threshold at 1% FPR.

Why Isolation Forest:
  - Unsupervised: no attack labels needed during training
  - Linear-time: O(n log n), runs in real time
  - Naturally handles multimodal "self" distributions (different host roles)
  - Robust to high-dimensional, mixed-type features
"""

import numpy as np
import joblib
from pathlib import Path
from typing import Optional
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from soma.envs.cyborg_wrapper import HOST_NAMES, FEATURES_PER_HOST, N_HOSTS


OBS_DIM = N_HOSTS * FEATURES_PER_HOST


class InnateImmunityLayer:
    """
    Isolation Forest anomaly detector for network host behavior.

    Trained once on clean episodes (include_red=False).
    Detects deviations from learned "self" at each network step.

    Usage:
        layer = InnateImmunityLayer()
        layer.fit(X_clean)
        layer.calibrate_threshold(X_val_clean)
        for obs in stream:
            if layer.is_anomalous(obs):
                escalate(obs)
    """

    def __init__(
        self,
        n_estimators:  int   = 200,
        contamination: float = 0.01,
        fpr_target:    float = 0.01,
        random_state:  int   = 42,
    ):
        self.n_estimators  = n_estimators
        self.contamination = contamination
        self.fpr_target    = fpr_target
        self._model        = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
            n_jobs=-1,
        )
        self._scaler        = StandardScaler()
        self.threshold_: Optional[float] = None
        self._fitted        = False

    # ------------------------------------------------------------------
    def fit(self, X_clean: np.ndarray, jitter: float = 0.0) -> "InnateImmunityLayer":
        """
        Train on clean network observations.
        X_clean: shape (n, 30) — concatenated host features.

        jitter: std of Gaussian noise added before fitting. Use 1e-4 on
        CybORG clean data, which is near-zero-variance — without jitter the
        Isolation Forest cannot find meaningful splits and scores degenerate.
        """
        if jitter > 0.0:
            rng = np.random.default_rng(42)
            X_clean = X_clean + rng.normal(0, jitter, X_clean.shape).astype(X_clean.dtype)
        self._scaler.fit(X_clean)
        X_s = self._scaler.transform(X_clean)
        self._model.fit(X_s)
        self._fitted = True
        return self

    def calibrate_threshold(self, X_val_clean: np.ndarray) -> float:
        """
        Set threshold so FPR on clean validation data ≈ fpr_target.
        Scores: higher = more anomalous (negated IF score).
        """
        scores = self._scores(X_val_clean)
        self.threshold_ = float(np.percentile(scores, (1 - self.fpr_target) * 100))
        measured = float(np.mean(scores > self.threshold_))
        print(f"[Innate] Threshold={self.threshold_:.4f}  "
              f"FPR={measured:.4f} (target {self.fpr_target})")
        return self.threshold_

    # ------------------------------------------------------------------
    def anomaly_score(self, obs: np.ndarray) -> float:
        """Single-observation anomaly score. Higher = more anomalous."""
        return float(self._scores(obs.reshape(1, -1))[0])

    def anomaly_scores_batch(self, X: np.ndarray) -> np.ndarray:
        """Batch anomaly scores. Shape (n,)."""
        return self._scores(X)

    def is_anomalous(self, obs: np.ndarray) -> bool:
        """True if obs exceeds calibrated threshold."""
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() first.")
        return self.anomaly_score(obs) > self.threshold_

    def per_host_scores(self, obs: np.ndarray) -> dict[str, float]:
        """
        Per-host anomaly scores via leave-one-out ablation.
        Useful for the demo — identifies which host is suspicious.
        """
        base = self.anomaly_score(obs)
        result = {}
        for i, host in enumerate(HOST_NAMES):
            start = i * FEATURES_PER_HOST
            obs_masked        = obs.copy()
            obs_masked[start:start + FEATURES_PER_HOST] = 0.0
            result[host] = max(0.0, base - self.anomaly_score(obs_masked))
        return result

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model":      self._model,
            "scaler":     self._scaler,
            "threshold":  self.threshold_,
            "fpr_target": self.fpr_target,
        }, path)
        print(f"[Innate] Saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "InnateImmunityLayer":
        d   = joblib.load(path)
        obj = cls(fpr_target=d["fpr_target"])
        obj._model      = d["model"]
        obj._scaler     = d["scaler"]
        obj.threshold_  = d["threshold"]
        obj._fitted     = True
        return obj

    # ------------------------------------------------------------------
    def _scores(self, X: np.ndarray) -> np.ndarray:
        X_s = self._scaler.transform(X)
        return -self._model.score_samples(X_s)
