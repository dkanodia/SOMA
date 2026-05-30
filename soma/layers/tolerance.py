"""
soma/layers/tolerance.py
=========================
Layer 3 — Immune Tolerance: suppress false positives on known-normal hosts.

Biological framing:
  Self-tolerance prevents the immune system from attacking the body's own
  cells. Central tolerance eliminates self-reactive lymphocytes; peripheral
  tolerance suppresses reactions to normal tissue. SOMA's tolerance layer
  learns which host states are "self" and suppresses innate alarms on them,
  while flagging dramatic role violations.

Mechanism:
  Per-host Gaussian model of normal feature distributions (mean, std).
  - suppressed_hosts: hosts whose current obs is within tolerance (suppress alarm).
  - breach_hosts: hosts with z-score > breach_threshold on any feature.
"""

import numpy as np
import joblib
from pathlib import Path
from typing import Optional

HOST_NAMES        = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]
FEATURES_PER_HOST = 5


class ImmuneToleranceLayer:
    """
    Per-host Gaussian self-tolerance model.

    After calibrate(X_clean), maintains learned mean/std per host.

    suppressed_hosts(obs): hosts currently within tolerance bounds (suppress).
    breach_hosts(obs):     hosts violating role-based z-score threshold.
    """

    def __init__(
        self,
        suppress_sigma:  float = 1.5,
        breach_sigma:    float = 3.0,
    ):
        self.suppress_sigma = suppress_sigma
        self.breach_sigma   = breach_sigma
        self._mean: Optional[np.ndarray] = None  # (n_hosts, features)
        self._std:  Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    def calibrate(self, X_clean: np.ndarray) -> None:
        """
        Fit per-host mean and std from clean observations.
        X_clean: shape (n, 30)
        """
        n = len(HOST_NAMES)
        means, stds = [], []
        for i in range(n):
            start = i * FEATURES_PER_HOST
            h_obs = X_clean[:, start:start + FEATURES_PER_HOST]
            means.append(h_obs.mean(axis=0))
            stds.append(h_obs.std(axis=0) + 1e-4)
        self._mean = np.array(means, dtype=np.float32)
        self._std  = np.array(stds,  dtype=np.float32)
        print(f"[Tolerance] Calibrated on {len(X_clean)} clean steps, {n} hosts")

    # ------------------------------------------------------------------
    def _host_zscore(self, obs: np.ndarray, host_idx: int) -> float:
        """Max abs z-score across features for a single host."""
        if self._mean is None:
            return 0.0
        start = host_idx * FEATURES_PER_HOST
        x     = obs[start:start + FEATURES_PER_HOST]
        z     = np.abs((x - self._mean[host_idx]) / self._std[host_idx])
        return float(z.max())

    def suppressed_hosts(self, obs: np.ndarray) -> list:
        """Hosts within tolerance — suppress innate alarm for these."""
        if self._mean is None:
            return []
        result = []
        for i, host in enumerate(HOST_NAMES):
            if self._host_zscore(obs, i) <= self.suppress_sigma:
                result.append(host)
        return result

    def breach_hosts(self, obs: np.ndarray) -> list:
        """Hosts breaching tolerance — role violation, flag regardless."""
        if self._mean is None:
            return []
        result = []
        for i, host in enumerate(HOST_NAMES):
            if self._host_zscore(obs, i) >= self.breach_sigma:
                result.append(host)
        return result

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        joblib.dump({"mean": self._mean, "std": self._std,
                     "suppress_sigma": self.suppress_sigma,
                     "breach_sigma": self.breach_sigma}, path)

    @classmethod
    def load(cls, path: Path) -> "ImmuneToleranceLayer":
        d   = joblib.load(path)
        obj = cls(d["suppress_sigma"], d["breach_sigma"])
        obj._mean = d["mean"]
        obj._std  = d["std"]
        return obj
