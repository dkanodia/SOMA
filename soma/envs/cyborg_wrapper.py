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

        self.observation_space = spaces.Box(
            low=0, high=255, shape=(OBS_DIM,), dtype=np.int64
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

    # ------------------------------------------------------------------
    def _init_cyborg(self):
        from CybORG import CybORG
        from CybORG.Agents import B_lineAgent
        from CybORG.Agents.Wrappers import ChallengeWrapper
        import inspect
        from pathlib import Path as _Path

        if self._scenario_path is None:
            cyborg_file = _Path(inspect.getfile(CybORG))
            self._scenario_path = str(
                cyborg_file.parent / "Shared" / "Scenarios" / "Scenario1b.yaml"
            )

        agents = {"Red": B_lineAgent} if self._include_red else {}
        cyborg = CybORG(self._scenario_path, "sim", agents=agents)
        self._env = ChallengeWrapper(agent_name="Blue", env=cyborg)

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self._env is None:
            self._init_cyborg()
        obs = self._env.reset()
        self._step_count = 0
        return np.array(obs, dtype=np.int64), {}

    # ------------------------------------------------------------------
    def step(self, action: int):
        obs, reward, done, info = self._env.step(action=int(action))
        self._step_count += 1
        if info is None:
            info = {}
        # Expose deterministic red agent phase index for detection labelling.
        info["red_agent_step"] = self._step_count
        return np.array(obs, dtype=np.int64), float(reward), bool(done), False, info

    # ------------------------------------------------------------------
    def render(self):
        pass

    def close(self):
        pass
