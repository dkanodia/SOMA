"""
soma/envs/cyborg_wrapper.py
============================
Gymnasium-compatible wrapper for CybORG CAGE 2.

Requires CybORG to be installed separately:
  git clone https://github.com/cage-challenge/cage-challenge-2
  cd cage-challenge-2 && pip install -e .

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


# Host names in CAGE 2 Scenario1b — update if scenario changes
HOST_NAMES = [
    "User0", "User1", "User2",
    "Enterprise0", "Enterprise1",
    "Op_Server0",
]

# Blue agent actions available in CAGE 2
BLUE_ACTIONS = [
    "Monitor",
    "Analyze_User0",    "Analyze_User1",    "Analyze_User2",
    "Analyze_Enterprise0", "Analyze_Enterprise1", "Analyze_Op_Server0",
    "Remove_User0",     "Remove_User1",     "Remove_User2",
    "Remove_Enterprise0", "Remove_Enterprise1", "Remove_Op_Server0",
    "Restore_User0",    "Restore_User1",    "Restore_User2",
    "Restore_Enterprise0", "Restore_Enterprise1", "Restore_Op_Server0",
]

FEATURES_PER_HOST = 5
N_HOSTS           = len(HOST_NAMES)


class CybORGWrapper(gym.Env):
    """
    Wraps CAGE 2 CybORG for use with Stable Baselines3.

    Observation
    -----------
    Flat float32 vector of shape (N_HOSTS * FEATURES_PER_HOST,):
      [activity, compromised, session_count, process_count, network_position]
      per host, concatenated in HOST_NAMES order.

    Action
    ------
    Discrete index into BLUE_ACTIONS.

    Notes
    -----
    - B_lineAgent is used as the red agent (scripted, deterministic).
    - The agent trained here is frozen at deployment — NOT online adaptive.
    - FPR budget: 1% of clean-episode steps flagged as anomalous.
      Calibrated in soma/eval/fpr_calibration.py.
    """

    metadata = {"render_modes": []}

    def __init__(self, scenario_path: Optional[str] = None):
        super().__init__()

        # TODO: resolve CybORG import and scenario path
        # from CybORG import CybORG
        # from CybORG.Agents import B_lineAgent
        # if scenario_path is None:
        #     import inspect
        #     cyborg_file = str(inspect.getfile(CybORG))
        #     scenario_path = cyborg_file[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
        # self._env = CybORG(scenario_path, "sim", agents={"Red": B_lineAgent()})

        self._env          = None   # set in reset() after CybORG import
        self._prev_raw_obs = None
        self._step_count   = 0
        self._recently_analyzed: set = set()  # hosts analyzed in last 5 steps

        obs_dim = N_HOSTS * FEATURES_PER_HOST
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(len(BLUE_ACTIONS))

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        # TODO: raw_obs = self._env.reset()
        raw_obs          = {}   # placeholder
        self._prev_raw_obs = raw_obs
        self._step_count = 0
        self._recently_analyzed.clear()
        return self._flatten(raw_obs), {}

    # ------------------------------------------------------------------
    def step(self, action: int):
        action_str = BLUE_ACTIONS[action]
        host       = self._action_host(action_str)

        # TODO: result = self._env.step(action=action_str, agent="Blue")
        result     = ({}, 0.0, False, {})  # placeholder
        raw_obs, _, done, info = result

        reward = self._compute_reward(raw_obs, self._prev_raw_obs, action_str, host)

        self._update_recently_analyzed(host, action_str)
        self._prev_raw_obs = raw_obs
        self._step_count  += 1

        return self._flatten(raw_obs), reward, done, False, info

    # ------------------------------------------------------------------
    def _flatten(self, raw_obs: dict) -> np.ndarray:
        """Convert raw CybORG observation dict to flat float32 vector."""
        vecs = []
        for host in HOST_NAMES:
            h = raw_obs.get(host, {})
            vecs.extend([
                float(h.get("Activity",    0)),
                float(h.get("Compromised", 0)),
                float(len(h.get("Sessions",  []))),
                float(len(h.get("Processes", []))),
                float(h.get("Interface", {}).get("IP_Address", 0)) % 256 / 255.0,
            ])
        return np.array(vecs, dtype=np.float32)

    # ------------------------------------------------------------------
    def _compute_reward(self, curr, prev, action_str, host) -> float:
        """
        Reward function with explicit repeated-Analyze penalty to prevent
        reward hacking (agent spamming Analyze on noisy-activity hosts).
        """
        if prev is None:
            return 0.0

        reward = 0.0
        for h in HOST_NAMES:
            c_comp = float(curr.get(h, {}).get("Compromised", 0))
            p_comp = float(prev.get(h, {}).get("Compromised", 0))
            p_act  = float(prev.get(h, {}).get("Activity",    0))

            # Detected lateral movement before compromise
            if c_comp == 0 and p_act > 0:
                reward += 8.0

            # New compromise — missed detection
            if c_comp == 1 and p_comp == 0:
                reward -= 10.0

            # False positive: acted on a clean host
            if host == h and action_str.startswith(("Remove_", "Restore_")):
                if c_comp == 0:
                    reward -= 4.0

            # Repeated Analyze on recently-analyzed clean host → reward hacking guard
            if host == h and action_str.startswith("Analyze_"):
                if h in self._recently_analyzed and c_comp == 0:
                    reward -= 2.0

        reward -= 0.5   # per-step efficiency penalty
        return reward

    # ------------------------------------------------------------------
    def _action_host(self, action_str: str) -> Optional[str]:
        for h in HOST_NAMES:
            if action_str.endswith(h):
                return h
        return None

    def _update_recently_analyzed(self, host, action_str):
        if host and action_str.startswith("Analyze_"):
            self._recently_analyzed.add(host)
        # Expire after 5 steps — crude sliding window
        if self._step_count % 5 == 0:
            self._recently_analyzed.clear()

    def render(self):
        pass

    def close(self):
        if self._env:
            pass   # CybORG has no explicit close
