"""
soma/layers/tolerance.py
=========================
Layer 3 — Immune Tolerance: host role-based behavior suppression.

Biological framing:
  The immune system is "tolerant" of self — it knows the body's own
  cells and does not attack them. For SOMA, tolerance means knowing that
  a server (Enterprise0) with high session counts is NORMAL, not an attack.
  The tolerance layer suppresses alarms when a host is behaving within
  its role expectations, even if it looks anomalous to the generic
  innate detector.

Mechanism:
  1. Define role baselines from clean CybORG data:
     - workstation (User0/1/2): low activity, 1-2 sessions, few processes
     - server (Enterprise0/1): medium-high activity, many sessions
     - critical (Op_Server0): low-medium activity, controlled sessions
  2. Z-score each host's observation against its role baseline.
  3. If z-score < threshold AND only innate fires → suppress alarm.
  4. If z-score is HIGH → tolerance breach → escalate regardless.

This prevents false positives on servers that are legitimately busy.
"""

import numpy as np
from typing import Optional

from soma.envs.cyborg_wrapper import HOST_NAMES, FEATURES_PER_HOST


# ---------------------------------------------------------------------------
# Role baselines: (mean, std) per feature for each role
#   features: [activity, compromised, sessions, processes, network_pos]
# ---------------------------------------------------------------------------

_ROLE_BASELINE: dict[str, np.ndarray] = {
    "workstation": np.array([
        [0.15, 0.06],   # activity
        [0.00, 0.01],   # compromised
        [1.50, 0.70],   # sessions
        [4.00, 1.20],   # processes
        [0.20, 0.12],   # network_pos
    ]),
    "server": np.array([
        [0.43, 0.12],
        [0.00, 0.01],
        [5.75, 1.80],
        [11.5, 2.80],
        [0.60, 0.08],
    ]),
    "critical": np.array([
        [0.25, 0.06],
        [0.00, 0.01],
        [3.00, 1.00],
        [7.00, 1.50],
        [0.90, 0.02],
    ]),
}

HOST_ROLE = {
    "User0": "workstation", "User1": "workstation", "User2": "workstation",
    "Enterprise0": "server", "Enterprise1": "server",
    "Op_Server0": "critical",
}


# ---------------------------------------------------------------------------
# Tolerance layer
# ---------------------------------------------------------------------------

class ImmuneToleranceLayer:
    """
    Host role-based alarm suppressor.

    A host behaving within role expectations gets its alarm suppressed.
    A host deviating significantly from its role baseline gets escalated.

    Usage:
        tol = ImmuneToleranceLayer()
        tol.calibrate(X_clean)
        for obs in stream:
            suppressed = tol.suppressed_hosts(obs)   # set of host names
            breach     = tol.breach_hosts(obs)        # set flagging role deviation
    """

    def __init__(
        self,
        suppress_thresh: Optional[float] = None,  # z-score below = suppress
        breach_thresh:   Optional[float] = None,  # z-score above = breach
        fpr_target:      float           = 0.05,
    ):
        self.suppress_thresh = suppress_thresh
        self.breach_thresh   = breach_thresh
        self.fpr_target      = fpr_target

    # ------------------------------------------------------------------
    def host_zscore(self, host: str, feat: np.ndarray) -> float:
        """L2 z-score of host feature against its role baseline."""
        role = HOST_ROLE.get(host, "workstation")
        bl   = _ROLE_BASELINE[role]
        mu   = bl[:, 0]
        std  = bl[:, 1].clip(1e-6)
        return float(np.linalg.norm((feat - mu) / std))

    def obs_zscores(self, obs: np.ndarray) -> dict[str, float]:
        """Per-host z-scores from a full 30-dim observation."""
        result = {}
        for i, h in enumerate(HOST_NAMES):
            start     = i * FEATURES_PER_HOST
            result[h] = self.host_zscore(h, obs[start:start + FEATURES_PER_HOST])
        return result

    # ------------------------------------------------------------------
    def suppressed_hosts(self, obs: np.ndarray) -> set[str]:
        """
        Hosts whose z-score is below suppress_thresh — alarm is suppressed.
        These hosts are behaving within role expectations.
        """
        if self.suppress_thresh is None:
            return set()
        zs = self.obs_zscores(obs)
        return {h for h, z in zs.items() if z < self.suppress_thresh}

    def breach_hosts(self, obs: np.ndarray) -> set[str]:
        """
        Hosts whose z-score exceeds breach_thresh — role tolerance violated.
        These hosts should be escalated regardless of innate score.
        """
        if self.breach_thresh is None:
            return set()
        zs = self.obs_zscores(obs)
        return {h for h, z in zs.items() if z > self.breach_thresh}

    def is_suppressed(self, host: str, obs: np.ndarray) -> bool:
        """True if this host is within role tolerance (suppress alarm)."""
        if self.suppress_thresh is None:
            return False
        i    = HOST_NAMES.index(host)
        feat = obs[i * FEATURES_PER_HOST:(i + 1) * FEATURES_PER_HOST]
        return self.host_zscore(host, feat) < self.suppress_thresh

    # ------------------------------------------------------------------
    def calibrate(
        self,
        X_clean: np.ndarray,
        fpr_target: Optional[float] = None,
    ) -> "ImmuneToleranceLayer":
        """
        Set suppress and breach thresholds from clean data.
        suppress_thresh = 50th percentile (within normal = suppress)
        breach_thresh   = (1 - fpr_target) * 100th percentile
        """
        fpr = fpr_target or self.fpr_target
        all_zs = []
        for obs in X_clean:
            for i, h in enumerate(HOST_NAMES):
                start = i * FEATURES_PER_HOST
                feat  = obs[start:start + FEATURES_PER_HOST]
                all_zs.append(self.host_zscore(h, feat))

        self.suppress_thresh = float(np.percentile(all_zs, 50))
        self.breach_thresh   = float(np.percentile(all_zs, (1 - fpr) * 100))
        print(f"[Tolerance] suppress_thresh={self.suppress_thresh:.3f}  "
              f"breach_thresh={self.breach_thresh:.3f}")
        return self
