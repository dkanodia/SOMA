"""
soma/fusion/network_correlator.py
===================================
Fusion layer — correlates signals from all 5 immune layers into Incidents.

Biological framing:
  The complement system and cytokine network integrate innate and adaptive
  signals into a coordinated immune response. NetworkImmuneCorrelator is
  SOMA's complement: it aggregates per-layer signals into ranked Incidents
  with confidence levels and structured explanations.

Scoring:
  Each layer that fires contributes a weight to a host's incident score.
  Layers: innate (0.30), memory (0.30), tolerance_breach (0.20),
          learned_attacks (0.20).
  Confidence: HIGH ≥ 0.6, MEDIUM ≥ 0.35, LOW ≥ 0.15.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

HOST_NAMES = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]

LAYER_WEIGHTS = {
    "innate":           0.30,
    "memory":           0.30,
    "tolerance_breach": 0.20,
    "learned_attacks":  0.20,
}


# ---------------------------------------------------------------------------
# Incident
# ---------------------------------------------------------------------------

@dataclass
class Incident:
    host:         str
    score:        float
    layers_fired: list
    explanation:  str
    confidence:   str       # "HIGH", "MEDIUM", "LOW"
    attack_type:  str


# ---------------------------------------------------------------------------
# Correlator
# ---------------------------------------------------------------------------

class NetworkImmuneCorrelator:
    """
    Step-by-step fusion of immune layer signals into ranked Incident list.

    Call update_step() once per network observation step.
    Call top_threat() to get the highest-scoring (host, score) pair.
    """

    def __init__(self):
        self._last_incidents: list[Incident] = []
        self._step = 0

    # ------------------------------------------------------------------
    def update_step(
        self,
        obs:                   np.ndarray,
        innate_score:          float,
        innate_threshold:      float,
        memory_scores:         dict,          # {host: float}
        memory_threshold:      float,
        tolerance_suppressed:  list,          # hosts suppressed (tolerated)
        tolerance_breached:    list,          # hosts breaching tolerance
        learned_attack_conf:   float,
        learned_attack_type:   str,
        innate_host_scores:    Optional[dict] = None,  # {host: float}
    ) -> list[Incident]:
        """
        Fuse all layer signals for this step.

        Returns list of Incident objects (may be empty if nothing fires).
        """
        incidents: list[Incident] = []

        innate_fired  = innate_score > innate_threshold
        learned_fired = learned_attack_conf > 0.3

        for host in HOST_NAMES:
            layers_fired  = []
            score         = 0.0

            # Innate contribution (host-level)
            h_innate = (innate_host_scores or {}).get(host, 0.0)
            if innate_fired and (innate_host_scores is None or h_innate > innate_threshold * 0.5):
                layers_fired.append("innate")
                contribution = LAYER_WEIGHTS["innate"]
                # Scale by how much this host contributed
                if innate_host_scores:
                    total = max(sum(innate_host_scores.values()), 1e-9)
                    contribution *= h_innate / total * len(HOST_NAMES)
                score += contribution

            # Memory contribution
            mem_score = memory_scores.get(host, 0.0)
            if memory_threshold and mem_score > memory_threshold:
                layers_fired.append("memory")
                score += LAYER_WEIGHTS["memory"] * min(mem_score / (memory_threshold + 1e-9), 2.0)

            # Tolerance breach
            if host in tolerance_breached:
                layers_fired.append("tolerance_breach")
                score += LAYER_WEIGHTS["tolerance_breach"]

            # Tolerance suppression (reduce score if host is tolerated)
            if host in tolerance_suppressed and "memory" not in layers_fired:
                score *= 0.5

            # Learned attacks (shared signal — add to any host that innate flagged)
            if learned_fired and host in (tolerance_breached or []) or (
                learned_fired and innate_fired and h_innate and
                h_innate == max((innate_host_scores or {host: 1}).values())
            ):
                if "learned_attacks" not in layers_fired:
                    layers_fired.append("learned_attacks")
                score += LAYER_WEIGHTS["learned_attacks"] * learned_attack_conf

            score = min(float(score), 1.0)

            if score < 0.15 or not layers_fired:
                continue

            confidence = (
                "HIGH"   if score >= 0.6  else
                "MEDIUM" if score >= 0.35 else
                "LOW"
            )
            atype = learned_attack_type if learned_fired else "anomaly"
            explanation = self._build_explanation(host, layers_fired, score, mem_score, h_innate)

            incidents.append(Incident(
                host=host,
                score=score,
                layers_fired=layers_fired,
                explanation=explanation,
                confidence=confidence,
                attack_type=atype,
            ))

        incidents.sort(key=lambda i: i.score, reverse=True)
        self._last_incidents = incidents
        self._step += 1
        return incidents

    # ------------------------------------------------------------------
    def top_threat(self) -> Optional[tuple]:
        """Returns (host, score) of highest-scoring incident, or None."""
        if not self._last_incidents:
            return None
        top = self._last_incidents[0]
        return (top.host, top.score)

    # ------------------------------------------------------------------
    @staticmethod
    def _build_explanation(
        host:         str,
        layers_fired: list,
        score:        float,
        mem_score:    float,
        innate_score: float,
    ) -> str:
        parts = []
        if "innate" in layers_fired:
            parts.append(f"fast anomaly (score={innate_score:.2f})")
        if "memory" in layers_fired:
            parts.append(f"drift from baseline (drift={mem_score:.2f})")
        if "tolerance_breach" in layers_fired:
            parts.append("role violation")
        if "learned_attacks" in layers_fired:
            parts.append("matches known attack signature")
        verb = "flagged" if score < 0.5 else "HIGH CONFIDENCE threat"
        return f"{host} {verb}: {', '.join(parts)}"
