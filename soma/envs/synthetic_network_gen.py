"""
soma/envs/synthetic_network_gen.py
====================================
Synthetic CybORG-compatible network episode generator.

Used when CybORG is not installed. Produces the same (30,) observation
format as CybORGWrapper: 6 hosts × 5 features each.

Features per host (matching cyborg_wrapper.py):
  [activity, compromised, session_count, process_count, network_position]

Host roles:
  User0/1/2          — workstations (low activity, few sessions)
  Enterprise0/1      — servers (higher activity, many sessions)
  Op_Server0         — critical (controlled, restricted)

B_lineAgent attack phases (deterministic, mirroring CAGE 2):
  initial_access      — steps 1-3:  User0 compromised
  lateral_movement    — steps 4-8:  Enterprise0 compromised
  privilege_escalation— steps 9-12: Enterprise1 compromised
  impact              — steps 13+:  Op_Server0 targeted

Stealth knob:
  stealth=0.0 → obvious attack (sudden spikes)
  stealth=1.0 → sophisticated attack (slow drift, low-and-slow)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants (matching cyborg_wrapper.py)
# ---------------------------------------------------------------------------

HOST_NAMES = [
    "User0", "User1", "User2",
    "Enterprise0", "Enterprise1",
    "Op_Server0",
]
FEATURES_PER_HOST = 5
N_HOSTS           = len(HOST_NAMES)
OBS_DIM           = N_HOSTS * FEATURES_PER_HOST

ATTACK_PHASES = [
    "initial_access",
    "lateral_movement",
    "privilege_escalation",
    "impact",
]

# Host role index
HOST_ROLE = {
    "User0": "workstation", "User1": "workstation", "User2": "workstation",
    "Enterprise0": "server", "Enterprise1": "server",
    "Op_Server0": "critical",
}

# ---------------------------------------------------------------------------
# Per-host clean baselines: (mean, std) for each of the 5 features
#   [activity, compromised, sessions, processes, network_pos]
# ---------------------------------------------------------------------------
_CLEAN_BASELINE = {
    "User0":       np.array([[0.15, 0.05], [0.0, 0.0], [1.5, 0.5], [4.0, 1.0], [0.10, 0.02]]),
    "User1":       np.array([[0.12, 0.04], [0.0, 0.0], [1.2, 0.4], [3.5, 0.8], [0.20, 0.02]]),
    "User2":       np.array([[0.18, 0.06], [0.0, 0.0], [1.8, 0.6], [4.5, 1.0], [0.30, 0.02]]),
    "Enterprise0": np.array([[0.45, 0.10], [0.0, 0.0], [6.0, 1.5], [12.0, 2.5], [0.55, 0.03]]),
    "Enterprise1": np.array([[0.40, 0.08], [0.0, 0.0], [5.5, 1.2], [11.0, 2.0], [0.65, 0.03]]),
    "Op_Server0":  np.array([[0.25, 0.05], [0.0, 0.0], [3.0, 0.8], [7.0, 1.2], [0.90, 0.01]]),
}

# Attack delta at PEAK (stealth=0, impact phase) per host being attacked
_ATTACK_DELTA = {
    "User0":       np.array([+0.60, +1.0, +4.0, +3.0,  0.0]),
    "User1":       np.array([+0.40, +1.0, +3.0, +2.0,  0.0]),
    "User2":       np.array([+0.40, +1.0, +3.0, +2.0,  0.0]),
    "Enterprise0": np.array([+0.50, +1.0, +8.0, +6.0,  0.0]),
    "Enterprise1": np.array([+0.50, +1.0, +7.0, +5.0,  0.0]),
    "Op_Server0":  np.array([+0.70, +1.0, +5.0, +4.0,  0.0]),
}

# Which hosts are targeted in each phase (ordered by kill-chain progression)
_PHASE_TARGETS = {
    "initial_access":       ["User0"],
    "lateral_movement":     ["User0", "Enterprise0"],
    "privilege_escalation": ["User0", "Enterprise0", "Enterprise1"],
    "impact":               ["User0", "Enterprise0", "Enterprise1", "Op_Server0"],
}

# Phase scale (fraction of peak delta applied per phase)
_PHASE_SCALE = {
    "initial_access":       0.30,
    "lateral_movement":     0.60,
    "privilege_escalation": 0.85,
    "impact":               1.00,
}


# ---------------------------------------------------------------------------
# Per-host state
# ---------------------------------------------------------------------------

@dataclass
class HostState:
    name:       str
    role:       str
    compromised: bool = False
    _cum_drift: np.ndarray = field(default_factory=lambda: np.zeros(FEATURES_PER_HOST))


# ---------------------------------------------------------------------------
# Synthetic network generator
# ---------------------------------------------------------------------------

class SyntheticNetworkGen:
    """
    Generates CybORG-compatible network episodes without CybORG.

    Usage:
        gen = SyntheticNetworkGen(seed=42)
        gen.reset()
        for _ in range(50):
            obs, label, info = gen.step()
    """

    def __init__(
        self,
        episode_length: int   = 50,
        attack_start:   int   = 5,     # step when attack begins
        stealth:        float = 0.0,   # 0=obvious, 1=sophisticated
        seed:           int   = 42,
    ):
        self.episode_length = episode_length
        self.attack_start   = attack_start
        self.stealth        = stealth
        self.seed           = seed
        self._rng           = np.random.default_rng(seed)
        self._step          = 0
        self._hosts: list[HostState] = []

    def reset(self) -> np.ndarray:
        self._rng   = np.random.default_rng(self.seed)
        self._step  = 0
        self._hosts = [HostState(name=h, role=HOST_ROLE[h]) for h in HOST_NAMES]
        return self._obs()

    def step(self) -> tuple[np.ndarray, bool, dict]:
        """
        Advance one step. Returns (obs, is_attack, info).
        obs: shape (30,) — 6 hosts × 5 features
        is_attack: True if any host is under active attack this step
        info: {step, phase, compromised_hosts}
        """
        self._step += 1
        phase    = self._current_phase()
        is_atk   = (phase != "clean")
        obs      = self._obs(phase)
        comp     = [h.name for h in self._hosts if h.compromised]
        return obs, is_atk, {"step": self._step, "phase": phase, "compromised_hosts": comp}

    # ------------------------------------------------------------------
    def _current_phase(self) -> str:
        if not self._should_attack():
            return "clean"
        steps_since = self._step - self.attack_start
        if steps_since < 3:
            return "initial_access"
        elif steps_since < 8:
            return "lateral_movement"
        elif steps_since < 12:
            return "privilege_escalation"
        else:
            return "impact"

    def _should_attack(self) -> bool:
        return self._step >= self.attack_start

    def _obs(self, phase: str = "clean") -> np.ndarray:
        vecs = []
        targets = _PHASE_TARGETS.get(phase, [])
        scale   = _PHASE_SCALE.get(phase, 0.0)

        for hs in self._hosts:
            bl   = _CLEAN_BASELINE[hs.name]
            feat = self._rng.normal(bl[:, 0], bl[:, 1].clip(0.001))

            # compromised is always binary — sample from baseline mean (usually 0)
            feat[1] = 0.0

            if hs.name in targets:
                delta = _ATTACK_DELTA[hs.name] * scale

                if self.stealth > 0:
                    # Sophisticated: accumulate tiny drift per step
                    rate = 0.05 * (1 - self.stealth)
                    hs._cum_drift += delta * rate
                    hs._cum_drift = np.clip(hs._cum_drift, 0, delta * 1.5)
                    effective = delta * (1 - self.stealth) + hs._cum_drift * self.stealth
                else:
                    effective = delta

                feat = feat + effective
                feat[1] = 1.0   # compromised = binary flag
                hs.compromised = True

            feat = self._clamp(feat, hs.name)
            vecs.extend(feat.tolist())

        return np.array(vecs, dtype=np.float32)

    @staticmethod
    def _clamp(feat: np.ndarray, host: str) -> np.ndarray:
        feat[0] = np.clip(feat[0], 0.0, 1.0)   # activity
        feat[1] = float(feat[1] >= 0.5)          # compromised (binary)
        feat[2] = np.clip(feat[2], 0.0, 30.0)   # sessions
        feat[3] = np.clip(feat[3], 0.0, 50.0)   # processes
        feat[4] = np.clip(feat[4], 0.0, 1.0)    # network_pos
        return feat


# ---------------------------------------------------------------------------
# Convenience generators
# ---------------------------------------------------------------------------

def generate_clean_episodes(
    n_steps: int = 1000,
    seed:    int = 0,
) -> np.ndarray:
    """
    Returns X_clean: shape (n_steps, 30) — pure clean network traffic.
    Used to train and calibrate all immune layers.
    """
    gen = SyntheticNetworkGen(
        episode_length=n_steps,
        attack_start=n_steps + 1,   # never attack
        stealth=0.0,
        seed=seed,
    )
    gen.reset()
    rows = []
    for _ in range(n_steps):
        obs, _, _ = gen.step()
        rows.append(obs)
    return np.array(rows, dtype=np.float32)


def generate_attack_episode(
    stealth:        float = 0.0,
    n_steps:        int   = 50,
    attack_start:   int   = 10,
    seed:           int   = 0,
) -> tuple[np.ndarray, np.ndarray, list]:
    """
    Returns (obs_arr, labels, infos) for one attack episode.
    obs_arr: shape (n_steps, 30)
    labels:  shape (n_steps,) bool — True if attack step
    infos:   list of dicts with step/phase/compromised_hosts
    """
    gen = SyntheticNetworkGen(
        episode_length=n_steps,
        attack_start=attack_start,
        stealth=stealth,
        seed=seed,
    )
    gen.reset()
    obs_list, labels, infos = [], [], []
    for _ in range(n_steps):
        obs, is_atk, info = gen.step()
        obs_list.append(obs)
        labels.append(is_atk)
        infos.append(info)
    return np.array(obs_list, dtype=np.float32), np.array(labels, dtype=bool), infos
