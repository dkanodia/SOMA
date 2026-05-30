"""
soma/fusion/response_orchestrator.py
======================================
Stateless rule-based policy router: maps ranked Incidents + layer flags
to a recommended BLUE_ACTION.

This is additive — it runs alongside the PPO agent, not instead of it.
The PPO agent continues to act; the orchestrator's recommendation is
streamed to the frontend as a parallel signal for dashboard visibility.

Priority rules:
  HIGH confidence                      → Remove_{host}
  MEDIUM confidence                    → Analyze_{host}
  MEDIUM confidence + 3+ layers fired  → escalate to Remove_{host}
  LOW confidence                       → Monitor (no-op)
  LOW confidence + drift active        → escalate to Analyze_{host}
  No incidents                         → Monitor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# BLUE_ACTIONS mirrored from soma/envs/cyborg_wrapper.py — kept inline to
# avoid pulling in the gymnasium/CybORG dependency at import time.
BLUE_ACTIONS = [
    "Monitor",
    "Analyze_User0",    "Analyze_User1",    "Analyze_User2",
    "Analyze_Enterprise0", "Analyze_Enterprise1", "Analyze_Op_Server0",
    "Remove_User0",     "Remove_User1",     "Remove_User2",
    "Remove_Enterprise0", "Remove_Enterprise1", "Remove_Op_Server0",
    "Restore_User0",    "Restore_User1",    "Restore_User2",
    "Restore_Enterprise0", "Restore_Enterprise1", "Restore_Op_Server0",
]

# Build name→index lookup once at import time
_ACTION_IDX: dict[str, int] = {name: i for i, name in enumerate(BLUE_ACTIONS)}


@dataclass
class OrchestratorDecision:
    recommended_action: int          # index into BLUE_ACTIONS (0–18)
    action_name: str                 # e.g. "Remove_User0"
    host: str                        # target host, or "" for Monitor
    confidence: str                  # "HIGH" | "MEDIUM" | "LOW" | "NONE"
    reason: str
    incident_score: float
    layers_contributing: list = field(default_factory=list)


class ResponseOrchestrator:
    """
    Stateless orchestrator — no internal history.
    Call recommend() once per step.
    """

    def recommend(
        self,
        incidents: list,       # list[Incident] from NetworkImmuneCorrelator (sorted desc)
        layer_flags: dict,     # {"innate": bool, "honeypot": bool, "drift": bool, "learned": bool}
    ) -> OrchestratorDecision:

        if not incidents:
            return OrchestratorDecision(
                recommended_action=0,
                action_name="Monitor",
                host="",
                confidence="NONE",
                reason="No active incidents detected",
                incident_score=0.0,
                layers_contributing=[],
            )

        top = incidents[0]
        n_layers = len(top.layers_fired)
        drift_active = bool(layer_flags.get("drift"))

        if top.confidence == "HIGH":
            prefix = "Remove"
            reason = f"HIGH confidence on {top.host} (score={top.score:.2f}, layers={'+'.join(top.layers_fired)})"
        elif top.confidence == "MEDIUM":
            if n_layers >= 3:
                prefix = "Remove"
                reason = (
                    f"MEDIUM escalated→Remove: {n_layers} layers fired on {top.host} "
                    f"(score={top.score:.2f})"
                )
            else:
                prefix = "Analyze"
                reason = f"MEDIUM confidence on {top.host} (score={top.score:.2f})"
        else:  # LOW
            if drift_active:
                prefix = "Analyze"
                reason = f"LOW escalated→Analyze: drift alarm active on {top.host}"
            else:
                prefix = "Monitor"
                reason = f"LOW confidence on {top.host} — monitoring only"

        action_idx, action_name = self._select_action_index(prefix, top.host)

        return OrchestratorDecision(
            recommended_action=action_idx,
            action_name=action_name,
            host=top.host,
            confidence=top.confidence,
            reason=reason,
            incident_score=top.score,
            layers_contributing=list(top.layers_fired),
        )

    @staticmethod
    def _select_action_index(prefix: str, host: str) -> tuple[int, str]:
        """Return (index, name) for the given action prefix + host."""
        if prefix == "Monitor" or not host:
            return 0, "Monitor"
        name = f"{prefix}_{host}"
        idx = _ACTION_IDX.get(name)
        if idx is None:
            # Host name not in BLUE_ACTIONS — fall back to Monitor
            return 0, "Monitor"
        return idx, name
