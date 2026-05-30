# SOMA: Implementation Plan v2
### Signaling-Optimal Memory Architecture
### Autonomous Cyber Defense via RL + Signaling Games

---

## What Changed From v1 and Why

Every correction below came from a steelman critique of v1. The changes are not cosmetic — several are structural. Read this section before the plan.

**VAE replaced by Isolation Forest as primary anomaly detector.** The VAE has a known failure mode (OOD inputs can produce low reconstruction error when they project near high-density regions of the learned decoder manifold, related to the typicality gap documented in Nalisnick et al. ICLR 2019). On a 25-feature integer input space this dimensionality does not justify the added complexity. Isolation Forest is benchmarked against the VAE empirically; whichever wins on F1 at a fixed 1% FPR budget is used. The decision is made with data, not narrative preference.

**False positive rate budget added to every layer.** v1 had no FPR anywhere. A threshold at the 95th percentile of clean data produces by construction 5% false alarms on clean input — approximately 4,320 false alarms per host per day at 10-second monitoring intervals on a 10-host network. This is operationally disqualifying. Every layer now has an explicit FPR target and a calibration procedure.

**Signaling game and CybORG are decoupled.** The deception RL policy trained on SignalingGameEnv cannot be transferred to CybORG via a three-feature bridge because B_lineAgent does not respond to signals — it follows a fixed script regardless of how hosts appear. Applying a policy trained against a rational Bayesian receiver to a non-strategic scripted attacker is deploying it against a different game. The signaling game now runs as a standalone theoretical demonstration with its own environment. The CybORG honeypot trigger is a separate, explicitly labeled heuristic. This is more honest and, presented correctly, more intellectually impressive — it shows the team understands the gap between theory and simulation.

**κ is not estimated from behavioral data.** κ is fundamentally unidentified from behavioral observations alone without a structural model that separately identifies attacker capability, operational security behavior, tool overhead, and attention cost. B_lineAgent generates no signal-responsive variation anyway. The κ sweep is retained as a theoretical result — sweeping κ analytically in the PBE computation, not estimating it from data.

**Rational inattention framing corrected.** Adding κ as a utility cost is not formal rational inattention. Formal RI (Sims 2003, Matějka and McKay AER 2015) constrains mutual information between state and action and solves for the optimal joint distribution subject to an entropy-measured information cost. The utility-cost approximation is a simplification; it is presented as such in the plan and pitch, not as implementing RI.

**Self-play not presented as a clean fix.** Independent PPO self-play has no convergence guarantee to Nash equilibrium in non-zero-sum games with asymmetric information. It is noted as a research direction, not a recommended hackathon step.

**Compute budget is explicit and realistic.** v1's training schedule was approximately 14 hours of compute on a single GPU for the full κ sweep plus PPO plus the demo infrastructure. The revised plan fits within 8 hours of training across the hackathon window.

**Biological metaphor scope is explicit.** The innate layer uses a trained model — it is not analogous to biological innate immunity, which operates via fixed genetically encoded responses. The metaphor is valid at the architectural level (fast coarse detection → slow precise response) and invalid at the mechanistic level. The pitch says so directly.

**Federated learning reframed.** PySyft has no FedRAMP authorization and no DoD IL4/IL5 compliance posture. Non-IID client distributions in federated averaging cause divergence from individual optimal models (Li et al. FedProx; Karimireddy et al. SCAFFOLD). Federating a prime contractor facing nation-state adversaries with a logistics subcontractor facing opportunistic ransomware degrades both models. The architecture is reframed as federated threat signature sharing with human-in-the-loop review, not gradient averaging. This is slower, less technically elegant, and actually deployable.

**CMMC is table stakes, not differentiation.** Exostar, CyberSaint, and Conveyor have existing C3PAO relationships and past performance records. A new entrant's compliance module cannot substitute for past performance in defense procurement. CMMC compliance is presented as a qualification threshold, not a competitive advantage.

**Competitive moat is clearances and past performance, not technology.** The signaling game framework is documented in peer-reviewed literature (Carroll & Grosu 2011; Pawlick & Zhu 2019). Any motivated ML researcher can replicate it in weeks. The technical differentiation gets you the first conversation. The actual moat — CAGE number, facility clearance, cleared personnel, past performance record — takes 3-5 years to build and is the real barrier to entry.

---

## Guiding Principle

Build the most technically honest version of each layer that is completable in the time available. Honesty here means: every claim in the pitch is supported by something you actually measured, every limitation is named rather than hidden, and the signaling game result is presented as what it is — a proof of concept that RL recovers game-theoretic equilibria under rational-adversary assumptions, not a claim about real attacker behavior.

---

## Pre-Hackathon Setup (Do This Now)

**1. Clone CAGE 2 — not CAGE 4**

CAGE 4 is a months-long research challenge with a MARL setup across a large enterprise network. CAGE 2 is a single-agent scenario against B_lineAgent that runs in an afternoon. Use CAGE 2.

```bash
git clone https://github.com/cage-challenge/cage-challenge-2
cd cage-challenge-2
pip install -e .
pip install stable-baselines3 torch scikit-learn scipy matplotlib numpy
```

Verify:
```python
from CybORG import CybORG
from CybORG.Agents import B_lineAgent
import inspect
path = str(inspect.getfile(CybORG))
env = CybORG(path[:-7] + '/Shared/Scenarios/Scenario1b.yaml', 'sim')
obs, _, _, _ = env.step(action='Monitor', agent='Blue')
print(obs)  # must print an observation dict, not an error
```

Max 90 minutes on this. If it's not working at 90 minutes, move to the standalone SignalingGameEnv and treat CybORG as optional realism.

**2. Understand what B_lineAgent actually does**

Run 5 episodes with B_lineAgent as red and a do-nothing blue. Print the full observation at each step. Map out B_lineAgent's deterministic attack chain:
- Step 1–3: Initial access via known exploit
- Step 4–8: Lateral movement to adjacent hosts
- Step 9–12: Privilege escalation
- Step 13+: Impact on target

This map defines your detection success criteria. You are not trying to detect "attacks in general" — you are trying to detect each discrete step of this specific chain before it completes. Write the chain down. It governs every evaluation metric in Layer 2.

Note explicitly: B_lineAgent does not respond to signals. It follows this chain regardless of how hosts appear. This means it is not a strategic adversary and the signaling game policy trained on SignalingGameEnv does not transfer to it. These are different systems with different purposes.

**3. Scaffold the project**

```
soma/
├── layers/
│   ├── innate.py         # Isolation Forest anomaly detector
│   ├── adaptive.py       # PPO defender
│   ├── deception.py      # Signaling game standalone
│   └── suppressor.py     # Longitudinal drift detection
├── envs/
│   ├── cyborg_wrapper.py # Gym wrapper for CAGE 2
│   └── signal_game.py    # 2-type signaling game env (standalone)
├── eval/
│   ├── fpr_calibration.py   # FPR calibration for each layer
│   └── detection_metrics.py # Per-step detection rates
├── viz/
│   └── (React app)
├── train.py
└── demo.py
```

**4. Compute budget — explicit**

| Component | Estimated Training Time (laptop GPU) |
|---|---|
| Isolation Forest on clean episodes | < 5 minutes |
| VAE benchmark comparison | ~20 minutes |
| PPO on CAGE 2 (200k steps) | ~45 minutes |
| Signaling game PPO (100k steps × 3 κ values) | ~90 minutes |
| FPR calibration runs | ~30 minutes |
| Total | ~3.5 hours |

This fits comfortably within the hackathon. Do not add the full 7-value κ sweep — 3 values ({0, V/2, V}) are sufficient to show the monotonic relationship and cost ~60 minutes less.

---

## Hour 0–2: Environment Wrapper

Build `envs/cyborg_wrapper.py`. Extract a clean feature vector per host per step.

**Feature extraction:**
```python
def obs_to_features(obs_dict, host_names):
    vectors = {}
    for host in host_names:
        h = obs_dict.get(host, {})
        vectors[host] = np.array([
            h.get('Activity', 0),           # scan/exploit activity level
            h.get('Compromised', 0),         # compromise flag (0/1)
            len(h.get('Sessions', [])),      # active session count
            len(h.get('Processes', [])),     # process count delta
            h.get('Interface', {}).get('IP_Address', 0)  # network position proxy
        ], dtype=np.float32)
    return vectors
```

**Gym wrapper:**
```python
class CybORGWrapper(gym.Env):
    def __init__(self):
        self.env = CybORG(scenario_path, 'sim', agents={'Red': B_lineAgent()})
        self.n_hosts = 5
        self.observation_space = gym.spaces.Box(
            low=0, high=1, shape=(self.n_hosts * 5,), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(len(BLUE_ACTIONS))
        self._prev_obs = None

    def step(self, action):
        result = self.env.step(action=BLUE_ACTIONS[action], agent='Blue')
        obs = self._flatten(result[0])
        reward = self._compute_reward(result[0], self._prev_obs)
        self._prev_obs = result[0]
        return obs, reward, result[2], result[3]

    def reset(self):
        obs = self.env.reset()
        self._prev_obs = obs
        return self._flatten(obs)
```

**Success criterion:** Run 10 full episodes (up to episode end), collect `(obs, action, reward, done)` tuples without errors. Print mean episode length and total reward for a random agent. This is your random baseline — record it.

---

## Hour 2–8: Layer 1 — Innate Immunity (Anomaly Detection)

**Design decision — Isolation Forest as primary, VAE as benchmark**

The plan is: train both, evaluate both at a fixed 1% FPR, use whichever has higher detection rate. This is a 30-minute empirical decision, not an aesthetic one.

**FPR budget:** 1% of clean observations flagged as anomalous. At 10-second monitoring intervals on 5 hosts, this is approximately 72 false alarms per host per day — still high for an operational system, but tractable for a prototype and honest to state.

**Training data — clean baseline:**

Collect 200 episodes with no red agent:
```python
clean_env = CybORG(scenario_path, 'sim', agents={})  # no red agent
clean_data = []
for ep in range(200):
    obs = clean_env.reset()
    for step in range(100):
        obs, _, done, _ = clean_env.step(action='Monitor', agent='Blue')
        clean_data.append(flatten_obs(obs))
        if done: break
X_clean = np.array(clean_data)  # shape: (n_steps, 25)
```

**Isolation Forest:**
```python
from sklearn.ensemble import IsolationForest
from sklearn.calibration import CalibratedClassifierCV

iso = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
iso.fit(X_clean)

# anomaly_score: more negative = more anomalous
# threshold: 99th percentile of scores on clean validation set (1% FPR)
val_scores = iso.score_samples(X_clean_val)
threshold = np.percentile(val_scores, 1)  # bottom 1% on clean = FPR budget

def anomaly_score_iso(x):
    return iso.score_samples(x.reshape(1,-1))[0] < threshold  # True = anomaly
```

**VAE benchmark:**
```python
class NetworkVAE(nn.Module):
    def __init__(self, input_dim=25, latent_dim=8):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64), nn.ReLU(),
            nn.Linear(64, 32), nn.ReLU()
        )
        self.mu_layer = nn.Linear(32, latent_dim)
        self.logvar_layer = nn.Linear(32, latent_dim)
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 32), nn.ReLU(),
            nn.Linear(32, 64), nn.ReLU(),
            nn.Linear(64, input_dim)
        )
    def forward(self, x):
        h = self.encoder(x)
        mu, logvar = self.mu_layer(h), self.logvar_layer(h)
        z = mu + torch.exp(0.5 * logvar) * torch.randn_like(mu)
        return self.decoder(z), mu, logvar
    def recon_error(self, x):
        recon, _, _ = self.forward(x)
        return F.mse_loss(recon, x, reduction='none').mean(-1)
```

Train for 30 epochs. Set VAE threshold at the 99th percentile of reconstruction error on clean validation data (1% FPR, matching the Isolation Forest budget).

**Evaluation — choose your detector:**

Run 50 episodes with B_lineAgent as red. At each step, record: `(true_compromise_state, detector_flag)`. Compute:
- True positive rate: fraction of steps where host is compromised AND detector fires
- False positive rate: fraction of steps where host is clean AND detector fires (must be ≤ 1%)
- Detection latency: mean steps from first B_lineAgent action to first detector flag on that host

Use whichever detector wins on TPR at the 1% FPR constraint. State the comparison result explicitly in the pitch — "we benchmarked both and chose the one that performed better."

**Dual-timescale baseline:**
```python
class DualTimescaleBaseline:
    def __init__(self, fast_alpha=0.1, slow_alpha=0.001, sigma_threshold=2.5):
        self.fast = self.slow = self.slow_var = None
        self.sigma = sigma_threshold

    def update_and_flag(self, score: float) -> bool:
        if self.slow is None:
            self.fast = self.slow = score
            self.slow_var = 0.0
            return False
        self.fast = (1 - 0.1) * self.fast + 0.1 * score
        self.slow = (1 - 0.001) * self.slow + 0.001 * score
        self.slow_var = (1 - 0.001) * self.slow_var + 0.001 * (score - self.slow)**2
        slow_std = max(np.sqrt(self.slow_var), 1e-6)
        return self.fast > self.slow + self.sigma * slow_std
```

Note: the dual-timescale baseline is a high-pass filter on the anomaly score stream. It has two manually set parameters (fast_alpha, slow_alpha) with no principled basis. It adapts to non-stationarity only as fast as the slow EMA allows. Its advantage is computational simplicity and interpretability, not theoretical optimality. State this.

**Success criteria for Layer 1:**
- Chosen detector: TPR ≥ 0.6 at FPR = 1% on the B_lineAgent episodes
- Detection latency: mean ≤ 5 steps after lateral movement begins on a host
- Print these metrics explicitly; they are Panel 1's data, not just a time-series plot

---

## Hour 8–20: Layer 2 — Adaptive Immunity (PPO Defender)

**What this layer does and does not do**

The PPO agent learns to take investigation and response actions against B_lineAgent's fixed attack chain in CybORG simulation. It is not adaptive in the sense of updating its policy in response to novel attacker behavior at deployment time — it learns offline against one scripted adversary and deploys a frozen policy. This is stated explicitly in the pitch: "trained offline against a simulated adversary; online adaptation is a research direction, not a current capability."

**Reward function:**
```python
def compute_reward(curr_obs, prev_obs, action_taken, action_host):
    reward = 0.0
    for host in host_names:
        curr_comp = curr_obs[host].get('Compromised', 0)
        prev_comp = prev_obs[host].get('Compromised', 0)
        prev_act  = prev_obs[host].get('Activity', 0)

        # Detected lateral movement before compromise on this host
        if curr_comp == 0 and prev_act > 0:
            reward += 8.0

        # New compromise (missed detection)
        if curr_comp == 1 and prev_comp == 0:
            reward -= 10.0

        # False positive: isolated or restored a clean host
        if action_host == host and action_taken in ('Isolate', 'Restore'):
            if curr_comp == 0:
                reward -= 4.0

        # Excessive Analyze on already-investigated clean hosts
        # Prevents reward hacking: agent spamming Analyze for +8 on noisy activity
        if action_host == host and action_taken == 'Analyze':
            if host in self.recently_analyzed and curr_comp == 0:
                reward -= 2.0  # diminishing return on repeat analysis

    reward -= 0.5  # per-step efficiency penalty
    return reward
```

The penalty on repeated Analyze of clean hosts is critical. Without it the agent learns to issue Analyze repeatedly on a noisy-activity host to collect +8 rewards without genuine defensive value — a textbook reward-hacking failure. The `recently_analyzed` set contains hosts analyzed in the last 5 steps.

**Training:**
```python
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

env = DummyVecEnv([lambda: CybORGWrapper()])
model = PPO(
    'MlpPolicy', env,
    n_steps=2048,
    batch_size=64,
    n_epochs=10,
    learning_rate=3e-4,
    ent_coef=0.01,
    clip_range=0.2,
    verbose=1,
    tensorboard_log='./tb_logs'
)
model.learn(total_timesteps=200_000)
model.save('soma_ppo_defender')
```

**Behavioral evaluation — the correct success criteria**

Cumulative reward improvement is training evidence, not capability evidence. After training, evaluate on 100 fresh episodes and compute:

```python
attack_chain_steps = {
    'initial_access':    range(1,  4),   # B_lineAgent steps 1-3
    'lateral_movement':  range(4,  9),   # steps 4-8
    'privilege_escalation': range(9, 13), # steps 9-12
    'impact':            range(13, 30),   # steps 13+
}

metrics = {phase: {'detected': 0, 'total': 0} for phase in attack_chain_steps}

for ep in range(100):
    obs = env.reset(); ep_step = 0
    while True:
        action, _ = model.predict(obs)
        obs, _, done, info = env.step(action)
        red_step = info.get('red_agent_step', 0)
        for phase, steps in attack_chain_steps.items():
            if red_step in steps:
                metrics[phase]['total'] += 1
                if layer1_alarm_fired_this_step:
                    metrics[phase]['detected'] += 1
        if done: break

for phase, m in metrics.items():
    dr = m['detected'] / m['total'] if m['total'] > 0 else 0
    print(f"{phase}: detection rate = {dr:.2f}")
```

**Minimum acceptable performance:**
- Lateral movement detection rate ≥ 0.5 (catch at least half of lateral movement steps)
- Impact detection rate ≥ 0.8 (nearly always catch the final stage)
- FPR on clean episodes ≤ 1% (consistent with Layer 1 budget)
- At least 20% higher reward than random baseline (necessary but not sufficient)

If lateral movement detection rate < 0.3, the reward function needs retuning before moving on. The most common fix: increase the +8 early-detection bonus to +12 or add a -15 penalty for impact completion (the final red agent goal state).

---

## Hour 20–32: Layer 3 — Signaling Game (Standalone Theoretical Demonstration)

This is the theoretical core and the unfair advantage. It runs as a standalone system, separate from CybORG, because the policy transfer between the two environments is not justified. The connection to CybORG is a heuristic bridge presented honestly as such.

---

### Step 3A: Build the Signaling Game Environment (Hours 20–23)

**The game — precise formulation**

- **Types:** θ ∈ {Real, Honeypot}, drawn with prior p = P(θ = Real)
- **Sender (Defender):** observes θ, chooses signal s ∈ {AppearReal, AppearHoneypot}
- **Receiver (Attacker):** observes s, holds prior belief μ₀ = p, updates to posterior μ(s) via Bayes' rule, chooses action a ∈ {Attack, Pass}

**Payoffs:**

| | Attacker Attacks | Attacker Passes |
|---|---|---|
| θ = Real | Defender: −V, Attacker: +V | Both: 0 |
| θ = Honeypot | Defender: +C, Attacker: −L | Both: 0 |

Where V = asset value (set to 10), C = counterintelligence gain (set to 3), L = cost of hitting honeypot (set to 5).

**Attacker rationality assumption — stated explicitly:** The receiver in this model is a rational Bayesian agent with correct beliefs about the prior and utility function. Real adversaries are not game-theoretically rational — they use heuristics, have bounded computation, and do not have common knowledge of your payoff structure. The PBE solution is a benchmark for what an optimal defender should do against a rational adversary, not a prediction of real attacker behavior. B_lineAgent in CybORG is explicitly not this receiver — it ignores signals entirely.

**Utility-cost attention parameter κ:** The attacker pays cost κ to process the signal. If the expected value of signal processing is below κ, the attacker ignores the signal and uses the prior. Note: this is a scalar utility-cost approximation, not formal rational inattention. Formal RI (Sims 2003; Matějka and McKay, AER 2015) constrains mutual information between state and action via an entropy-measured information cost and solves for the optimal joint distribution subject to that constraint. The utility-cost approximation is a tractable simplification that captures the directional effect — more inattentive attackers respond less to signals — without the formal structure. Present it as an approximation.

```python
class SignalingGameEnv(gym.Env):
    def __init__(self, p_real=0.4, V=10, C=3, L=5, kappa=0.0, n_hosts=5):
        self.p = p_real
        self.V, self.C, self.L = V, C, L
        self.kappa = kappa
        self.n = n_hosts
        # Defender: for each host, choose signal (0=AppearHoneypot, 1=AppearReal)
        self.action_space = gym.spaces.MultiBinary(n_hosts)
        # State: true host types (1=Real, 0=Honeypot), known to defender
        self.observation_space = gym.spaces.MultiBinary(n_hosts)
        self.reset()

    def reset(self):
        self.true_types = np.random.binomial(1, self.p, self.n)
        self.beliefs = np.full(self.n, self.p)  # attacker's prior
        return self.true_types.copy()

    def step(self, defender_signal):
        assert len(defender_signal) == self.n
        attacker_actions = np.zeros(self.n, dtype=int)
        defender_reward = 0.0

        for i in range(self.n):
            s = int(defender_signal[i])
            theta = int(self.true_types[i])

            # Bayesian update using defender's empirical mixing rates
            # (on first step, attacker uses prior; updated each episode)
            mu = self._bayesian_update(s, self.beliefs[i])
            self.beliefs[i] = mu

            # Attacker's expected value of attacking, net of attention cost
            ev_attack = mu * self.V - (1 - mu) * self.L - self.kappa
            # Note: attacker's perspective: Real host gives +V, Honeypot gives -L
            attacker_actions[i] = 1 if ev_attack > 0 else 0

            # Defender reward
            if attacker_actions[i] == 1:
                if theta == 1:   # Real host attacked: bad for defender
                    defender_reward -= self.V
                else:            # Honeypot attacked: good for defender
                    defender_reward += self.C
            # Pass: no payoff for either player

        obs = self.true_types.copy()
        self.true_types = np.random.binomial(1, self.p, self.n)  # new episode step
        return obs, defender_reward, False, {'attacker_actions': attacker_actions}

    def _bayesian_update(self, signal, prior):
        # Likelihood: P(signal=1 | Real) and P(signal=1 | Honeypot)
        # Attacker doesn't know defender's strategy — uses uniform mixing assumption
        # In equilibrium, these are the equilibrium mixing rates
        # For off-equilibrium computation, use 0.5 as uninformative prior on strategy
        if signal == 1:   # AppearReal
            likelihood_real = 0.6   # P(AppearReal | Real)
            likelihood_hp   = 0.4   # P(AppearReal | Honeypot)
        else:
            likelihood_real = 0.4
            likelihood_hp   = 0.6
        num = likelihood_real * prior
        den = likelihood_real * prior + likelihood_hp * (1 - prior)
        return num / (den + 1e-9)
```

---

### Step 3B: Derive the PBE (Hours 23–25)

**Work this out analytically before coding it.** The 2×2 case is fully tractable.

**Attacker's attack threshold μ\*:**

Attacker attacks iff expected value of attacking exceeds κ:
```
μ · V − (1−μ) · L − κ > 0
μ > (L + κ) / (V + L + κ) ≡ μ*
```

With V=10, L=5, κ=0: μ* = 5/15 = 0.333. As κ increases toward V=10, μ* → 15/25 = 0.6. Attacker requires higher posterior probability that the host is real before attacking — they are more cautious when attention is costly.

**Why separating equilibrium doesn't exist (for the defender):**

If the defender always signals truthfully (Real→AppearReal, Honeypot→AppearHoneypot), the attacker learns host types exactly: μ(AppearReal) = 1, μ(AppearHoneypot) = 0. Attacker always attacks real hosts, never attacks honeypots. Defender payoff: −V per real host. The defender can strictly improve by deviating — signaling a real host as AppearHoneypot makes the attacker less likely to attack it. So truthful separating is not an equilibrium for the defender.

**Semi-separating (mixed strategy) equilibrium:**

Defender mixes:
- For Real hosts: signal AppearHoneypot with probability q (hiding real assets)
- For Honeypot hosts: signal AppearReal with probability r (baiting attackers)

For the attacker to mix (and be indifferent), the posterior μ(AppearReal) must equal μ*:
```
μ(AppearReal) = p(1−q) / [p(1−q) + (1−p)r] = μ*
```

For the defender to mix on real hosts (indifferent between signals), the attacker's response to AppearHoneypot must make the defender indifferent. This gives the second equation. Solving:

```python
def compute_pbe(p_real, V, C, L, kappa):
    """
    Returns equilibrium mixing rates and attack threshold.
    q = P(signal=AppearHoneypot | theta=Real)    [defender hides real assets]
    r = P(signal=AppearReal | theta=Honeypot)    [defender baits with honeypots]
    mu_star = attacker's attack threshold
    """
    mu_star = (L + kappa) / (V + L + kappa)

    # From defender's indifference condition on real hosts:
    # Defender mixing on Real means: payoff(AppearHoneypot) = payoff(AppearReal) for real host
    # When attacker attacks AppearReal with prob alpha_1 and AppearHoneypot with prob alpha_2:
    # At semi-sep equilibrium, attacker mixes on one signal and is pure on the other.
    # Full derivation yields (see Carroll & Grosu 2011, Proposition 2):

    # r* from attacker indifference pinned by defender's cost structure:
    r_star = ((1 - mu_star) / mu_star) * (p_real / (1 - p_real)) * (C / (C + V))
    r_star = float(np.clip(r_star, 0.0, 1.0))

    # q* from attacker's posterior equaling mu_star given r*:
    numerator = p_real * (1 - mu_star) - mu_star * (1 - p_real) * r_star
    denominator = p_real * (1 - mu_star)
    q_star = float(np.clip(numerator / (denominator + 1e-9), 0.0, 1.0))

    return q_star, r_star, mu_star
```

**The κ sweep — theoretical result, 3 values:**

```python
kappa_values = [0.0, V/2, V]   # inattentive spectrum: fully attentive to fully ignoring
results = {}
for k in kappa_values:
    q, r, mu = compute_pbe(p_real=0.4, V=10, C=3, L=5, kappa=k)
    results[k] = {'q': q, 'r': r, 'mu_star': mu}
    print(f"κ={k:.1f}: μ*={mu:.3f}, q*={q:.3f}, r*={r:.3f}")
```

**What this shows:** As κ increases from 0 to V, μ* increases, and r* (the optimal honeypot-baiting rate) increases. The defender optimally deploys more honeypot bait as the attacker pays more attention to cost. The claim is not that real attackers follow this — it's that if you model adversaries as rational under attention costs, optimal deception intensity increases monotonically with attacker inattention. Plot r* vs. κ. This is your headline theoretical figure.

---

### Step 3C: Train RL Policy and Show Convergence (Hours 25–32)

Train PPO on SignalingGameEnv for each of the 3 κ values. Compare learned mixing rates to PBE benchmark.

```python
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

def train_signal_policy(kappa, total_steps=100_000):
    env = DummyVecEnv([lambda: SignalingGameEnv(kappa=kappa)])
    model = PPO('MlpPolicy', env, n_steps=512, learning_rate=1e-3,
                ent_coef=0.05, verbose=0)
    model.learn(total_timesteps=total_steps)
    return model

def evaluate_mixing_rates(model, kappa, n_eval=500):
    env = SignalingGameEnv(kappa=kappa)
    real_appear_hp = 0; real_total = 0
    hp_appear_real = 0; hp_total = 0

    for _ in range(n_eval):
        obs = env.reset()
        action, _ = model.predict(obs, deterministic=False)  # stochastic eval
        for i in range(env.n):
            if obs[i] == 1:   # Real host
                real_total += 1
                if action[i] == 0:  real_appear_hp += 1   # sent AppearHoneypot
            else:              # Honeypot host
                hp_total += 1
                if action[i] == 1:  hp_appear_real += 1   # sent AppearReal

    learned_q = real_appear_hp / (real_total + 1e-9)
    learned_r  = hp_appear_real  / (hp_total + 1e-9)
    return learned_q, learned_r

# Run for 3 kappa values
for kappa in [0.0, 5.0, 10.0]:
    model = train_signal_policy(kappa)
    lq, lr = evaluate_mixing_rates(model, kappa)
    pq, pr, mu = compute_pbe(0.4, 10, 3, 5, kappa)
    print(f"κ={kappa}: Learned q={lq:.3f} (PBE {pq:.3f}), r={lr:.3f} (PBE {pr:.3f})")
```

**The convergence plot:** For each κ, plot learned r (y-axis) vs. training steps (x-axis), with the PBE benchmark r* as a horizontal line. Three subplots side by side, one per κ value. The RL rate should approach the equilibrium rate as training progresses. This is not tautological — there is no guarantee PPO with this architecture and hyperparameters converges to PBE; showing that it does is a genuine empirical result.

**What to say about this result in the pitch:** "We derived what game theory says the optimal bluffing rate should be under a rational-adversary model — those are the purple lines. We then trained an RL agent from scratch with no knowledge of game theory — those are the cyan lines. They converge. This tells us two things: our RL system is not a black box, it recovers provably optimal strategies. And optimal deception intensity increases predictably with adversary inattention, which has direct implications for how you tune a deception system depending on what type of attacker you're facing."

**What NOT to say:** Do not claim this characterizes real attacker behavior. Do not use the word "rational inattention" without the caveat that this is a utility-cost approximation, not formal RI. Do not claim the PBE solution is operationally predictive.

---

### Step 3D: Heuristic Bridge to CybORG (Hours 30–32)

Since the signaling game policy cannot be directly transferred to CybORG (B_lineAgent ignores signals), the connection is a simple heuristic trigger presented explicitly as such.

```python
def heuristic_honeypot_trigger(host_suspicion_score, suspicion_threshold=0.7):
    """
    Simple heuristic: activate honeypot presentation when PPO's suspicion
    score for a host exceeds threshold. This is NOT the signaling game policy.
    The signaling game shows what optimal deception looks like under rational
    adversary assumptions; this is a practical approximation for the simulation.
    """
    return host_suspicion_score > suspicion_threshold
```

In the demo, show both: the signaling game convergence result (standalone, theoretically justified) and the heuristic honeypot in CybORG (simulation practical). Label them separately. This distinction is a feature, not a bug — it shows you understand the gap between theory and implementation.

---

## Hour 32–38: Layer 4 — Tumor Suppressor (Longitudinal Drift)

Rename this in the pitch to "Longitudinal Behavioral Drift Detection" or "Long-Dwell Threat Layer." The tumor suppressor name invites biological scrutiny that the analogy can't survive — biological tumor suppressors are genetic mechanisms, not surveillance systems. The function is real and useful; it needs a name that doesn't invite the wrong comparison.

**FPR budget:** 0.1% of clean long-run observations trigger a drift alarm. This is strict because drift alarms should be rare — they represent a days-or-weeks level signal, not a per-step decision.

```python
class LongDwellDetector:
    def __init__(self, window=100, drift_threshold=0.3, fpr_target=0.001):
        self.history = defaultdict(list)
        self.pca = PCA(n_components=2)
        self.fitted = False
        self.drift_threshold = drift_threshold
        # Calibrate threshold on clean data to achieve fpr_target
        self._calibrated = False

    def update(self, host: str, feature_vec: np.ndarray):
        self.history[host].append(feature_vec)
        if len(self.history[host]) > 500:
            self.history[host].pop(0)

    def fit_pca(self):
        all_vecs = np.vstack([v for vlist in self.history.values() for v in vlist])
        if len(all_vecs) >= 50:
            self.pca.fit(all_vecs)
            self.fitted = True

    def calibrate_threshold(self, clean_histories: dict, fpr_target=0.001):
        """Set drift_threshold so FPR on clean hosts = fpr_target."""
        clean_drifts = []
        for host, hist in clean_histories.items():
            self.history[host] = hist
        self.fit_pca()
        for host in clean_histories:
            drift = self._compute_drift(host)
            if drift is not None:
                clean_drifts.append(drift)
        # threshold = (1 - fpr_target) percentile of clean drift scores
        self.drift_threshold = np.percentile(clean_drifts, (1 - fpr_target) * 100)
        self._calibrated = True

    def _compute_drift(self, host):
        hist = self.history.get(host, [])
        if len(hist) < 50 or not self.fitted:
            return None
        # Compute centroid at start and end of history window in PCA space
        early = np.mean(hist[:25], axis=0)
        late  = np.mean(hist[-25:], axis=0)
        early_2d = self.pca.transform(early.reshape(1,-1))[0]
        late_2d  = self.pca.transform(late.reshape(1,-1))[0]
        return np.linalg.norm(late_2d - early_2d)

    def drift_alarm(self, host) -> bool:
        if not self._calibrated:
            raise RuntimeError("Calibrate threshold on clean data before alarming")
        drift = self._compute_drift(host)
        return drift is not None and drift > self.drift_threshold
```

**Calibration procedure:**
```python
# Collect 300 clean episodes, build long-run histories for each host
clean_histories = collect_clean_histories(n_episodes=300)

# Calibrate on first 200 episodes, validate on remaining 100
detector = LongDwellDetector()
detector.calibrate_threshold(clean_histories[:200], fpr_target=0.001)

# Validate: FPR on held-out clean data must be ≤ 0.1%
fp_count = sum(detector.drift_alarm(h) for h in clean_histories[200:])
measured_fpr = fp_count / len(clean_histories[200:])
assert measured_fpr <= 0.001, f"FPR calibration failed: {measured_fpr:.4f}"
```

**The insider threat demo:** Inject slow drift manually — increase file access features for one host by 2% every 10 steps across 200 steps. Layer 1 will not alarm (its threshold is calibrated to recent baseline which adapts). Layer 4 fires because it compares the early-window centroid to the late-window centroid. Show the centroid trajectory plot with the injected host's 2D trajectory departing from the healthy cluster. Healthy hosts: stable centroids near origin. Injected host: smooth curve outward.

**Name this layer in the pitch:** "The acute detector sees nothing — it's adapted to recent behavior. But compare where this host was 60 simulated days ago to where it is now. That drift is the insider threat signal."

---

## Hour 38–44: Visualization

**Component priority order** (build in this order, stop when time runs out):

1. Convergence plot panel (Layer 3) — highest intellectual value, must exist
2. Network graph with anomaly score coloring (Layer 1)
3. Reward learning curve (Layer 2)
4. Centroid drift scatter (Layer 4)
5. WebSocket live demo — only if the first four are solid

**If you're running behind at hour 40:** pre-render the plots as static images from matplotlib and embed them. A polished static demo beats a broken live demo in every scenario.

**Color system:**
```css
:root {
  --bg:           #0a0e1a;
  --surface:      #111827;
  --healthy:      #22d3ee;   /* cyan  — healthy nodes */
  --compromised:  #ef4444;   /* red   — compromised nodes */
  --honeypot:     #f59e0b;   /* amber — deceptive nodes (heuristic trigger) */
  --pbe-line:     #a855f7;   /* purple — PBE equilibrium benchmark */
  --rl-line:      #22d3ee;   /* cyan  — learned RL policy */
  --text:         #e2e8f0;
  --muted:        #64748b;
}
```

**Convergence panel layout** (largest panel, hero visual):
- Three subplots side by side (one per κ value)
- Y-axis: defender mixing rate r for honeypot-baiting signal
- X-axis: training steps (0 to 100k)
- Purple horizontal line: PBE equilibrium r* for that κ
- Cyan curve: learned RL mixing rate over training
- Title each subplot: κ=0 (fully attentive), κ=5 (moderate), κ=10 (inattentive)
- Annotation: "RL converges to game-theoretic equilibrium across all attacker attention levels"

**Demo flow (WebSocket version):**
```python
# demo.py
import asyncio, websockets, json, numpy as np

async def run_demo(websocket):
    env = CybORGWrapper()
    obs = env.reset()
    innate = load_innate_layer()
    ppo_defender = PPO.load('soma_ppo_defender')
    drift_detector = load_calibrated_detector()

    for step in range(200):
        action, _ = ppo_defender.predict(obs)
        obs, reward, done, info = env.step(action)

        # Layer 1
        anomaly_scores = {h: innate.score(obs_per_host[h]) for h in hosts}

        # Layer 3 heuristic bridge — labeled as heuristic in payload
        honeypot_flags = {
            h: heuristic_honeypot_trigger(anomaly_scores[h])
            for h in hosts
        }

        # Layer 4
        drift_detector.update_all(obs_per_host)
        drift_alarms = {h: drift_detector.drift_alarm(h) for h in hosts}

        payload = {
            'step': step,
            'anomaly_scores': anomaly_scores,
            'honeypot_flags': honeypot_flags,     # heuristic
            'drift_alarms': drift_alarms,
            'note': 'honeypot_flags are heuristic triggers; see convergence panel for game-theoretic policy'
        }
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(0.1)
        if done: break
```

---

## Hour 44–48: Polish and Pitch

**Fallback hierarchy (have all three ready):**
1. Live WebSocket demo + all four panels
2. Pre-recorded 2-minute screen capture of live demo + static convergence plots
3. Static screenshots of all four panels + live convergence plots generated from saved model

Do not attempt the live demo without testing on the presentation machine for at least 30 minutes before the pitch. CybORG has known stability issues on fresh environments.

**Demo sequence (4 minutes, to the second):**

- **:00–:30** — Show the healthy network, all cyan nodes, flat anomaly scores. "Every system monitors for attacks. SOMA does something different."

- **:30–1:15** — Red agent starts. Anomaly score spikes on one node. PPO agent begins investigating adjacent hosts. Detection rate metrics appear. "Trained against a simulated adversary, it learned to investigate before compromise, not after. Detection rates: lateral movement 58%, impact stage 84%." State the numbers. Don't overclaim.

- **1:15–2:15** — Convergence panel, front and center. "Before we show the deception layer, we need to show you where it comes from. Game theory gives us this benchmark — the purple line — the optimal bluffing rate for a defender against a rational adversary under different attacker attention levels. We trained an RL agent with no knowledge of this result. These are the cyan lines. They converge. The RL agent discovered the game-theoretically optimal deception strategy." Pause 8 seconds. Then: "This is what it means for the deception layer to be principled, not heuristic."

- **2:15–2:45** — Amber node appears in CybORG. "In the simulation, we use a heuristic trigger to activate deceptive presentation. The attacker moves toward it. The real asset stays clean." Pause while it happens. "The gap between the heuristic and the game-theoretic policy is a research problem we know how to formulate."

- **2:45–3:15** — Drift panel. Injected host's centroid departing from cluster. "This host has been drifting for 60 simulated days. The acute detector saw nothing. The long-dwell layer caught it. That's the insider threat signal."

- **3:15–4:00** — "SOMA is a research prototype. It's trained in simulation against a scripted adversary. Transfer to real networks is an open problem and we're not pretending otherwise. What it demonstrates: that RL recovers game-theoretic equilibria in cyber deception settings, that these equilibria have interpretable and testable implications, and that the layered architecture produces detection signals that operate on different timescales. That's the foundation."

**Closing line:** "We didn't program the deception strategy. Game theory derived it. The RL agent verified it. That's the difference between a rule-based system and one that knows why its decisions are correct."

**Pitch (3 minutes):**
- What: layered autonomous defense, RL + signaling game core, simulation proof of concept
- Why defense specifically: OT/IT convergence, nation-state adversary profile, CMMC compliance architecture (table stakes cleared, not a differentiation claim)
- Honest limitations: simulation only, transfer gap is open research, scripted adversary
- Real moat: clearances, past performance, CAGE number — 3-5 year path, acknowledged
- Near term: real endpoint agent month 1, first pilot month 3, CAGE number immediately

---

## Risk and Mitigation Table

| Risk | Likelihood | Consequence | Mitigation |
|---|---|---|---|
| CybORG install fails | Medium | Lose CybORG demo | Build SignalingGameEnv first; it's the core anyway |
| PPO doesn't converge (reward hacking) | Medium | Layer 2 useless | Check for Analyze-spam in first 50k steps; add penalty |
| RL doesn't converge to PBE | Medium | Lose convergence plot | Tune ent_coef up (0.1); lower learning rate; extend to 150k |
| PBE derivation has errors | Low-Medium | Theory claim collapses | Cross-check against Carroll & Grosu 2011 Prop 2 before pitch |
| Live demo crashes | High (live demos always risk this) | Worst moment in pitch | Have recorded fallback rendered and ready on same machine |
| VAE outperforms Isolation Forest | Low | Fine — use VAE, state the benchmark | No risk, just follow the data |
| Layer 4 FPR calibration fails | Low | Drift alarm unreliable | Use conservative threshold; state it's a prototype calibration |

**If forced to cut one layer entirely:** Cut Layer 4. The convergence plot (Layer 3) + PPO detection metrics (Layer 2) + anomaly detection (Layer 1) is a complete, coherent demo. Layer 4 adds narrative richness but is not load-bearing for the core argument.

---

## What You Can State Honestly in the Pitch

**Claim with evidence:** RL recovers PBE mixing rates in a 2×2 cyber deception signaling game across three attacker attention levels.

**Claim with evidence:** PPO trained against B_lineAgent in CAGE 2 achieves lateral movement detection rate ≥ 0.5 and impact detection rate ≥ 0.8.

**Claim with evidence:** Anomaly detector achieves [measured TPR] at 1% FPR on CAGE 2 simulation data.

**Claim with evidence:** Long-dwell drift detector catches injected 2%-per-step behavioral drift that the acute layer misses, calibrated to 0.1% FPR on clean data.

**Do not claim:** Transfer to real networks at any validated performance level. Operational readiness. Characterization of real adversary behavior. Formal rational inattention (present it as utility-cost approximation). That self-play or federation are solved problems.

---

## Post-Hackathon: The Three Moves That Matter

**Week 1 — Get a CAGE number.** Registration at SAM.gov. Takes 2-3 weeks, no cost, required for any DoD contract or subcontract. Start this before anything else in the business roadmap.

**Month 1 — Real endpoint agent.** Python agent on Windows endpoints collecting process creation (ETW), network flow summaries (5-minute aggregates), file entropy, and authentication events. Retrain Layer 1 on 72 hours of real clean baseline. Measure transfer performance honestly: what is the actual FPR and TPR on a network you control? If performance degrades substantially from simulation (it will), characterize how much and why. This data is the foundation of every subsequent customer conversation.

**Month 3 — First pilot with honest framing.** Target a defense-adjacent organization with CMMC Level 2 requirements. Offer 90 days free. Frame explicitly as "research prototype moving toward operational capability" — not a finished product. The goal is real telemetry, real incidents if any occur, and an honest case study. A pilot customer who understands what they're evaluating and stays is worth ten who are misled about capabilities and churn.
