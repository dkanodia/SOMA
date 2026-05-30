"""
soma/layers/suppressor.py
==========================
Layer 4 — Long-Dwell Drift Detection.

NOTE ON NAMING: "Tumor suppressor" was the original name. Biological tumor
suppressors are genetic mechanisms — not surveillance systems. The function
here (detecting slow behavioural drift) has no mechanistic analogy to them.
Renamed to avoid biological comparisons the implementation cannot survive.

What this does:
  Tracks the 2D PCA centroid of each host's behavioural feature vectors
  over a rolling 100-episode window. A host whose centroid drifts significantly
  from its early-window position triggers a long-dwell alarm.

Why Layer 1 misses this:
  The dual-timescale EMA adapts to recent baseline. Slow drift (2% per step
  over 60 steps) falls within the fast-EMA's normal range. The long-dwell
  detector compares early-window to late-window centroid — it cannot adapt away.

FPR budget: 0.1% (strict — these alarms should be rare)
  Calibrated on clean long-run episodes (see soma/eval/fpr_calibration.py).
  MUST call calibrate_threshold() on clean data before drift_alarm().

Limitation:
  Requires 100+ clean episodes before calibration is valid. In a hackathon
  demo, inject the drift manually to show the mechanism — state this in the pitch.
"""

import numpy as np
from collections import defaultdict
from sklearn.decomposition import PCA
from pathlib import Path
from typing import Optional
import joblib


class LongDwellDetector:
    """
    PCA-based centroid drift detector with calibrated FPR threshold.

    Parameters
    ----------
    window : int
        Max history length per host (rolling).
    n_components : int
        PCA dimensions for visualisation and drift measurement.
    fpr_target : float
        Target false positive rate. Threshold set via calibrate_threshold().
    """

    def __init__(
        self,
        window: int       = 500,
        n_components: int = 2,
        fpr_target: float = 0.001,
    ):
        self.window       = window
        self.n_components = n_components
        self.fpr_target   = fpr_target

        self.history: dict[str, list] = defaultdict(list)
        self.pca              = PCA(n_components=n_components)
        self.fitted:  bool    = False
        self.threshold_: Optional[float] = None   # set by calibrate_threshold()

    # ------------------------------------------------------------------
    def update(self, host: str, feature_vec: np.ndarray) -> None:
        """Add a feature observation for a host."""
        self.history[host].append(feature_vec.copy())
        if len(self.history[host]) > self.window:
            self.history[host].pop(0)

    def update_all(self, host_features: dict[str, np.ndarray]) -> None:
        """Convenience: update all hosts from a {host: vec} dict."""
        for host, vec in host_features.items():
            self.update(host, vec)

    # ------------------------------------------------------------------
    def fit_pca(self) -> bool:
        """Fit PCA on all accumulated history. Returns True if enough data."""
        all_vecs = [v for vlist in self.history.values() for v in vlist]
        if len(all_vecs) < 50:
            return False
        self.pca.fit(np.vstack(all_vecs))
        self.fitted = True
        return True

    # ------------------------------------------------------------------
    def calibrate_threshold(
        self,
        clean_histories: dict[str, list],
        fpr_target: Optional[float] = None,
    ) -> float:
        """
        Set drift threshold so FPR on clean hosts = fpr_target.

        Parameters
        ----------
        clean_histories : dict
            {host_id: [feature_vec, ...]} from clean (no red agent) episodes.
        fpr_target : float, optional
            Override self.fpr_target.

        Returns
        -------
        float: calibrated threshold.
        """
        fpr = fpr_target or self.fpr_target
        for host, hist in clean_histories.items():
            self.history[host] = list(hist)

        if not self.fit_pca():
            raise RuntimeError("Not enough clean data to fit PCA. Need >= 50 vectors.")

        drift_scores = []
        for host in clean_histories:
            d = self._compute_drift(host)
            if d is not None:
                drift_scores.append(d)

        if not drift_scores:
            raise RuntimeError("Could not compute drift for any host. Check window size.")

        # Threshold = (1 - fpr)-th percentile of clean drift scores
        self.threshold_ = float(np.percentile(drift_scores, (1.0 - fpr) * 100))
        measured_fpr = sum(d > self.threshold_ for d in drift_scores) / len(drift_scores)
        assert measured_fpr <= fpr + 0.001, \
            f"FPR calibration failed: measured {measured_fpr:.4f} > target {fpr:.4f}"
        return self.threshold_

    # ------------------------------------------------------------------
    def drift_alarm(self, host: str) -> bool:
        """
        True if host's centroid has drifted beyond calibrated threshold.
        Raises RuntimeError if calibrate_threshold() has not been called.
        """
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() on clean data before alarming.")
        if not self.fitted:
            return False
        d = self._compute_drift(host)
        return d is not None and d > self.threshold_

    def _compute_drift(self, host: str) -> Optional[float]:
        """L2 distance between early-window and late-window centroid in PCA space."""
        hist = self.history.get(host, [])
        min_len = 50
        if len(hist) < min_len or not self.fitted:
            return None

        early = np.mean(hist[:min_len // 2], axis=0)
        late  = np.mean(hist[-min_len // 2:], axis=0)

        early_2d = self.pca.transform(early.reshape(1, -1))[0]
        late_2d  = self.pca.transform(late.reshape(1, -1))[0]
        return float(np.linalg.norm(late_2d - early_2d))

    # ------------------------------------------------------------------
    def centroid_trajectory(self, host: str, step_size: int = 10) -> list[np.ndarray]:
        """2D PCA trajectory of centroid over time — for visualisation."""
        hist = self.history.get(host, [])
        if len(hist) < 50 or not self.fitted:
            return []
        trajectory = []
        for i in range(25, len(hist), step_size):
            c    = np.mean(hist[max(0, i - 25): i], axis=0)
            c_2d = self.pca.transform(c.reshape(1, -1))[0]
            trajectory.append(c_2d)
        return trajectory

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        joblib.dump({
            "pca": self.pca, "fitted": self.fitted,
            "threshold": self.threshold_, "window": self.window,
        }, path)

    @classmethod
    def load(cls, path: Path) -> "LongDwellDetector":
        obj = cls()
        d = joblib.load(path)
        obj.pca        = d["pca"]
        obj.fitted     = d["fitted"]
        obj.threshold_ = d["threshold"]
        obj.window     = d["window"]
        return obj
