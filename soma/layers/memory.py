"""
soma/layers/memory.py
======================
Layer 4 — Immunological Memory: per-host drift detection.

Biological framing:
  Memory B-cells remember past self and recognize when the body has changed.
  HostDriftLayer maintains a rolling recent window per host and computes
  drift as the z-score distance from the calibrated clean baseline.
  Catches slow, stealthy attackers that evade the fast innate layer.

Mechanism:
  Per-host rolling mean (recent_k steps) vs stored clean baseline (mean, std).
  Drift score = mean(|rolling_mean - clean_mean| / clean_std).
  Threshold calibrated at target FPR on clean data.
"""

import numpy as np
from collections import deque
from typing import Optional
import joblib
from pathlib import Path

HOST_NAMES        = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]
FEATURES_PER_HOST = 5


class HostDriftLayer:
    """
    Per-host drift detector: rolling window vs clean baseline z-score.

    Parameters
    ----------
    memory_k  : int   Length of the rolling observation buffer per host.
    recent_k  : int   Alias for memory_k (kept for API compatibility).
    fpr_target: float Target false positive rate on clean data.
    """

    def __init__(
        self,
        memory_k:   int   = 10,
        recent_k:   int   = 10,
        fpr_target: float = 0.05,
    ):
        self.memory_k   = max(memory_k, recent_k)
        self.recent_k   = max(memory_k, recent_k)
        self.fpr_target = fpr_target
        self.threshold_: Optional[float] = None

        # Per-host rolling buffers
        n = len(HOST_NAMES)
        self._buffers = [deque(maxlen=self.memory_k) for _ in range(n)]

        # Baseline (set during calibrate_threshold)
        self._baseline_mean: Optional[np.ndarray] = None   # (n, FEATURES_PER_HOST)
        self._baseline_std:  Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    def _host_drift(self, host_idx: int, x: np.ndarray) -> float:
        """Z-score distance of current rolling mean from clean baseline."""
        buf = self._buffers[host_idx]
        buf.append(x.copy())

        # Auto-build baseline from the first memory_k observations if not pre-set.
        # This lets episode-scoped detectors (no pre-loaded baseline) work correctly.
        if self._baseline_mean is None:
            if len(buf) < self.memory_k:
                return 0.0
            # Freeze baseline after first window
            arr = np.array(buf)
            n   = len(HOST_NAMES)
            if self._baseline_mean is None:
                self._baseline_mean = np.zeros((n, FEATURES_PER_HOST), dtype=np.float64)
                self._baseline_std  = np.ones((n, FEATURES_PER_HOST),  dtype=np.float64) * 1e-4
            self._baseline_mean[host_idx] = arr.mean(axis=0)
            self._baseline_std[host_idx]  = arr.std(axis=0) + 1e-4

        if len(buf) < 2:
            return 0.0

        recent_mean = np.mean(np.array(buf), axis=0)
        std         = self._baseline_std[host_idx] + 1e-6
        z           = np.abs(recent_mean - self._baseline_mean[host_idx]) / std
        return float(np.mean(z))

    def update_and_scores(self, obs: np.ndarray) -> dict:
        """
        Update per-host buffers and return drift scores.

        Returns
        -------
        dict {host_name: drift_score}  — higher = more drift from baseline.
        """
        obs    = obs.astype(np.float64)
        scores = {}
        for i, host in enumerate(HOST_NAMES):
            start = i * FEATURES_PER_HOST
            x     = obs[start:start + FEATURES_PER_HOST]
            scores[host] = self._host_drift(i, x)
        return scores

    # ------------------------------------------------------------------
    def calibrate_threshold(self, X_clean: np.ndarray) -> float:
        """
        1. Compute per-host clean baseline (mean, std) from X_clean.
        2. Run X_clean through the detector to collect drift scores.
        3. Set threshold at (1-fpr_target) percentile.
        """
        n    = len(HOST_NAMES)
        dims = FEATURES_PER_HOST

        # Compute per-host baseline
        means, stds = [], []
        for i in range(n):
            start = i * dims
            h_obs = X_clean[:, start:start + dims]
            means.append(h_obs.mean(axis=0))
            stds.append(h_obs.std(axis=0) + 1e-4)
        self._baseline_mean = np.array(means, dtype=np.float64)
        self._baseline_std  = np.array(stds,  dtype=np.float64)

        # Reset buffers
        self._buffers = [deque(maxlen=self.memory_k) for _ in range(n)]

        # Collect drift scores on clean data
        all_scores = []
        for obs in X_clean:
            sc = self.update_and_scores(obs)
            all_scores.extend(sc.values())

        self.threshold_ = float(np.percentile(all_scores, (1 - self.fpr_target) * 100))
        measured = float(np.mean([s > self.threshold_ for s in all_scores]))
        print(f"[Memory] Threshold={self.threshold_:.4f}  FPR={measured:.4f} (target {self.fpr_target})")

        # Reset buffers again so detector starts fresh for live use
        self._buffers = [deque(maxlen=self.memory_k) for _ in range(n)]
        return self.threshold_

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        joblib.dump({
            "memory_k":       self.memory_k,
            "recent_k":       self.recent_k,
            "fpr_target":     self.fpr_target,
            "threshold":      self.threshold_,
            "baseline_mean":  self._baseline_mean,
            "baseline_std":   self._baseline_std,
        }, path)

    @classmethod
    def load(cls, path: Path) -> "HostDriftLayer":
        d   = joblib.load(path)
        obj = cls(d.get("memory_k", 10), d.get("recent_k", 10), d.get("fpr_target", 0.05))
        obj.threshold_      = d.get("threshold")
        obj._baseline_mean  = d.get("baseline_mean")
        obj._baseline_std   = d.get("baseline_std")
        return obj
