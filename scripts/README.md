# `scripts/` — Training and Demo Entry Points

Run these in order. Each script has a hard dependency on the previous one completing successfully. If any fails, do not proceed to the next.

---

## Execution order

```
1. verify_env.py        ← run this first, every time, before anything else
2. train_innate.py      ← Layer 1: ~30 minutes
3. train_adaptive.py    ← Layer 2: ~45 minutes (requires CybORG)
4. train_deception.py   ← Layer 3: ~90 minutes (standalone, no CybORG)
5. demo.py              ← runs live server or exports static fallback
```

Total training time: ~3.5 hours. Start training before sleeping or working on the frontend.

---

## `verify_env.py` — Environment Verification

**Run this before anything else. Always.**

Three checks:
1. PyTorch import and CUDA availability
2. Stable Baselines3 import
3. CybORG import and basic episode step

### If CybORG check fails

```bash
git clone https://github.com/cage-challenge/cage-challenge-2
cd cage-challenge-2
pip install -e .
cd ..
python scripts/verify_env.py
```

Give this 90 minutes maximum. If CybORG still fails to install after debugging, the project continues without it: `SignalingGameEnv` is fully standalone, and `train_deception.py` runs independently. The demo can use SignalingGameEnv as the primary visual if CybORG is unavailable.

### What "CybORG OK" means

The script runs one step with B_lineAgent as red and prints the first 5 keys of the observation dict. If you see host names (User0, Enterprise0, etc.) rather than an error, CybORG is working.

---

## `train_innate.py` — Layer 1 Training

**Complete the `TODO` sections before running:**

### `collect_clean_data()` — implement this first

```python
def collect_clean_data(n_episodes: int) -> np.ndarray:
    from CybORG import CybORG
    import inspect
    path     = str(inspect.getfile(CybORG))
    scenario = path[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
    env      = CybORG(scenario, "sim", agents={})   # NO red agent
    
    from soma.envs.cyborg_wrapper import CybORGWrapper
    wrapper  = CybORGWrapper.__new__(CybORGWrapper)
    # ... or directly call env.step("Monitor", "Blue") and flatten
    
    all_obs = []
    for ep in range(n_episodes):
        env.reset()
        for step in range(100):
            obs, _, done, _ = env.step(action="Monitor", agent="Blue")
            all_obs.append(flatten_obs(obs))   # see cyborg_wrapper._flatten()
            if done:
                break
    return np.array(all_obs)
```

### Full script flow

1. Collect 200 clean episodes → `X` of shape `(n_steps, 25)`
2. Split 70/15/15 into train/val/test
3. Train Isolation Forest on train split
4. Calibrate Isolation Forest threshold on val split (target: 1% FPR)
5. Train VAE on train split
6. Calibrate VAE threshold on val split
7. Measure TPR of both on test-split red-agent data at fixed FPR
8. Save the winner's model
9. Write benchmark result to `results/fpr_calibration/layer1_benchmark.txt`

### What "red-agent test data" means for step 7

Collect 50 episodes **with** B_lineAgent as red agent. Label each step as anomalous if B_lineAgent has taken at least one lateral movement action (steps 4+ in its chain). Measure TPR = fraction of labeled-anomalous steps that the detector flags.

### Expected output

```
Collecting clean episode data...
Train: 13850  Val: 2960  Test: 2960
Training Isolation Forest...
[Layer 1] Calibrated threshold: -0.4821
[Layer 1] Measured FPR on val_clean: 0.0098 (target 0.01)
Training VAE benchmark...
[Layer 1] Calibrated threshold: 0.3214
[Layer 1] Measured FPR on val_clean: 0.0102 (target 0.01)
Benchmark result: IF TPR=0.712  VAE TPR=0.634  Selected=isolation_forest
Done. Check results/fpr_calibration/layer1_benchmark.txt
```

---

## `train_adaptive.py` — Layer 2 PPO Training

**Complete the `TODO` sections:**

```python
from CybORG import CybORG
from CybORG.Agents import B_lineAgent
from soma.envs.cyborg_wrapper import CybORGWrapper
from soma.layers.adaptive import build_agent, train, evaluate_action_distribution
from soma.eval.detection_metrics import evaluate_detection_rates
from soma.layers.innate import InnateIsolationForest

CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

env_fn = lambda: CybORGWrapper()
agent  = build_agent(env_fn, tb_log=TB_LOG)
agent  = train(agent, TOTAL_STEPS, str(CHECKPOINT_DIR))
agent.save(str(CHECKPOINT_DIR / "soma_ppo_final"))

# Behavioral evaluation
innate = InnateIsolationForest.load(Path("models/innate/isolation_forest.joblib"))
results = evaluate_detection_rates(
    predict_fn = lambda obs: agent.predict(obs, deterministic=True)[0],
    env_fn     = env_fn,
    layer1_fn  = innate.is_anomalous,
    n_episodes = 100,
)

# Reward hacking check
dist = evaluate_action_distribution(agent, env_fn)
print(f"Analyze action fraction: {dist['analyze_fraction']:.2%}")
if dist['analyze_fraction'] > 0.70:
    print("WARNING: possible reward hacking — inspect detected anomaly correspondence")

assert results["lateral_movement"]["rate"] >= 0.50, "FAIL: lateral movement DR too low"
assert results["impact"]["rate"]           >= 0.80, "FAIL: impact DR too low"
```

### TensorBoard monitoring

```bash
tensorboard --logdir ./tb_logs
```

Open http://localhost:6006. Watch:
- `train/reward`: should trend upward with noise
- `train/explained_variance`: should approach 1.0 after 50k steps
- `train/entropy_loss`: if it collapses to 0, policy has converged to deterministic — increase `ent_coef`

### Checkpoint evaluation (run at each 50k checkpoint)

```python
from stable_baselines3 import PPO
checkpoint = PPO.load("models/adaptive/soma_ppo_50000_steps")
# run evaluate_detection_rates and print lateral movement DR
```

Stop training if lateral movement DR ≥ 0.70 and impact DR ≥ 0.90 at any checkpoint — you've exceeded minimum thresholds with margin.

---

## `train_deception.py` — Layer 3 κ Sweep

**This script does NOT require CybORG.** It runs entirely on `SignalingGameEnv`.

**Complete the `TODO` sections:**

```python
from soma.layers.deception import run_convergence_study   # use with_history variant
from soma.viz.plots import plot_convergence, plot_kappa_sweep
from soma.theory.pbe_solver import kappa_sweep

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Theoretical sweep (fast — pure math, no RL)
pbe_results = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
plot_kappa_sweep(pbe_results, save_path=RESULTS_DIR / "kappa_sweep.png")

# RL convergence study (slow — 3 training runs)
rl_results = run_convergence_study(V=10.0, C=3.0, L=5.0, p_real=0.4)

for kappa, r in rl_results.items():
    r["model"].save(str(MODELS_DIR / f"signal_policy_kappa_{kappa:.1f}"))

# Build convergence_data for plot_convergence()
convergence_data = {
    k: {
        "learned_r_history": r.get("learned_r_history", [r["learned_r"]]),
        "pbe_r_star":        r["pbe"].r_star,
    }
    for k, r in rl_results.items()
}
plot_convergence(convergence_data, save_path=RESULTS_DIR / "convergence_plot.png")

print("Hero visual saved to results/convergence/convergence_plot.png")
```

### Expected output

```
Running κ sweep on SignalingGameEnv (standalone)...
κ=0.0:  learned q=0.XXX (PBE 0.XXX)  learned r=0.422 (PBE 0.431)
κ=5.0:  learned q=0.XXX (PBE 0.XXX)  learned r=0.609 (PBE 0.621)
κ=10.0: learned q=0.XXX (PBE 0.XXX)  learned r=0.741 (PBE 0.752)
Generating convergence plot (hero visual)...
Hero visual saved to results/convergence/convergence_plot.png
```

The learned r values should be within ~0.02 of the PBE values. A gap larger than 0.05 means either the PBE solver is wrong or the RL training needs more steps.

---

## `demo.py` — Live Demo Server

### Preparing the static fallback (do this first, before the pitch)

```bash
python scripts/demo.py --static
```

Implement `export_static()`:

```python
def export_static(output_path: Path = Path("results/demo_episode.json")):
    # Load all trained models
    # Run one episode from start to finish
    # Collect all JSON payloads
    # Write to output_path
    output_path.parent.mkdir(exist_ok=True)
    payloads = []
    # ... collect from run_episode() without WebSocket
    with open(output_path, "w") as f:
        json.dump(payloads, f)
    print(f"Static fallback exported: {output_path}")
```

The React frontend's `useWebSocket` hook must then load this file when the WebSocket connection fails (see `frontend/src/hooks/useWebSocket.js`).

### Running the live server

```bash
# Terminal 1
python scripts/demo.py

# Terminal 2
cd frontend && npm install && npm start
```

Open http://localhost:3000.

### Complete `run_episode()` for the live server

```python
async def run_episode(websocket):
    from soma.layers.innate    import InnateIsolationForest
    from soma.layers.adaptive  import load as load_ppo
    from soma.layers.deception import heuristic_honeypot_trigger
    from soma.layers.suppressor import LongDwellDetector
    from soma.envs.cyborg_wrapper import CybORGWrapper, HOST_NAMES
    
    innate   = InnateIsolationForest.load(Path("models/innate/isolation_forest.joblib"))
    ppo      = load_ppo("models/adaptive/soma_ppo_final")
    detector = LongDwellDetector.load(Path("models/innate/drift_detector.joblib"))
    env      = CybORGWrapper()
    obs, _   = env.reset()
    
    obs_dict = {}  # per-host feature dicts
    
    for step in range(200):
        action, _ = ppo.predict(obs, deterministic=True)
        obs, _, done, _, info = env.step(action)
        
        # Per-host processing
        anomaly_scores  = {}
        honeypot_flags  = {}
        for i, host in enumerate(HOST_NAMES):
            host_obs = obs[i * 5 : (i + 1) * 5]
            score    = -innate.model.score_samples(host_obs.reshape(1, -1))[0]  # higher = bad
            anomaly_scores[host] = float(score)
            honeypot_flags[host] = bool(heuristic_honeypot_trigger(
                score / max_score  # normalize to [0,1]
            ))
            detector.update(host, host_obs)
        
        drift_alarms = {h: detector.drift_alarm(h) for h in HOST_NAMES}
        
        # Host status for NetworkGraph
        hosts = []
        for i, host in enumerate(HOST_NAMES):
            host_obs  = obs[i * 5 : (i + 1) * 5]
            hosts.append({
                "id":           host,
                "compromised":  bool(host_obs[1] > 0.5),
                "anomaly_score": anomaly_scores[host],
                "honeypot":     honeypot_flags[host],
                "drift_alarm":  drift_alarms[host],
            })
        
        payload = {
            "step":           step,
            "hosts":          hosts,
            "anomaly_scores": anomaly_scores,
            "honeypot_flags": honeypot_flags,
            "drift_alarms":   drift_alarms,
            "honeypot_note":  "heuristic trigger — not signaling game policy",
            "reward":         float(info.get("reward", 0)),
        }
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(0.15)   # ~7 fps — fast enough to look alive, slow enough to read
        
        if done:
            break
```

### The 10-second demo silence moment

At the moment B_lineAgent pivots toward a honeypot-activated host, the demo should pause narration. The host turns amber in the NetworkGraph. Prepare a recorded backup of this moment (export to video or GIF using the static JSON replay) in case the live demo fails.

**Risk: the honeypot activation may not trigger at the right moment.** B_lineAgent is deterministic, so you know exactly which step it will pivot to Op_Server0. If the heuristic trigger threshold is calibrated to fire near step 9–12, the demo moment is reproducible. Test this 10 times before the pitch.
