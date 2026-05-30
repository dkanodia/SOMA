"""
soma/envs/synthetic_network_gen.py
====================================
Synthetic network episode generator for SOMA demos and training.

Simulates a 6-host network (mirroring CAGE 2 Scenario1b topology) with
controllable attack progression. Used when CybORG is unavailable or for
fast iteration on the immune layer stack.

Observation: 30-dim float32 vector — 6 hosts × 5 features.
Features per host: [activity, compromised, sessions, processes, network_pos]
"""

import numpy as np
from typing import Optional

HOST_NAMES        = ["User0", "User1", "User2", "Enterprise0", "Enterprise1", "Op_Server0"]
FEATURES_PER_HOST = 5
N_HOSTS           = len(HOST_NAMES)
OBS_DIM           = N_HOSTS * FEATURES_PER_HOST

# Attack phases and the host indices they involve
ATTACK_PHASES = [
    "clean",
    "initial_access",
    "lateral_movement",
    "privilege_escalation",
    "impact",
]

# Lateral movement path: User0 → User1 → Enterprise0 → Op_Server0
ATTACK_PATH = [0, 1, 3, 5]   # indices into HOST_NAMES


# ---------------------------------------------------------------------------
# Clean baseline per-host parameters (mean, std)
# ---------------------------------------------------------------------------
_CLEAN_MEAN = np.array([
    # activity, compromised, sessions, processes, network_pos
    0.15, 0.0, 0.10, 0.20, 0.10,  # User0
    0.12, 0.0, 0.08, 0.18, 0.10,  # User1
    0.10, 0.0, 0.07, 0.15, 0.10,  # User2
    0.20, 0.0, 0.15, 0.25, 0.50,  # Enterprise0
    0.18, 0.0, 0.12, 0.22, 0.50,  # Enterprise1
    0.25, 0.0, 0.20, 0.30, 0.90,  # Op_Server0
], dtype=np.float32)

_CLEAN_STD = np.array([
    0.05, 0.0, 0.03, 0.05, 0.01,
    0.04, 0.0, 0.03, 0.04, 0.01,
    0.04, 0.0, 0.02, 0.04, 0.01,
    0.06, 0.0, 0.05, 0.06, 0.01,
    0.05, 0.0, 0.04, 0.05, 0.01,
    0.07, 0.0, 0.06, 0.08, 0.01,
], dtype=np.float32)


class SyntheticNetworkGen:
    """
    Deterministic (seeded) synthetic episode generator.

    Parameters
    ----------
    episode_length : int
    attack_start   : int   Step at which attack begins.
    stealth        : float 0=obvious (large spikes), 1=sophisticated (slow drift).
    seed           : int
    """

    def __init__(
        self,
        episode_length: int   = 60,
        attack_start:   int   = 10,
        stealth:        float = 0.0,
        seed:           int   = 42,
    ):
        self.episode_length = episode_length
        self.attack_start   = attack_start
        self.stealth        = stealth
        self.rng            = np.random.default_rng(seed)

        self._t              = 0
        self._compromised    = set()
        self._drift_state    = np.zeros(OBS_DIM, dtype=np.float32)

    def reset(self):
        self._t           = 0
        self._compromised = set()
        self._drift_state = np.zeros(OBS_DIM, dtype=np.float32)

    def step(self):
        t       = self._t
        is_atk  = t >= self.attack_start
        phase   = self._phase(t)

        obs = _CLEAN_MEAN.copy()
        obs += self.rng.normal(0, _CLEAN_STD).astype(np.float32)

        if is_atk:
            obs = self._inject_attack(obs, t)

        obs = np.clip(obs, 0.0, 1.0)
        info = {
            "phase":             phase,
            "compromised_hosts": list(self._compromised),
        }
        self._t += 1
        return obs, is_atk, info

    # ------------------------------------------------------------------
    def _phase(self, t: int) -> str:
        if t < self.attack_start:
            return "clean"
        rel = t - self.attack_start
        if rel < 3:
            return "initial_access"
        if rel < 8:
            return "lateral_movement"
        if rel < 12:
            return "privilege_escalation"
        return "impact"

    def _inject_attack(self, obs: np.ndarray, t: int) -> np.ndarray:
        rel      = t - self.attack_start
        stealth  = self.stealth

        # Obvious attacks: large spikes visible to fast anomaly detection.
        # Sophisticated attacks: tiny per-step spikes that drift cumulatively —
        # individually sub-threshold for innate, detectable by memory.
        direct_amp = (1.0 - stealth) * 0.45          # obvious=0.45, stealth=0.9 → 0.045
        drift_step = stealth * 0.003                  # stealth=0.9 → 0.0027 per step (slow, cumulative)

        # Which hosts are currently under attack
        n_hosts_active = min(1 + rel // 4, len(ATTACK_PATH))
        for idx in ATTACK_PATH[:n_hosts_active]:
            h_name = HOST_NAMES[idx]
            self._compromised.add(h_name)
            start  = idx * FEATURES_PER_HOST

            # Obvious: hard spike on activity, compromised, sessions
            noise = float(self.rng.uniform(0, 0.05))
            obs[start + 0] = min(1.0, obs[start + 0] + direct_amp + noise)
            obs[start + 1] = min(1.0, (1.0 - stealth))          # compromised flag obvious only
            obs[start + 2] = min(1.0, obs[start + 2] + direct_amp * 0.8)
            obs[start + 3] = min(1.0, obs[start + 3] + direct_amp * 0.5)

        # Sophisticated: accumulate slow drift across all features
        if stealth > 0.3:
            self._drift_state += (self.rng.normal(0, drift_step, OBS_DIM)).astype(np.float32)
            obs += self._drift_state

        return obs


# ---------------------------------------------------------------------------
# Convenience generators
# ---------------------------------------------------------------------------

def generate_attack_episode(
    stealth:      float = 0.0,
    n_steps:      int   = 60,
    attack_start: int   = 10,
    seed:         int   = 42,
):
    """
    Returns (obs_arr, labels, infos).
      obs_arr : ndarray shape (n_steps, 30)
      labels  : bool ndarray shape (n_steps,) — True during attack
      infos   : list of info dicts
    """
    gen = SyntheticNetworkGen(
        episode_length=n_steps, attack_start=attack_start,
        stealth=stealth, seed=seed,
    )
    gen.reset()
    obs_list, labels, infos = [], [], []
    for _ in range(n_steps):
        obs, is_atk, info = gen.step()
        obs_list.append(obs)
        labels.append(is_atk)
        infos.append(info)
    return np.array(obs_list, dtype=np.float32), np.array(labels, dtype=bool), infos


def generate_clean_episodes(n_steps: int = 1200, seed: int = 999) -> np.ndarray:
    """
    Returns ndarray shape (n_steps, 30) — clean (no attack) observations.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_steps):
        obs = _CLEAN_MEAN.copy()
        obs += rng.normal(0, _CLEAN_STD).astype(np.float32)
        rows.append(np.clip(obs, 0.0, 1.0))
    return np.array(rows, dtype=np.float32)
