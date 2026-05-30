"""
soma/layers/memory.py
======================
Layer 4 — Immune Memory: host behavior drift detection.

Biological framing:
  Memory T-cells remember what a healthy cell looks like. When a host's
  behavior gradually drifts from its early-episode baseline (the
  "immune memory snapshot"), the memory layer fires: "I remember what
  this host used to look like — something is wrong now."

  Key advantage over a running EMA: the baseline does NOT drift with
  the attacker. Even a slow, low-and-slow intrusion accumulates drift
  against the frozen early-episode snapshot.

Mechanism:
  Per-host: freeze the first `memory_k` observations as the snapshot.
  Compare snapshot centroid against rolling recent centroid (last `recent_k`).
  Drift = PCA-projected centroid distance (or plain L2 in feature space).

Calibration: threshold at 95th percentile of clean-episode drift scores.
"""

import numpy as np
from collections import defaultdict
from typing import Optional


# ---------------------------------------------------------------------------
# Per-host memory tracker
# ---------------------------------------------------------------------------

class _HostMemory:
    """
    Fixed early window vs rolling recent window per host.
    drift_score() returns the L2 distance between their centroids.
    """

    def __init__(self, memory_k: int = 10, recent_k: int = 10):
        self._memory_k    = memory_k
        self._recent_k    = recent_k
        self._memory_buf: list[np.ndarray] = []   # frozen after memory_k obs
        self._recent_buf: list[np.ndarray] = []   # rolling window
        self._memory_frozen = False

    def update(self, feat: np.ndarray) -> Optional[float]:
        """
        Add one host observation. Returns drift score once both windows
        are ready; None during warm-up.
        """
        if not self._memory_frozen:
            self._memory_buf.append(feat.copy())
            if len(self._memory_buf) >= self._memory_k:
                self._memory_frozen = True
            return None

        self._recent_buf.append(feat.copy())
        if len(self._recent_buf) > self._recent_k:
            self._recent_buf.pop(0)

        if len(self._recent_buf) < max(3, self._recent_k // 2):
            return None

        return self._compute_drift()

    def _compute_drift(self) -> float:
        mem_mu    = np.mean(self._memory_buf, axis=0)
        recent_mu = np.mean(self._recent_buf, axis=0)
        # Normalize by memory std so all features contribute equally
        mem_std   = np.std(self._memory_buf, axis=0).clip(1e-4)
        return float(np.linalg.norm((recent_mu - mem_mu) / mem_std))

    def drift_score(self) -> Optional[float]:
        """Current drift (read-only, normalised). None if not ready."""
        if not self._memory_frozen or len(self._recent_buf) < 3:
            return None
        return self._compute_drift()


    @property
    def ready(self) -> bool:
        return self._memory_frozen and len(self._recent_buf) >= 3

    def reset(self) -> None:
        self._memory_buf.clear()
        self._recent_buf.clear()
        self._memory_frozen = False


# ---------------------------------------------------------------------------
# Public layer
# ---------------------------------------------------------------------------

class HostDriftLayer:
    """
    Per-host immune memory drift detector for network intrusion.

    Each host gets an independent memory tracker. The layer fires when
    a host's recent behavior diverges significantly from its early-episode
    baseline — catching slow, persistent intrusions that evade fast detectors.

    Usage:
        mem = HostDriftLayer()
        mem.calibrate_threshold(X_clean_episodes)
        for obs in stream:
            scores = mem.update_and_scores(obs)   # dict[host → score]
            fired  = mem.alarm_hosts(obs)          # list of hosts that fired
    """

    def __init__(
        self,
        memory_k:   int   = 10,   # observations to freeze as snapshot
        recent_k:   int   = 10,   # rolling recent window size
        fpr_target: float = 0.05,
    ):
        self.memory_k   = memory_k
        self.recent_k   = recent_k
        self.fpr_target = fpr_target
        self.threshold_: Optional[float] = None
        self._hosts: dict[str, _HostMemory] = {}

    def _get_host(self, host: str) -> _HostMemory:
        if host not in self._hosts:
            self._hosts[host] = _HostMemory(self.memory_k, self.recent_k)
        return self._hosts[host]

    # ------------------------------------------------------------------
    def _split_obs(self, obs: np.ndarray) -> dict[str, np.ndarray]:
        """Split 30-dim obs into per-host 5-dim vectors."""
        from soma.envs.cyborg_wrapper import HOST_NAMES, FEATURES_PER_HOST
        result = {}
        for i, h in enumerate(HOST_NAMES):
            start = i * FEATURES_PER_HOST
            result[h] = obs[start:start + FEATURES_PER_HOST]
        return result

    # ------------------------------------------------------------------
    def update(self, obs: np.ndarray) -> dict[str, Optional[float]]:
        """Update all hosts; return per-host drift scores (None if warming up)."""
        per_host = self._split_obs(obs)
        return {h: self._get_host(h).update(feat) for h, feat in per_host.items()}

    def drift_scores(self) -> dict[str, float]:
        """Current drift scores for all ready hosts (0.0 if not ready)."""
        return {h: (m.drift_score() or 0.0) for h, m in self._hosts.items()}

    def update_and_scores(self, obs: np.ndarray) -> dict[str, float]:
        """Update then return current drift scores."""
        self.update(obs)
        return self.drift_scores()

    def alarm_hosts(self, obs: np.ndarray) -> list[str]:
        """Update and return list of hosts whose drift exceeds threshold."""
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() first.")
        scores = self.update_and_scores(obs)
        return [h for h, s in scores.items() if s > self.threshold_]

    def max_drift_score(self, obs: np.ndarray) -> float:
        """Max drift score across all hosts after update."""
        scores = self.update_and_scores(obs)
        vals = list(scores.values())
        return float(max(vals)) if vals else 0.0

    # ------------------------------------------------------------------
    def calibrate_threshold(
        self,
        X_clean: np.ndarray,
        fpr_target: Optional[float] = None,
    ) -> float:
        """
        Set drift threshold from clean episodes.
        X_clean: shape (T, 30) — multiple clean-episode steps concatenated.
        """
        fpr = fpr_target or self.fpr_target
        cal_hosts: dict[str, _HostMemory] = {}

        from soma.envs.cyborg_wrapper import HOST_NAMES, FEATURES_PER_HOST
        for h in HOST_NAMES:
            cal_hosts[h] = _HostMemory(self.memory_k, self.recent_k)

        scores = []
        for obs in X_clean:
            for i, h in enumerate(HOST_NAMES):
                start = i * FEATURES_PER_HOST
                feat  = obs[start:start + FEATURES_PER_HOST]
                d     = cal_hosts[h].update(feat)
                if d is not None:
                    scores.append(d)

        if not scores:
            self.threshold_ = 1.0
            return self.threshold_

        self.threshold_ = float(np.percentile(scores, (1 - fpr) * 100))
        print(f"[Memory] Drift threshold={self.threshold_:.4f}  "
              f"(calibrated at {(1-fpr)*100:.0f}th pct of {len(scores)} clean scores)")
        return self.threshold_

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset all host memories (call at episode start)."""
        self._hosts.clear()
