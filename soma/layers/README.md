# `soma/layers/` — Four Detection Layers

Four files. Four timescales. Each has a calibrated FPR budget that must be measured before the layer is used.

---

## Layer ordering and dependencies

```
innate.py       → train first (clean data required for calibration)
adaptive.py     → train second (requires CybORGWrapper from envs/)
deception.py    → train third (requires pbe_solver.py and signal_game.py)
suppressor.py   → calibrate last (requires 500+ clean episode steps)
```

`deception.py` has **no dependency on CybORG**. Train it independently on `SignalingGameEnv`. It will work even if CybORG fails to install.

---

## `innate.py` — Layer 1: Per-Step Anomaly Detection

**FPR budget: 1%**

### What to complete

Two detectors are implemented as class stubs. Complete and train both; use whichever achieves higher TPR at the fixed 1% FPR budget on test-split red-agent data.

**Primary model: `InnateIsolationForest`**

The `fit()` and `calibrate_threshold()` methods are complete. Complete the training pipeline in `scripts/train_innate.py`.

**Threshold calibration — how it works:**

`calibrate_threshold(X_val_clean)` sets the decision threshold to the `fpr_target`-th percentile of anomaly scores on clean validation data. Because Isolation Forest scores more-anomalous observations with more-negative values, the threshold is set at the **bottom** `fpr_target * 100`-th percentile:

```python
scores    = self.model.score_samples(X_val_clean)   # more negative = more anomalous
threshold = np.percentile(scores, fpr_target * 100)  # bottom 1%
```

This guarantees that exactly `fpr_target` fraction of clean observations fall below the threshold — i.e., FPR = 1% by construction on validation data. Measure the actual FPR on the separate test-split clean data; it should be within ±0.5% of the target.

**Benchmark model: `InnateVAE`**

The VAE is implemented and functional. **Known failure mode:** Reconstruction error is not a guaranteed monotone anomaly score. OOD inputs can produce low reconstruction error when they project near high-density regions of the learned decoder manifold. This is the typicality gap (Nalisnick et al., ICLR 2019, "Do Deep Generative Models Know What They Don't Know?").

On a 25-feature integer input space, the VAE is unlikely to outperform the Isolation Forest. If it does, use it and state the benchmark result. If it doesn't, use the Isolation Forest and state that too. The decision is an empirical one — not aesthetic.

**VAE training loop** (add to `scripts/train_innate.py`):

```python
import torch
import torch.optim as optim

def train_vae(model, X_train, n_epochs=50, lr=1e-3):
    opt   = optim.Adam(model.parameters(), lr=lr)
    X_t   = torch.tensor(X_train, dtype=torch.float32)
    model.train()
    for epoch in range(n_epochs):
        opt.zero_grad()
        recon, mu, logvar = model(X_t)
        recon_loss = F.mse_loss(recon, X_t)
        kl_loss    = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
        loss       = recon_loss + 0.1 * kl_loss   # β = 0.1 is fine for this dim
        loss.backward()
        opt.step()
    return model
```

**`DualTimescaleBaseline`** — this is a high-pass filter, not a principled anomaly detector. Its two parameters (`fast_alpha`, `slow_alpha`) have no principled basis. Use it as a sanity check: it should not fire on a flat constant signal. It is **not** benchmarked against the other two models — it's a monitoring utility, not a deployment candidate.

### FPR in practice — the operational reality

At 1% FPR with 10-second monitoring intervals on 6 hosts:
- 6 observations per 10-second window
- 1% FPR → ~6 false alarms per 1000 windows per host
- Over 24 hours (8,640 windows) → ~52 false alarms per host per day

This is too high for a production system. For the hackathon demo it is acceptable. State this explicitly in the pitch: "1% FPR is a prototype threshold. Production would target 0.01% with more training data."

### Layer 1 output to Layer 2

`is_anomalous(obs_vec: np.ndarray) -> bool` is the interface Layer 2 consumes. Each step, Layer 1 classifies the per-host observation. Layer 2's PPO agent sees the full 30-feature flattened observation — Layer 1 is not directly in the observation space, but its outputs are used by the demo server to color-code hosts in the NetworkGraph panel.

---

## `adaptive.py` — Layer 2: PPO Defender

**FPR budget: 1% (false positive actions on clean episodes)**

### What to complete

The `build_agent()` and `train()` functions are complete. Complete:

1. `evaluate_action_distribution()` — run `n_episodes` episodes, record the fraction of steps using each action type. This is the reward hacking check.

2. Add `train()` call to `scripts/train_adaptive.py`.

3. Add the behavioral evaluation call to `scripts/train_adaptive.py` with the assertion that lateral movement detection rate ≥ 0.50.

### Hyperparameters — do not change these without reason

| Parameter | Value | Rationale |
|---|---|---|
| `n_steps` | 2048 | Standard for episodic tasks |
| `batch_size` | 64 | Sufficient for 25-dim obs |
| `n_epochs` | 10 | Typical |
| `learning_rate` | 3e-4 | Adam default, works well |
| `ent_coef` | 0.01 | Mild entropy bonus; increase to 0.05 if policy collapses |
| `clip_range` | 0.2 | PPO standard |
| `gae_lambda` | 0.95 | Long-horizon estimation |
| `gamma` | 0.99 | Discounts future appropriately |

If training plateaus before 100k steps, try `ent_coef=0.05`. If reward drops after a peak, try `learning_rate=1e-4` from that checkpoint. Stop at 300k steps regardless.

### Success criteria — what to measure

Do NOT report cumulative reward as a capability metric. Report these four:

| Metric | Minimum threshold | How to measure |
|---|---|---|
| Lateral movement detection rate | ≥ 0.50 | `detection_metrics.evaluate_detection_rates()` |
| Impact stage detection rate | ≥ 0.80 | same |
| FPR on clean episodes | ≤ 0.01 | `fpr_calibration.calibrate_layer2()` |
| Analyze action fraction | ≤ 0.70 | `evaluate_action_distribution()` |

The fourth criterion is the reward hacking check. If Analyze > 70% of actions, the agent has likely learned to exploit the +8 reward by spamming Analyze on any active host — inspect whether detections correspond to actual B_lineAgent steps.

### What "adaptive" does and does not mean

The trained PPO policy is **frozen at deployment**. It does not update online. "Adaptive" describes the CAGE 2 challenge framing — the blue agent adapts its actions per-step in response to observations. It does not mean the policy adapts to new attacker strategies at runtime. State this in the pitch.

### Checkpoint strategy

Save every 50k steps with `CheckpointCallback`. At each checkpoint:
1. Run `evaluate_action_distribution()` — print action fractions
2. Check if Analyze fraction > 70% (reward hacking check)
3. Run 20 test episodes, compute mean episode length and total reward

If you need to compare checkpoints, load with `PPO.load(path)` and run evaluation.

---

## `deception.py` — Layer 3: Signaling Game + Heuristic Bridge

**FPR budget: N/A for the RL policy (standalone env). 1% FPR for the CybORG heuristic trigger.**

### Architecture — the most important thing to understand before touching this file

**Two separate systems with different purposes:**

```
SignalingGameEnv  ←→  PPO deception policy  →  validated against PBE
                                                (theoretical contribution)
         ↕
  [LABELED HEURISTIC BRIDGE — explicit gap]
         ↕
CybORGWrapper  →  heuristic_honeypot_trigger()  →  honeypot activation
                                                    in demo
```

B_lineAgent follows a fixed script regardless of how hosts appear. The game-theoretic signaling policy was trained against a rational Bayesian receiver — applying it to B_lineAgent means deploying a policy against a different game. The two systems are intentionally kept separate. This is more honest and, explained correctly, more impressive.

### What to complete in `train_signal_policy()`

The function is complete as structured. The main thing to add is **convergence tracking** — measuring `r` every 5,000 steps during training to produce the history for the convergence plot:

```python
def train_signal_policy_with_history(kappa: float, eval_every: int = 5000) -> tuple[PPO, list]:
    env_fn = lambda: SignalingGameEnv(kappa=kappa)
    env    = DummyVecEnv([env_fn])
    model  = PPO("MlpPolicy", env, verbose=0, **SIGNAL_HYPERPARAMS)
    
    r_history = []
    steps_done = 0
    while steps_done < SIGNAL_TOTAL_STEPS:
        model.learn(total_timesteps=eval_every, reset_num_timesteps=False)
        steps_done += eval_every
        _, r = evaluate_mixing_rates(model, kappa)
        r_history.append(r)
    
    return model, r_history
```

Pass `r_history` to `plot_convergence()` in `soma/viz/plots.py`.

### What to complete in `run_convergence_study()`

The function is complete but calls the non-history version. Swap to `train_signal_policy_with_history()`. The return dict should include `"learned_r_history"` for the plot:

```python
results[k] = {
    "learned_q":        lq,
    "learned_r":        lr,
    "learned_r_history": r_history,   # add this
    "pbe":              pbe,
    "pbe_r_star":       pbe.r_star,   # add this for plot convenience
    "model":            model,
}
```

### `evaluate_mixing_rates()` — implementation note

The function uses `deterministic=False` in `model.predict()`. This is critical — a deterministic policy doesn't produce mixed strategies, and the semi-separating PBE requires mixing. If you accidentally use `deterministic=True`, the learned rates will be extreme (0.0 or 1.0) and won't converge to the PBE mixing rates.

### `heuristic_honeypot_trigger()` — what it does and why it's labeled

Activates honeypot presentation when the suspicion score exceeds 0.7. The threshold is manually chosen with no principled basis. It is labeled `"heuristic trigger — not signaling game policy"` in every JSON payload sent to the frontend. In the demo UI, the honeypot label text must say "Heuristic trigger" — not "Game-theoretic decision." This distinction is what makes the architecture intellectually honest and impressive.

### Compute budget

Three training runs at 100,000 steps each ≈ 90 minutes on laptop CPU (no GPU needed for this tiny env). Run them sequentially overnight or during other work.

---

## `suppressor.py` — Layer 4: Long-Dwell Drift Detection

**FPR budget: 0.1% (strict — these alarms should be rare)**

**Renamed from "tumor suppressor"** — the biological name implies mechanistic similarity to genetic tumor suppressor proteins, which has no analog here. The function is longitudinal behavioral drift detection.

### What to complete

The full implementation is present. Three things to verify and complete:

1. **`calibrate_threshold()` requires at least 500 feature vectors.** In the hackathon you will not have 500 clean episodes before the demo. **Inject drift manually in the demo script** and state this in the pitch: "In the demo we inject synthetic behavioral drift to show the mechanism. Real deployment calibrates on 48+ hours of clean baseline."

2. **PCA fit requires at least 50 vectors.** The `fit_pca()` check returns False below 50. Make sure your demo collects enough clean baseline observations before activating drift detection.

3. **`centroid_trajectory()` is the visualization output.** Call this per host and pass the 2D trajectory arrays to the `DriftPanel` component in the frontend. Each trajectory is a `list[np.ndarray]` of shape `(2,)` — plot as a scatter with a time-colored path.

### Why Layer 1 misses what Layer 4 catches

Layer 1 (Isolation Forest) compares each observation to the training distribution. If an attacker slowly shifts host behavior by 2% per step over 60 steps, each individual step looks normal — the drift is invisible to a per-step detector. Layer 4 compares the centroid of the first 25 observations in its window to the centroid of the last 25. The cumulative 120% drift is visible as centroid displacement in PCA space.

This is the mechanism to demonstrate in the demo. Inject it by adding a small linear trend to one host's feature vector during the episode: `features[3] += step_number * 0.02`. Layer 1 will not alarm. Layer 4 will.

### FPR at 0.1%

Much stricter than Layer 1 because Layer 4 alarms trigger escalated response (human analyst review, in the real product). A 0.1% FPR on clean data means approximately 0.5 false alarms per host per 8-hour shift — one per shift per host is operationally tolerable.

Calibrate with `calibrate_threshold(clean_histories, fpr_target=0.001)`. Verify the assertion passes before using in the demo.
