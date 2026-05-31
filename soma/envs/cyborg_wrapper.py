"""
soma/envs/cyborg_wrapper.py
============================
Gymnasium-compatible wrapper for CybORG CAGE 2.

Requires CybORG to be installed separately:
  git clone https://github.com/cage-challenge/cage-challenge-2
  cd cage-challenge-2 && pip install -e .

Delegates observation vectorisation and action enumeration to CybORG's own
ChallengeWrapper (BlueTableWrapper → EnumActionWrapper → OpenAIGymWrapper),
which gives a 52-dim int64 observation and Discrete(54) action space.
Our wrapper adds a gymnasium-compatible reset() / step() signature and
exposes red_agent_step in info so detection_metrics.py can label phases.

What B_lineAgent does (its fixed, deterministic attack chain):
  Steps  1-3:  Initial access via known exploit
  Steps  4-8:  Lateral movement to adjacent hosts
  Steps  9-12: Privilege escalation
  Steps 13+:   Impact on target host

B_lineAgent does NOT respond to defender signals.
The signaling game RL policy is NOT applied here.
The heuristic honeypot trigger (see soma/layers/deception.py) is used instead.
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Optional

# ChallengeWrapper observation / action dimensions for CAGE 2 Scenario1b
OBS_DIM    = 52
N_ACTIONS  = 54

# Host names in CAGE 2 Scenario1b (subset monitored by Blue agent)
HOST_NAMES = [
    "User0", "User1", "User2",
    "Enterprise0", "Enterprise1",
    "Op_Server0",
]
FEATURES_PER_HOST = 5
N_HOSTS           = len(HOST_NAMES)

# Logical action labels (maps to EnumActionWrapper's Discrete(54) indices)
BLUE_ACTIONS = [
    "Monitor",
    "Analyze_User0",    "Analyze_User1",    "Analyze_User2",
    "Analyze_Enterprise0", "Analyze_Enterprise1", "Analyze_Op_Server0",
    "Remove_User0",     "Remove_User1",     "Remove_User2",
    "Remove_Enterprise0", "Remove_Enterprise1", "Remove_Op_Server0",
    "Restore_User0",    "Restore_User1",    "Restore_User2",
    "Restore_Enterprise0", "Restore_Enterprise1", "Restore_Op_Server0",
]


class CybORGWrapper(gym.Env):
    """
    Gymnasium wrapper around CybORG CAGE 2 ChallengeWrapper.

    Observation
    -----------
    int64 vector of shape (52,) — produced by CybORG's BlueTableWrapper.

    Action
    ------
    Discrete(54) — produced by CybORG's EnumActionWrapper.

    Notes
    -----
    - B_lineAgent is used as the red agent (scripted, deterministic).
    - The agent trained here is frozen at deployment — NOT online adaptive.
    - include_red=False runs without a red agent (clean data collection).
    """

    metadata = {"render_modes": []}

    def __init__(self, scenario_path: Optional[str] = None, include_red: bool = True):
        super().__init__()
        self._scenario_path = scenario_path
        self._include_red   = include_red
        self._env           = None   # lazy-initialized on first reset()
        self._step_count    = 0
        self._analyze_clean: dict[int, int] = {}  # host_soma_idx -> step last analyzed+clean

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

    # ------------------------------------------------------------------
    def _init_cyborg(self):
        from CybORG import CybORG
        from CybORG.Agents import B_lineAgent
        from CybORG.Agents.Wrappers import ChallengeWrapper
        from CybORG.Simulator.Scenarios import FileReaderScenarioGenerator
        import inspect
        from pathlib import Path as _Path

        # gym.utils.seeding.RandomNumberGenerator (a np.random.Generator subclass)
        # breaks copy.deepcopy with NumPy 1.26 and also lacks .randint() which
        # CybORG's simulator uses (legacy API). Patch the class directly so both
        # deepcopy and randint work, without replacing the seeding function.
        import gym.utils.seeding as _gym_seeding
        _RNG = _gym_seeding.RandomNumberGenerator
        if not hasattr(_RNG, '__deepcopy__'):
            def _rng_deepcopy(self, memo):
                new_rng = _RNG(self.bit_generator.__class__())
                new_rng.bit_generator.state = self.bit_generator.state.copy()
                return new_rng
            _RNG.__deepcopy__ = _rng_deepcopy
        if not hasattr(_RNG, 'randint'):
            def _rng_randint(self, low, high=None, size=None, dtype=int):
                if high is None:
                    low, high = 0, low
                return self.integers(low, high, size=size, dtype=dtype)
            _RNG.randint = _rng_randint

        if self._scenario_path is None:
            cyborg_file = _Path(inspect.getfile(CybORG))
            self._scenario_path = str(
                cyborg_file.parent / "Simulator" / "Scenarios" / "scenario_files" / "Scenario1b.yaml"
            )

        sg = FileReaderScenarioGenerator(self._scenario_path)
        agents = {"Red": B_lineAgent()} if self._include_red else {}
        cyborg = CybORG(sg, "sim", agents=agents)
        self._env = ChallengeWrapper(agent_name="Blue", env=cyborg)

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self._env is None:
            self._init_cyborg()
        obs = self._env.reset()
        self._step_count = 0
        self._analyze_clean.clear()
        return np.array(obs, dtype=np.float32), {}

    # ------------------------------------------------------------------
    def step(self, action: int):
        obs, reward, done, info = self._env.step(action=int(action))
        self._step_count += 1
        if info is None:
            info = {}

        reward = float(reward)

        # Anti-reward-hacking: penalize re-analyzing clean hosts within cooldown window
        action_int = int(action)
        action_name = BLUE_ACTIONS[action_int] if action_int < len(BLUE_ACTIONS) else ""
        if action_name.startswith("Analyze_"):
            host_name = action_name.split("_", 1)[1]
            if host_name in HOST_NAMES:
                soma_idx = HOST_NAMES.index(host_name)
                # Check if penalizing for recent analyze of clean host
                if soma_idx in self._analyze_clean:
                    if (self._step_count - self._analyze_clean[soma_idx]) < 5:
                        reward -= 2.0

                # After the step, check if this host is now clean and update tracking
                if host_name in _CYBORG_HOST_ORDER:
                    obs_raw = np.array(obs, dtype=np.int64)
                    cyborg_idx = _CYBORG_HOST_ORDER.index(host_name)
                    feat_start = cyborg_idx * _CYBORG_FEATURES_PER_HOST
                    exploit = int(obs_raw[feat_start + 1])
                    priv = int(obs_raw[feat_start + 3])
                    if exploit == 0 and priv == 0:
                        self._analyze_clean[soma_idx] = self._step_count

        # Expose deterministic red agent phase index for detection labelling.
        info["red_agent_step"] = self._step_count
        return np.array(obs, dtype=np.float32), reward, bool(done), False, info

    # ------------------------------------------------------------------
    def render(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------------------
# CybORG → 30-dim adapter
# ---------------------------------------------------------------------------

# CybORG BlueTableWrapper host order (13 hosts × 4 features = 52 dim)
# Features per host: [activity_scan, activity_exploit, compromised_unknown, compromised_priv]
_CYBORG_HOST_ORDER = [
    "Defender", "Enterprise0", "Enterprise1", "Enterprise2",
    "Op_Host0", "Op_Host1", "Op_Host2", "Op_Server0",
    "User0", "User1", "User2", "User3", "User4",
]
_CYBORG_FEATURES_PER_HOST = 4

# Fixed network_pos per host (positional prior in the network topology)
_NETWORK_POS = {
    "User0":       0.10, "User1":       0.10, "User2":       0.10,
    "Enterprise0": 0.50, "Enterprise1": 0.50,
    "Op_Server0":  0.90,
}


def cyborg_obs_to_30dim(cyborg_obs: np.ndarray) -> np.ndarray:
    """
    Convert CybORG's 52-dim BlueTableWrapper observation to the 30-dim
    format used by SOMA's immune layers (6 hosts × 5 features).

    CybORG features (per host): [activity_scan, activity_exploit,
                                   compromised_unknown, compromised_priv]
    SOMA features (per host):   [activity, compromised, sessions,
                                   processes, network_pos]

    The mapping: activity = 0.5*scan + 1.0*exploit
                 compromised = 0.33*unknown + 1.0*priv
                 sessions = activity (proxy)
                 processes = compromised (proxy)
                 network_pos = fixed topology value
    """
    obs_30 = np.zeros(len(HOST_NAMES) * FEATURES_PER_HOST, dtype=np.float32)
    cyborg_obs = np.array(cyborg_obs, dtype=np.float32)

    for soma_idx, host in enumerate(HOST_NAMES):
        if host not in _CYBORG_HOST_ORDER:
            continue
        cyborg_idx  = _CYBORG_HOST_ORDER.index(host)
        feat_start  = cyborg_idx * _CYBORG_FEATURES_PER_HOST
        scan        = float(cyborg_obs[feat_start + 0])
        exploit     = float(cyborg_obs[feat_start + 1])
        unknown     = float(cyborg_obs[feat_start + 2])
        priv        = float(cyborg_obs[feat_start + 3])

        activity    = min(1.0, 0.5 * scan + 1.0 * exploit)
        compromised = min(1.0, 0.33 * unknown + 1.0 * priv)

        out_start = soma_idx * FEATURES_PER_HOST
        obs_30[out_start + 0] = activity
        obs_30[out_start + 1] = compromised
        obs_30[out_start + 2] = activity           # sessions proxy
        obs_30[out_start + 3] = compromised        # processes proxy
        obs_30[out_start + 4] = _NETWORK_POS.get(host, 0.5)

    return obs_30


def generate_cyborg_clean_episodes(n_steps: int = 1200, seed: int = 999) -> np.ndarray:
    """
    Collect clean (no red agent) CybORG observations and convert to 30-dim.
    Returns ndarray shape (n_steps, 30).
    Falls back to synthetic if CybORG is not installed.
    """
    try:
        env = CybORGWrapper(include_red=False)
        obs_list = []
        obs, _ = env.reset()
        for _ in range(n_steps):
            obs_30 = cyborg_obs_to_30dim(obs)
            obs_list.append(obs_30)
            obs, _, done, _, _ = env.step(0)   # Monitor
            if done:
                obs, _ = env.reset()
        return np.array(obs_list, dtype=np.float32)
    except Exception as e:
        print(f"[CybORG] Falling back to synthetic clean data ({e})")
        from soma.envs.synthetic_network_gen import generate_clean_episodes
        return generate_clean_episodes(n_steps=n_steps, seed=seed)
