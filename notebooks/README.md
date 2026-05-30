# `notebooks/` — Development and Analysis Notebooks

Five notebooks corresponding to five development phases. Run them in order — each depends on the previous completing. These are exploratory/development tools; all production code lives in `soma/`.

---

## `01_environment_exploration.ipynb`

### Purpose

Map B_lineAgent's attack chain before writing any training code. Everything downstream depends on knowing exactly when each attack phase happens.

### What to implement

**Cell 1: CybORG episode rollout with do-nothing blue**

```python
from CybORG import CybORG
from CybORG.Agents import B_lineAgent
import inspect
import pandas as pd

path     = str(inspect.getfile(CybORG))
scenario = path[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
env      = CybORG(scenario, "sim", agents={"Red": B_lineAgent()})

HOST_NAMES = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]

records = []
for ep in range(5):
    env.reset()
    for step in range(50):
        obs, _, done, _ = env.step(action="Monitor", agent="Blue")
        for host in HOST_NAMES:
            h = obs.get(host, {})
            records.append({
                "episode": ep, "step": step, "host": host,
                "activity":    h.get("Activity",    0),
                "compromised": h.get("Compromised", 0),
                "sessions":    len(h.get("Sessions",  [])),
                "processes":   len(h.get("Processes", [])),
            })
        if done: break

df = pd.DataFrame(records)
```

**Cell 2: Visualize compromise timeline per host**

```python
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 5, figsize=(18, 4))
for ax, ep in enumerate(range(5)):
    ep_df = df[df["episode"] == ep]
    for host in HOST_NAMES:
        h_df = ep_df[ep_df["host"] == host]
        ax.plot(h_df["step"], h_df["compromised"], label=host, alpha=0.8)
    ax.set_title(f"Episode {ep}")
    ax.set_xlabel("Step")
    ax.set_ylabel("Compromised")
    ax.legend(fontsize=6)
plt.suptitle("B_lineAgent compromise timeline — record these step ranges")
plt.tight_layout()
plt.show()
```

**Cell 3: Print the attack chain map**

From the visualization, record which steps each phase occurs. This goes into `ATTACK_CHAIN` in `detection_metrics.py`.

**Cell 4: Observation feature inspection**

Print the raw observation dict at step 5 (lateral movement phase) to understand what features are available and how they change during an attack.

**Output:** A markdown cell at the end of the notebook stating:
```
B_lineAgent Attack Chain (Scenario1b):
  Initial access:       steps 1–3   (User0 activity spikes)
  Lateral movement:     steps 4–8   (Enterprise0/1 compromise)
  Privilege escalation: steps 9–12  (Op_Server0 sessions increase)
  Impact:               steps 13+   (Op_Server0 compromised)
```

---

## `02_innate_layer_dev.ipynb`

### Purpose

Train and compare Isolation Forest vs VAE. Make the IF-vs-VAE decision here with evidence.

### What to implement

**Cell 1: Collect clean episode data**

```python
# Run CybORG with NO red agent
clean_env = CybORG(scenario, "sim", agents={})
clean_obs = []
for _ in range(200):
    clean_env.reset()
    for step in range(100):
        obs, _, done, _ = clean_env.step("Monitor", "Blue")
        clean_obs.append(flatten_obs(obs))
        if done: break
X_clean = np.array(clean_obs)
print(f"Clean data shape: {X_clean.shape}")   # should be ~(14000, 25)
```

**Cell 2: Train and calibrate Isolation Forest**

```python
from soma.layers.innate import InnateIsolationForest
# Split, train, calibrate, measure FPR
```

**Cell 3: Train and calibrate VAE**

```python
from soma.layers.innate import InnateVAE
# Train for 50 epochs, calibrate, measure FPR
```

**Cell 4: Collect red-agent test data**

```python
# Run CybORG WITH B_lineAgent
# Label each step as anomalous if red_step >= 4 (lateral movement or later)
# Measure TPR of IF and VAE at their calibrated thresholds
```

**Cell 5: Decision table**

| Metric | Isolation Forest | VAE |
|---|---|---|
| FPR on clean val | ≤ 1.0% | ≤ 1.0% |
| TPR on red test | ? | ? |
| Training time | <5 min | ~20 min |
| Failure modes | clean OOD miss | typicality gap |

"**Selected:** [winner] with TPR=[value] at 1% FPR."

This cell's output is the content of `results/fpr_calibration/layer1_benchmark.txt`.

---

## `03_adaptive_layer_dev.ipynb`

### Purpose

Develop and validate the PPO reward function before running the full training script.

### What to implement

**Cell 1: Reward function unit tests**

Run 10 episodes with a random agent. Verify the reward function produces values in a reasonable range (e.g., total episode reward between −1000 and +500). Extreme values indicate a bug.

**Cell 2: Action distribution of random agent**

```python
from soma.envs.cyborg_wrapper import CybORGWrapper, BLUE_ACTIONS
from collections import Counter

env = CybORGWrapper()
action_counts = Counter()
for _ in range(20):
    obs, _ = env.reset()
    for step in range(100):
        action = env.action_space.sample()
        obs, _, done, _, _ = env.step(action)
        action_counts[BLUE_ACTIONS[action]] += 1
        if done: break
print("Random action distribution:", action_counts.most_common(10))
```

This is the random baseline. Record it.

**Cell 3: Short PPO training run**

Train for 10,000 steps (fast sanity check) and verify reward is increasing:

```python
from soma.layers.adaptive import build_agent
agent = build_agent(lambda: CybORGWrapper())
agent.learn(total_timesteps=10_000)
```

Plot the reward curve. If it's flat or decreasing at 10k steps, there's a bug in the reward function or environment.

**Cell 4: Reward hacking check at 10k steps**

```python
from soma.layers.adaptive import evaluate_action_distribution
dist = evaluate_action_distribution(agent, lambda: CybORGWrapper(), n_episodes=10)
print(f"Analyze fraction: {dist.get('analyze_fraction', 'N/A'):.2%}")
```

If Analyze > 70% at 10k steps, the reward hacking guard isn't working.

---

## `04_signaling_game_theory.ipynb`

### Purpose

Verify the PBE math, explore the κ sweep analytically, and produce the theoretical κ sweep plot.

### What to implement

**Cell 1: PBE manual derivation check**

Walk through the math by hand (or symbolically with sympy):

```python
from sympy import symbols, solve, Rational, simplify

mu, q, r, p, V, C, L, kappa = symbols("mu q r p V C L kappa", positive=True)

# Attacker's attack condition: mu * V - (1-mu) * L - kappa >= 0
# At indifference: mu_star = (L + kappa) / (V + L + kappa)
mu_star_expr = (L + kappa) / (V + L + kappa)
print("mu_star =", mu_star_expr)
print("At kappa=0, V=10, L=5:", mu_star_expr.subs([(V, 10), (L, 5), (kappa, 0)]))
```

**Cell 2: PBE solver outputs**

```python
from soma.theory.pbe_solver import kappa_sweep, print_sweep
results = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
print_sweep(results)
```

**Cell 3: Plot κ sweep (theoretical)**

```python
from soma.viz.plots import plot_kappa_sweep
fig = plot_kappa_sweep(results)
plt.show()
```

**Cell 4: Verify against Carroll & Grosu (2011) Proposition 2**

Add a markdown cell comparing the closed-form expressions to the paper. Note any discrepancies and how they were resolved. If the formulas match, state: "Verified against Carroll & Grosu (2011) Proposition 2."

**Cell 5: Game matrix visualization**

Draw the 2×2 payoff matrix for the base case (κ=0, V=10, C=3, L=5, p=0.4) as a formatted table. This is slide material.

---

## `05_convergence_analysis.ipynb`

### Purpose

Full convergence analysis after training. The primary output is the hero visual.

### What to implement

**Cell 1: Load trained models and PBE results**

```python
from stable_baselines3 import PPO
from soma.theory.pbe_solver import kappa_sweep
from soma.layers.deception import evaluate_mixing_rates

KAPPA_VALUES = [0.0, 5.0, 10.0]
pbe_results  = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)

models = {
    k: PPO.load(f"models/deception/signal_policy_kappa_{k:.1f}")
    for k in KAPPA_VALUES
}
```

**Cell 2: Measure final mixing rates**

```python
for k in KAPPA_VALUES:
    q, r  = evaluate_mixing_rates(models[k], kappa=k, n_eval=500)
    pbe   = pbe_results[k]
    print(f"κ={k:.1f}: learned r={r:.4f} vs PBE r*={pbe.r_star:.4f}  gap={abs(r - pbe.r_star):.4f}")
```

**Cell 3: Load training histories and generate hero visual**

```python
import json
from soma.viz.plots import plot_convergence
from pathlib import Path

# Load histories saved during training (train_deception.py writes these)
convergence_data = {}
for k in KAPPA_VALUES:
    history_path = Path(f"results/convergence/history_kappa_{k:.1f}.json")
    if history_path.exists():
        with open(history_path) as f:
            history = json.load(f)
    else:
        # Fallback: single point (final value only)
        q, r = evaluate_mixing_rates(models[k], kappa=k)
        history = [r]
    
    convergence_data[k] = {
        "learned_r_history": history,
        "pbe_r_star":        pbe_results[k].r_star,
    }

fig = plot_convergence(convergence_data, save_path=Path("results/convergence/convergence_plot.png"))
plt.show()
```

**Cell 4: Gap analysis**

```python
for k, d in convergence_data.items():
    final_r = d["learned_r_history"][-1]
    gap     = abs(final_r - d["pbe_r_star"])
    pct_gap = 100 * gap / max(d["pbe_r_star"], 1e-9)
    print(f"κ={k:.1f}: final r={final_r:.4f}, PBE r*={d['pbe_r_star']:.4f}, gap={gap:.4f} ({pct_gap:.1f}%)")
```

A gap < 5% at 100k steps is strong convergence. Gap > 10% means either the PBE is wrong or training needs more steps.

**Cell 5: Pitch notes — what to say**

Add a markdown cell with the two-level explanation:

> **Technical version:** "We train a PPO agent on a 2-type signaling game. The defender learns to mix between revealing and concealing host types. We solve the Perfect Bayesian Equilibrium analytically and show the RL policy converges to it across three values of the attacker's attention cost κ."
>
> **Plain English version (for non-technical judges):** "Purple line = what game theory says the optimal bluffing strategy should be. Cyan line = what our AI figured out by itself. They match."
