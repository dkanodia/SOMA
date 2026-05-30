"""
soma/eval/detection_metrics.py
================================
Per-step detection rate evaluation for Layer 2 (PPO defender).

B_lineAgent attack chain (CAGE 2 Scenario1b):
  Steps  1-3:  Initial access
  Steps  4-8:  Lateral movement
  Steps  9-12: Privilege escalation
  Steps 13+:   Impact

Minimum acceptable thresholds:
  Lateral movement:    detection rate >= 0.50
  Impact:              detection rate >= 0.80
  FPR on clean eps:    <= 0.01

Cumulative reward is training evidence only — not reported as a capability metric.
"""

import numpy as np
from collections import defaultdict
from typing import Callable


ATTACK_CHAIN = {
    "initial_access":       list(range(1,  4)),
    "lateral_movement":     list(range(4,  9)),
    "privilege_escalation": list(range(9,  13)),
    "impact":               list(range(13, 50)),
}

THRESHOLDS = {
    "lateral_movement": 0.50,
    "impact":           0.80,
}


def evaluate_detection_rates(
    predict_fn: Callable,
    env_fn: Callable,
    layer1_fn: Callable,
    n_episodes: int = 100,
) -> dict:
    """
    Evaluate per-chain-step detection rates over n_episodes.

    Parameters
    ----------
    predict_fn : callable(obs) -> action
    env_fn     : callable() -> CybORGWrapper instance
    layer1_fn  : callable(obs_vec) -> bool  (True = anomaly flagged)
    n_episodes : int

    Returns
    -------
    dict: {phase: {"detected": int, "total": int, "rate": float}}
    """
    counts = {phase: {"detected": 0, "total": 0} for phase in ATTACK_CHAIN}

    for ep in range(n_episodes):
        env  = env_fn()
        obs, _ = env.reset()

        for step in range(200):
            action  = predict_fn(obs)
            obs, _, done, _, info = env.step(action)

            red_step = info.get("red_agent_step", 0)
            l1_fired = layer1_fn(obs)

            for phase, steps in ATTACK_CHAIN.items():
                if red_step in steps:
                    counts[phase]["total"]    += 1
                    if l1_fired:
                        counts[phase]["detected"] += 1

            if done:
                break

    results = {}
    for phase, c in counts.items():
        rate = c["detected"] / c["total"] if c["total"] > 0 else 0.0
        results[phase] = {**c, "rate": rate}
        threshold = THRESHOLDS.get(phase)
        if threshold:
            status = "PASS" if rate >= threshold else "FAIL"
            print(f"[{status}] {phase}: {rate:.3f} (threshold {threshold})")
        else:
            print(f"       {phase}: {rate:.3f}")

    return results
