# `soma/eval/` — Evaluation and Calibration

This module exists to prevent the single most common failure mode in ML system demos: claiming capability without measuring it.

**Every threshold in every layer must be calibrated using a function in this module before the layer is used in any pitch or demo.** This is not optional.

---

## `fpr_calibration.py` — False Positive Rate Calibration

### Why this file is the most important in the project

A detection threshold set at the 95th percentile of clean data flags 5% of clean observations. On a 6-host network monitored every 10 seconds over 24 hours, this produces approximately 31,000 false alarms per day. No operational environment tolerates this. Without calibration, all claimed detection capabilities are meaningless.

### FPR budgets by layer

| Layer | Budget | Rationale |
|---|---|---|
| Layer 1 (Isolation Forest / VAE) | 1.0% | Per-step; 72 false alarms/host/day — tolerable for a prototype |
| Layer 2 (PPO heuristic trigger) | 1.0% | Consistent with Layer 1 |
| Layer 4 (Long-dwell drift) | 0.1% | Alarms trigger human review — must be rare |

### `calibrate_layer1(anomaly_fn, X_val_clean, fpr_target=0.01) → float`

**Input:** An anomaly scoring function `f(x: ndarray) → float` where **higher = more anomalous**, and a matrix of clean validation observations.

**Output:** A threshold `τ` such that `P(f(x) > τ | x ~ clean) ≈ fpr_target`.

**How it works:** Sets τ to the `(1 - fpr_target) * 100`-th percentile of scores on clean validation data. Measures the actual FPR and asserts it's within ±0.5% of target.

**Convention note for Isolation Forest:** Isolation Forest produces scores where **more negative = more anomalous**. When wrapping `iso.score_samples()` for `calibrate_layer1`, negate the scores so higher = more anomalous:

```python
calibrate_layer1(
    anomaly_fn = lambda x: -iso.model.score_samples(x.reshape(1, -1))[0],
    X_val_clean = X_val,
    fpr_target  = 0.01,
)
```

This convention ensures the calibration function works identically for the Isolation Forest and VAE.

### `calibrate_layer2(suspicion_fn, X_val_clean, fpr_target=0.01) → float`

Same structure as `calibrate_layer1`. The suspicion function maps a per-host observation vector to a scalar in [0, 1].

**Where does the suspicion score come from?** The heuristic bridge in `deception.py` compares a suspicion score to a threshold to activate honeypot presentation. The suspicion score itself comes from the Layer 2 PPO agent's value function estimate or from Layer 1's anomaly score. In the demo:

```python
# Simple proxy: use Layer 1 anomaly score normalized to [0, 1]
def suspicion_fn(x):
    raw_score = -iso.model.score_samples(x.reshape(1, -1))[0]
    return float(np.clip((raw_score - min_score) / (max_score - min_score), 0, 1))
```

Calibrate this function's threshold on clean observations so that 1% of clean per-host observations trigger the honeypot heuristic.

### `validate_all_fpr(results) → bool`

Call this at the end of `scripts/train_innate.py` and `scripts/train_adaptive.py` with measured FPRs:

```python
results = {
    "layer1_fpr": measured_fpr_layer1,
    "layer2_fpr": measured_fpr_layer2,
    "layer4_fpr": measured_fpr_layer4,
}
assert validate_all_fpr(results), "FPR budget violated — do not demo"
```

The ±0.2% tolerance in `validate_all_fpr` accounts for sampling variance in test-set measurement. If any layer fails, do not demo it — fix the threshold first.

### What to add

`fpr_calibration.py` is missing a Layer 4 calibration function. Add:

```python
def calibrate_layer4(
    detector: "LongDwellDetector",
    clean_histories: dict,
    fpr_target: float = 0.001,
) -> float:
    """
    Wrapper around LongDwellDetector.calibrate_threshold().
    Separated here to keep the calibration pipeline consistent.
    """
    from soma.layers.suppressor import LongDwellDetector
    return detector.calibrate_threshold(clean_histories, fpr_target=fpr_target)
```

---

## `detection_metrics.py` — Per-Phase Detection Rate Evaluation

### Why detection rate matters more than reward

Cumulative reward tells you training is working. Detection rate tells you what the agent actually learned to do. An agent that detects all Impact events but misses all lateral movement events can score reasonable cumulative reward — but provides nearly zero defensive value, because the attacker has already escalated by the time Impact is detected.

Report these four numbers in the pitch, not reward curves:

| Metric | Minimum acceptable |
|---|---|
| Lateral movement detection rate | 0.50 |
| Impact detection rate | 0.80 |
| FPR on clean episodes | ≤ 0.01 |
| Analyze action fraction | ≤ 0.70 |

### B_lineAgent attack chain — map this before training

B_lineAgent's attack chain is deterministic. The step ranges in `ATTACK_CHAIN` reflect CAGE 2 Scenario1b behavior:

```python
ATTACK_CHAIN = {
    "initial_access":       range(1, 4),    # steps 1-3
    "lateral_movement":     range(4, 9),    # steps 4-8
    "privilege_escalation": range(9, 13),   # steps 9-12
    "impact":               range(13, 50),  # steps 13+
}
```

**Before training**, verify this mapping by running 5 episodes with a do-nothing blue agent and printing the observation at each step. Specifically look for when `obs[host]["Compromised"]` flips from 0 to 1 for each host. The chain ranges above may need adjustment if Scenario1b was updated.

### `evaluate_detection_rates()` — what to complete

The function body is complete as structured. The `# TODO` placeholders are in the parameters. To call it:

```python
from soma.layers.innate   import InnateIsolationForest
from soma.layers.adaptive import load as load_ppo
from soma.envs.cyborg_wrapper import CybORGWrapper

ppo    = load_ppo("models/adaptive/soma_ppo_final")
innate = InnateIsolationForest.load(Path("models/innate/isolation_forest.joblib"))

results = evaluate_detection_rates(
    predict_fn = lambda obs: ppo.predict(obs, deterministic=True)[0],
    env_fn     = lambda: CybORGWrapper(),
    layer1_fn  = innate.is_anomalous,
    n_episodes = 100,
)
```

### What `red_agent_step` in info dict means

The `CybORGWrapper.step()` must include `info["red_agent_step"]` — the current step in B_lineAgent's attack chain. This is how `evaluate_detection_rates` knows which phase of the chain is active at each step.

In `CybORGWrapper.step()`:
```python
# Approximate red agent step from episode step count
# (B_lineAgent is deterministic — step count is a proxy)
info["red_agent_step"] = self._step_count
```

This is an approximation because CybORG doesn't directly expose B_lineAgent's internal state. If CybORG's observation dict includes red agent action info, use that instead.

### Adding clean-episode FPR measurement

Add a separate evaluation function for Layer 1 FPR on clean episodes (no red agent):

```python
def evaluate_clean_fpr(
    layer1_fn: Callable,
    n_episodes: int = 50,
    steps_per_episode: int = 100,
) -> float:
    """
    Run CybORG with NO red agent. Count fraction of steps where layer1_fn fires.
    This is the operational FPR — should be <= 0.01.
    """
    # Implement using CybORG with agents={} (no red agent)
    raise NotImplementedError
```

Add this to `scripts/train_innate.py` after calibration and include the result in `validate_all_fpr()`.
