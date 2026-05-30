# `soma/envs/` — Gymnasium Environments

Two completely separate environments live here. They must **never** be conflated in the pitch or codebase, because they model different games with different adversaries.

---

## Overview

| File | Purpose | Adversary | Theory status |
|---|---|---|---|
| `signal_game.py` | 2-type signaling game | Rational Bayesian receiver | Validated against closed-form PBE |
| `cyborg_wrapper.py` | CAGE 2 gym wrapper | B_lineAgent (scripted, deterministic) | No signaling — heuristic bridge only |

The deception RL policy is trained **exclusively** on `SignalingGameEnv`. The `CybORGWrapper` hosts the PPO adaptive defender. The two connect only through the heuristic trigger in `soma/layers/deception.py::heuristic_honeypot_trigger()` — not through any policy transfer.

---

## `signal_game.py` — SignalingGameEnv

### What to build

A fully functional `gymnasium.Env` implementing a 2-type, 2-signal, 2-action signaling game for training the deception RL policy.

**Game structure (do not change these, the PBE derivation depends on them):**

```
Types:   θ ∈ {Real=1, Honeypot=0}   drawn each step with prior p = P(Real)
Signals: s ∈ {AppearReal=1, AppearHoneypot=0}   chosen by defender (RL agent)
Actions: a ∈ {Attack=1, Pass=0}   chosen by rational Bayesian attacker
```

**Defender payoffs (what the RL agent maximises):**
- Attacker attacks a Real host: **−V** (asset compromised, bad)
- Attacker attacks a Honeypot: **+C** (counterintelligence gain, good)
- Attacker passes on any host: **0**

### `__init__` parameters — all must be configurable

```python
p_real : float = 0.4    # prior P(θ = Real)
V      : float = 10.0   # real asset value (loss to defender if attacked)
C      : float = 3.0    # counterintelligence gain (defender wins when honeypot hit)
L      : float = 5.0    # attacker cost of hitting a honeypot
kappa  : float = 0.0    # attacker attention cost (see κ section below)
n_hosts: int   = 5      # hosts per episode step
```

### Spaces

```python
action_space      = MultiBinary(n_hosts)   # defender signal per host
observation_space = MultiBinary(n_hosts)   # true host types (known to defender, NOT attacker)
```

### `reset()` implementation

Draw `n_hosts` independent Bernoulli(p_real) samples for `true_types`. Reset per-host beliefs to `p_real`. Return `(true_types.copy(), {})`.

### `step(defender_signal)` implementation — most critical part

For each host `i`:

1. **Bayesian update** — attacker updates belief `μ_i = P(Real | signal_i)` using the current mixing rates. In the skeleton the likelihood ratios are hardcoded as `(0.6, 0.4)`. This is a placeholder. The correct implementation uses the **equilibrium mixing rates** from the PBE solver:

   ```python
   # From soma.theory.pbe_solver import compute_pbe
   # pbe = compute_pbe(p_real, V, C, L, kappa)
   # P(AppearReal | Real)     = 1 - pbe.q_star
   # P(AppearReal | Honeypot) = pbe.r_star
   ```

   The `_bayesian_update` method has a `TODO` comment — replace the hardcoded `0.6/0.4` with the above. This is how the RL policy training environment properly reflects equilibrium belief updating.

   Bayes' rule:
   ```
   μ = (lr * prior) / (lr * prior + lh * (1 - prior))
   ```
   where `lr = P(signal=s | Real)` and `lh = P(signal=s | Honeypot)`.

2. **Attacker decision** — attacker attacks iff expected payoff minus attention cost exceeds zero:
   ```
   E[payoff | attack] = μ * V - (1 − μ) * L − κ > 0
   ```
   Rearranged: attack iff `μ > (L + κ) / (V + L + κ)`.

3. **Defender reward** — accumulate `−V` per compromised real host, `+C` per honeypot hit.

4. **Draw new types** for the next step (each step is a fresh type draw — the game is episodic in belief, not in types).

Return `(new_true_types, total_reward, False, False, {"attacker_actions": actions})`.

### κ (attention cost) — critical design note

κ is a **scalar utility penalty** on the attacker's payoff for observing the signal. It is **not** formal rational inattention (Sims 2003; Matějka & McKay AER 2015). Formal RI constrains mutual information via Shannon entropy — we do not implement that. κ is a tractable approximation.

The effect: higher κ means the attacker's attack threshold `μ* = (L + κ) / (V + L + κ)` rises, meaning the attacker needs higher confidence before attacking. Equivalently, the defender can afford to "bait" more aggressively (higher `r*`).

The κ sweep trains policies at `{0.0, 5.0, 10.0}` (= `{0, V/2, V}`). Three values are enough to show the monotonic relationship. Never estimate κ from behavioral data — it is unidentified without a structural model.

### What "convergence" means and how to measure it

After training a PPO policy on `SignalingGameEnv` for `kappa=k`, call `soma.layers.deception.evaluate_mixing_rates(model, kappa=k)` to measure the empirical mixing rates:

```
q = P(signal=AppearHoneypot | θ=Real)   ← estimated over 500 eval steps
r = P(signal=AppearReal | θ=Honeypot)   ← estimated over 500 eval steps
```

Compare to PBE values `(q*, r*)` from `compute_pbe(p_real, V, C, L, k)`. The convergence plot (hero visual) shows this gap shrinking during training. To generate the history, evaluate every 5,000 training steps and record `(r_learned, r_pbe_star)` pairs.

### Interaction with PBE solver

```python
# In signal_game.py _bayesian_update():
from soma.theory.pbe_solver import compute_pbe
pbe = compute_pbe(self.p, self.V, self.C, self.L, self.kappa)
# Use pbe.q_star and pbe.r_star as likelihood ratios
```

**Circular dependency note:** The PBE solver uses the same parameters. During training, the environment uses the PBE mixing rates as the Bayesian update kernel. The RL agent then learns to produce those same mixing rates. This is self-consistent — the equilibrium is a fixed point.

---

## `cyborg_wrapper.py` — CybORGWrapper

### Purpose

Exposes CAGE 2 CybORG as a `gymnasium.Env` compatible with Stable Baselines3. The only RL agent trained here is the PPO adaptive defender (Layer 2). B_lineAgent is the fixed red agent.

### CybORG installation (must be done before this file is usable)

```bash
git clone https://github.com/cage-challenge/cage-challenge-2
cd cage-challenge-2
pip install -e .
```

Verify:
```python
from CybORG import CybORG
from CybORG.Agents import B_lineAgent
import inspect
path = str(inspect.getfile(CybORG))
scenario = path[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
env = CybORG(scenario, "sim", agents={"Red": B_lineAgent()})
obs, _, _, _ = env.step(action="Monitor", agent="Blue")
print(list(obs.keys()))   # must print host names, not an error
```

Maximum 90 minutes debugging this. If it fails, the SignalingGameEnv runs standalone — treat CybORG as optional realism for the demo.

### What to complete in `__init__`

Uncomment and complete the CybORG initialization block:

```python
from CybORG import CybORG
from CybORG.Agents import B_lineAgent
import inspect
cyborg_file    = str(inspect.getfile(CybORG))
scenario_path  = cyborg_file[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
self._env      = CybORG(scenario_path, "sim", agents={"Red": B_lineAgent()})
```

### Observation space — what the 25 features are

5 features × 6 hosts (User0, User1, User2, Enterprise0, Enterprise1, Op_Server0), concatenated in HOST_NAMES order:

| Index | Feature | Source in CybORG obs dict |
|---|---|---|
| 0 | `activity` | `obs[host]["Activity"]` — scan/exploit flag |
| 1 | `compromised` | `obs[host]["Compromised"]` — 0 or 1 |
| 2 | `session_count` | `len(obs[host].get("Sessions", []))` |
| 3 | `process_count` | `len(obs[host].get("Processes", []))` |
| 4 | `network_position` | `obs[host]["Interface"]["IP_Address"] % 256 / 255.0` |

All values normalized to [0, 1]. Missing keys return 0.

### Action space

Discrete(19) — one index per entry in `BLUE_ACTIONS`. The list is already defined in the file. Index 0 is "Monitor" (no-op, used to gather observations). Indices 1–6 are Analyze actions per host. Indices 7–12 are Remove. Indices 13–18 are Restore.

**Critical:** CybORG's step API takes `action=string_name, agent="Blue"`. Convert the discrete action index before calling: `BLUE_ACTIONS[action_int]`.

### `reset()` implementation

```python
def reset(self, *, seed=None, options=None):
    super().reset(seed=seed)
    raw_obs = self._env.reset()             # returns dict
    self._prev_raw_obs = raw_obs
    self._step_count   = 0
    self._recently_analyzed.clear()
    return self._flatten(raw_obs), {}
```

### `step()` implementation

```python
def step(self, action: int):
    action_str = BLUE_ACTIONS[action]
    host       = self._action_host(action_str)    # None for "Monitor"
    result     = self._env.step(action=action_str, agent="Blue")
    raw_obs    = result[0]                        # dict
    done       = result[2]
    info       = result[3] if len(result) > 3 else {}
    
    reward = self._compute_reward(raw_obs, self._prev_raw_obs, action_str, host)
    self._update_recently_analyzed(host, action_str)
    self._prev_raw_obs = raw_obs
    self._step_count  += 1
    
    # Inject red agent step count for detection_metrics.py
    info["red_agent_step"] = self._step_count
    
    return self._flatten(raw_obs), reward, done, False, info
```

### Reward function — why it's shaped this way

The reward function has five terms. Each exists to prevent a specific failure mode:

| Term | Value | Why |
|---|---|---|
| Detect lateral movement before compromise | +8.0 | Primary objective |
| New compromise (missed detection) | −10.0 | Strong negative signal |
| False positive removal/restore on clean host | −4.0 | Penalise acting without evidence |
| Repeated Analyze on recently-analyzed clean host | −2.0 | **Reward hacking guard** — prevents agent spamming Analyze for +8 without genuine value |
| Per-step efficiency penalty | −0.5 | Discourage inaction |

The −2.0 repeated-Analyze penalty is the most important. Without it, the agent discovers it can score +8 by repeatedly analyzing any host showing minor activity — this is reward hacking. The `_recently_analyzed` set implements a 5-step sliding window that expires automatically.

At the 50k step checkpoint: print the action distribution. If Analyze actions > 70% of total and reward is climbing, check whether detected anomalies correspond to actual B_lineAgent steps or noise. If it's noise, the reward hacking guard isn't working — increase the −2.0 penalty to −5.0.

### B_lineAgent attack chain — map it before training

B_lineAgent follows a deterministic script. Run 5 clean episodes with a do-nothing blue and print observations at each step to produce this map:

```
Steps 1–3:   Initial access via known exploit on User0
Steps 4–8:   Lateral movement to Enterprise0, Enterprise1
Steps 9–12:  Privilege escalation on Op_Server0
Steps 13+:   Impact (data exfiltration on Op_Server0)
```

Your detection success criteria are keyed to this chain. "Lateral movement detected" means the agent issued an Analyze or triggered Layer 1 alarm during steps 4–8, before step 13. This map drives `soma/eval/detection_metrics.py`.

### `info` dict — what to pass through for evaluation

The `info` dict from `step()` must include:
- `"red_agent_step"`: int — which step of B_lineAgent's chain is active
- `"compromised_hosts"`: list[str] — hosts currently compromised

These are used by `evaluate_detection_rates()` in `detection_metrics.py` to compute per-phase detection rates.

### Failure mode: `_env` is None

The skeleton initializes `self._env = None`. Every method has placeholder returns. The full implementation must replace all `# TODO` placeholders. If CybORG installation fails, the file still imports cleanly — but `reset()` and `step()` will fail at runtime. This is intentional: the SignalingGameEnv continues working without CybORG.
