"""
soma/layers/explainer.py
========================
Feature attribution — WHY did each immune layer fire?

Biological framing:
  Dendritic cells present antigens to T-cells with full context:
  "This specific protein on this specific cell triggered the alarm."
  The explainer mirrors this: for each alarm, it surfaces the specific
  features and hosts that drove each layer's detection.

Methods:
  - Innate (Layer 1): leave-one-out host ablation — which host's
    anomaly score contributed most to the global anomaly?
  - Memory (Layer 4): rank hosts by normalized drift from baseline.
  - Tolerance (Layer 3): hosts with role-violating z-scores.
  - Learned (Layer 5): cosine similarity to gallery + reconstruction error.

Output: per-layer explanation dict (structured + human-readable reason).
Used by export_demo_cyber.py and frontend incident cards.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


FEATURE_NAMES    = ["activity", "compromised", "sessions", "processes", "network_pos"]
HOST_NAMES       = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]
FEATURES_PER_HOST = 5


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LayerExplanation:
    layer:        str
    top_hosts:    list[tuple[str, float]]    # (host, contribution_score)
    top_features: list[tuple[str, float]]   # (feature_name, value)
    reason:       str                        # human-readable summary


def _expl_to_dict(e: LayerExplanation) -> dict:
    return {
        "layer":        e.layer,
        "top_hosts":    [{"host": h, "score": round(s, 4)} for h, s in e.top_hosts],
        "top_features": [{"name": n, "value": round(v, 4)} for n, v in e.top_features],
        "reason":       e.reason,
    }


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class ImmuneExplainer:
    """
    Produces structured + human-readable explanations for each immune layer.

    Usage:
        exp = ImmuneExplainer()
        step_expl = exp.explain_step(
            obs, host_innate_scores, innate_threshold,
            drift_scores, memory_threshold,
            tolerance_suppressed, tolerance_breached,
            la_conf, la_type,
        )
        # Returns {innate, memory, tolerance, learned_attacks} dicts
    """

    # ------------------------------------------------------------------
    def explain_innate(
        self,
        obs: np.ndarray,
        host_scores: dict[str, float],
        threshold: float,
    ) -> LayerExplanation:
        """
        Rank hosts by leave-one-out anomaly contribution.
        Highlight the top host's most deviant raw features.
        """
        if not host_scores:
            return LayerExplanation("innate", [], [], "No host scores available")

        sorted_hosts = sorted(host_scores.items(), key=lambda x: -x[1])
        top3 = sorted_hosts[:3]

        top_host, top_score = top3[0]
        top_features = self._top_host_features(obs, top_host)

        fired = top_score > threshold
        reason = (
            f"Host {top_host} anomaly={top_score:.3f} "
            f"({'FIRED' if fired else 'below'} threshold={threshold:.3f}); "
            f"top feature: {top_features[0][0]}={top_features[0][1]:.3f}"
            if top_features else
            f"Host {top_host} anomaly={top_score:.3f} "
            f"({'FIRED' if fired else 'below'} threshold={threshold:.3f})"
        )
        return LayerExplanation(
            layer="innate",
            top_hosts=top3,
            top_features=top_features,
            reason=reason,
        )

    # ------------------------------------------------------------------
    def explain_memory(
        self,
        drift_scores: dict[str, float],
        threshold: float,
    ) -> LayerExplanation:
        """
        Rank hosts by normalized drift from early-episode baseline.
        Hosts above threshold represent behavior that departed from
        the immune system's frozen 'self' snapshot.
        """
        if not drift_scores:
            return LayerExplanation("memory", [], [], "Memory warming up")

        sorted_hosts = sorted(drift_scores.items(), key=lambda x: -x[1])
        top3 = [(h, round(s, 4)) for h, s in sorted_hosts[:3] if s > 0]

        if not top3:
            return LayerExplanation("memory", [], [],
                                    "Drift scores warming up — no ready hosts yet")

        top_host, top_drift = top3[0]
        fired = top_drift > threshold
        reason = (
            f"Host {top_host} drift={top_drift:.3f} "
            f"({'FIRED' if fired else 'within tolerance'}, threshold={threshold:.3f}); "
            f"recent behavior diverged from frozen early-episode baseline"
        )
        return LayerExplanation("memory", top3, [], reason)

    # ------------------------------------------------------------------
    def explain_tolerance(
        self,
        suppressed: list[str],
        breached: list[str],
        obs: np.ndarray,
    ) -> LayerExplanation:
        """
        Hosts outside their role-based behavioral envelope.
        Breached = above role max (suspicious high activity).
        Suppressed = below role min (within normal tolerance → mute innate).
        """
        top_hosts = (
            [(h, 2.0) for h in breached[:3]] +
            [(h, 0.4) for h in suppressed[:3] if h not in breached]
        )

        if breached:
            feats = self._top_host_features(obs, breached[0]) if breached else []
            reason = (
                f"Role violation: {', '.join(breached)} — "
                f"activity exceeds expected envelope for host role "
                f"(workstation/server/critical baselines)"
            )
        elif suppressed:
            reason = (
                f"Suppressed hosts (within role tolerance): "
                f"{', '.join(suppressed[:3])} — innate alarm muted for routine activity"
            )
        else:
            reason = "All hosts within role-based behavioral bounds"

        return LayerExplanation("tolerance", top_hosts, [], reason)

    # ------------------------------------------------------------------
    def explain_learned(
        self,
        la_conf: float,
        la_type: str,
        gallery_size: int = 0,
        threshold: float = 0.5,
    ) -> LayerExplanation:
        """
        VAE gallery match explanation.
        High confidence + known type → specific attack recognized.
        High reconstruction error + unknown type → novel attack variant.
        """
        fired = la_conf >= threshold
        features = [
            ("gallery_confidence", la_conf),
            ("gallery_size", float(gallery_size)),
        ]

        if gallery_size == 0:
            reason = "Gallery empty — no attack signatures learned yet"
        elif not fired:
            reason = (
                f"No gallery match (conf={la_conf:.3f} < {threshold}); "
                f"gallery has {gallery_size} signature(s) — pattern is novel"
            )
        else:
            reason = (
                f"Matched '{la_type}' from gallery "
                f"(conf={la_conf:.3f}); high cosine similarity to stored embedding"
            )

        return LayerExplanation("learned_attacks", [], features, reason)

    # ------------------------------------------------------------------
    def explain_step(
        self,
        obs: np.ndarray,
        host_innate_scores: dict[str, float],
        innate_threshold: float,
        drift_scores: dict[str, float],
        memory_threshold: float,
        tolerance_suppressed: list[str],
        tolerance_breached: list[str],
        la_conf: float,
        la_type: str,
        gallery_size: int = 0,
    ) -> dict:
        """
        Full per-step explanation. Returns a JSON-serializable dict with
        one explanation sub-dict per layer.
        """
        inn = self.explain_innate(obs, host_innate_scores, innate_threshold)
        mem = self.explain_memory(drift_scores, memory_threshold)
        tol = self.explain_tolerance(tolerance_suppressed, tolerance_breached, obs)
        lea = self.explain_learned(la_conf, la_type, gallery_size)

        return {
            "innate":          _expl_to_dict(inn),
            "memory":          _expl_to_dict(mem),
            "tolerance":       _expl_to_dict(tol),
            "learned_attacks": _expl_to_dict(lea),
        }

    # ------------------------------------------------------------------
    def _top_host_features(
        self,
        obs: np.ndarray,
        host: str,
        n: int = 2,
    ) -> list[tuple[str, float]]:
        """Raw feature values for a host, ranked by absolute magnitude."""
        if host not in HOST_NAMES:
            return []
        idx  = HOST_NAMES.index(host)
        feat = obs[idx * FEATURES_PER_HOST:(idx + 1) * FEATURES_PER_HOST]
        ranked = sorted(enumerate(feat), key=lambda x: -abs(float(x[1])))
        return [(FEATURE_NAMES[i], float(v)) for i, v in ranked[:n]]
