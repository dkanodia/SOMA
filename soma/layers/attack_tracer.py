"""
soma/layers/attack_tracer.py
==============================
Causal kill-chain reconstruction from host anomaly onset times.

Detects CAUSALITY between host compromises:
  If Host A goes anomalous at t1, Host B at t2 (t2 > t1),
  and A–B are network-adjacent → infer A→B lateral movement.

CAGE 2 Scenario1b topology:
  User0/1/2 → Enterprise0/1 → Op_Server0 (hub-and-spoke)

Output: ordered kill chain (source→target) with confidence scores.
Used by the frontend kill-chain diagram and incident explanations.
"""

from dataclasses import dataclass, field
from typing import Optional


# CAGE 2 Scenario1b network adjacency
NETWORK_ADJACENCY: dict[str, list[str]] = {
    "User0":       ["Enterprise0", "Enterprise1"],
    "User1":       ["Enterprise0"],
    "User2":       ["Enterprise1"],
    "Enterprise0": ["Op_Server0", "User0", "User1"],
    "Enterprise1": ["Op_Server0", "User0", "User2"],
    "Op_Server0":  ["Enterprise0", "Enterprise1"],
}

HOST_TIER = {
    "User0": 0, "User1": 0, "User2": 0,
    "Enterprise0": 1, "Enterprise1": 1,
    "Op_Server0": 2,
}


@dataclass
class KillChainEdge:
    source:     str
    target:     str
    phase:      str   # attack phase label
    confidence: float
    t_source:   int
    t_target:   int


class AttackTracer:
    """
    Tracks which hosts become anomalous and reconstructs the lateral
    movement kill chain from onset times + network adjacency.

    Usage:
        tracer = AttackTracer()
        for step, step_data in enumerate(episode):
            anomalous = set(step_data["compromised_hosts"])
            tracer.update(step, anomalous)
        kill_chain = tracer.kill_chain()
    """

    def __init__(self):
        self._onset: dict[str, int] = {}   # host → first anomalous step
        self._step = 0

    def update(self, step: int, anomalous_hosts: set[str]) -> list[KillChainEdge]:
        """
        Record new anomalous hosts at this step.
        Returns any new causal edges inferred this step.
        """
        self._step = step
        new_edges = []
        for h in anomalous_hosts:
            if h not in self._onset:
                self._onset[h] = step
                # Check if this host was "infected" by an already-anomalous adjacent host
                for adj in NETWORK_ADJACENCY.get(h, []):
                    if adj in self._onset and self._onset[adj] < step:
                        dt = step - self._onset[adj]
                        conf = max(0.3, 1.0 - 0.1 * dt)   # closer in time → higher confidence
                        new_edges.append(KillChainEdge(
                            source=adj, target=h,
                            phase=self._phase_label(HOST_TIER.get(adj, 0), HOST_TIER.get(h, 0)),
                            confidence=conf,
                            t_source=self._onset[adj],
                            t_target=step,
                        ))
        return new_edges

    def kill_chain(self) -> list[KillChainEdge]:
        """Current kill chain: all inferred lateral movement edges, ordered by time."""
        chain = self._onset.copy()
        sorted_hosts = sorted(chain.items(), key=lambda x: x[1])
        edges = []
        seen = set()
        for src, t_src in sorted_hosts:
            for tgt, t_tgt in sorted_hosts:
                if t_tgt <= t_src:
                    continue
                if tgt not in NETWORK_ADJACENCY.get(src, []):
                    continue
                key = (src, tgt)
                if key in seen:
                    continue
                seen.add(key)
                dt   = t_tgt - t_src
                conf = max(0.3, 1.0 - 0.08 * dt)
                edges.append(KillChainEdge(
                    source=src, target=tgt,
                    phase=self._phase_label(HOST_TIER.get(src, 0), HOST_TIER.get(tgt, 0)),
                    confidence=conf,
                    t_source=t_src,
                    t_target=t_tgt,
                ))
        return sorted(edges, key=lambda e: e.t_source)

    def compromised_hosts(self) -> list[str]:
        """All hosts that have gone anomalous, in onset order."""
        return [h for h, _ in sorted(self._onset.items(), key=lambda x: x[1])]

    def reset(self) -> None:
        self._onset.clear()
        self._step = 0

    @staticmethod
    def _phase_label(tier_src: int, tier_tgt: int) -> str:
        if tier_src == 0 and tier_tgt == 1:
            return "lateral_movement"
        if tier_src == 1 and tier_tgt == 2:
            return "privilege_escalation"
        if tier_src == 0 and tier_tgt == 2:
            return "direct_impact"
        return "propagation"

    def to_json(self) -> list[dict]:
        return [
            {
                "source": e.source, "target": e.target,
                "phase": e.phase, "confidence": round(e.confidence, 3),
                "t_source": e.t_source, "t_target": e.t_target,
            }
            for e in self.kill_chain()
        ]
