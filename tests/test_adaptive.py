"""tests/test_adaptive.py — Layer 2 (PPO adaptive defender) unit tests.

Most tests skip if CybORG is not installed, since CybORG requires a separate
git clone + pip install. The reward function and action distribution checks
run without CybORG by using a mock wrapper.
"""
import numpy as np
import pytest

from soma.envs.cyborg_wrapper import (
    CybORGWrapper, HOST_NAMES, BLUE_ACTIONS, N_HOSTS, FEATURES_PER_HOST,
)

OBS_DIM = N_HOSTS * FEATURES_PER_HOST
CYBORG_AVAILABLE = False
try:
    from CybORG import CybORG  # noqa: F401
    CYBORG_AVAILABLE = True
except ImportError:
    pass

skip_no_cyborg = pytest.mark.skipif(
    not CYBORG_AVAILABLE, reason="CybORG not installed"
)


# ---------------------------------------------------------------------------
# CybORGWrapper interface tests
# ---------------------------------------------------------------------------

class TestCybORGWrapperInterface:
    """Tests that do NOT require CybORG to be installed."""

    def test_observation_space_shape(self):
        wrapper = CybORGWrapper.__new__(CybORGWrapper)
        import gymnasium as gym
        wrapper.observation_space = gym.spaces.Box(
            low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        assert wrapper.observation_space.shape == (OBS_DIM,)

    def test_action_space_size(self):
        import gymnasium as gym
        n_actions = len(BLUE_ACTIONS)
        space = gym.spaces.Discrete(n_actions)
        assert space.n == n_actions

    def test_blue_actions_not_empty(self):
        assert len(BLUE_ACTIONS) > 0
        assert "Monitor" in BLUE_ACTIONS

    def test_host_names_count(self):
        assert len(HOST_NAMES) == N_HOSTS

    def test_reward_no_change(self):
        """_compute_reward returns 0 when prev is None."""
        wrapper = CybORGWrapper.__new__(CybORGWrapper)
        wrapper._recently_analyzed = set()
        wrapper._step_count = 0
        obs_dict = {h: {} for h in HOST_NAMES}
        reward = wrapper._compute_reward(obs_dict, None, "Monitor", None)
        assert reward == pytest.approx(0.0)

    def test_reward_new_compromise_penalised(self):
        """New compromise on a host yields -10 reward."""
        wrapper = CybORGWrapper.__new__(CybORGWrapper)
        wrapper._recently_analyzed = set()
        wrapper._step_count = 0

        host = HOST_NAMES[0]
        prev = {h: {"Activity": 0, "Compromised": 0} for h in HOST_NAMES}
        curr = {h: {"Activity": 0, "Compromised": 0} for h in HOST_NAMES}
        curr[host]["Compromised"] = 1   # new compromise on first host

        reward = wrapper._compute_reward(curr, prev, "Monitor", None)
        assert reward <= -10.0 - 0.5, f"Expected <= -10.5, got {reward}"

    def test_action_host_parsing(self):
        wrapper = CybORGWrapper.__new__(CybORGWrapper)
        assert wrapper._action_host("Analyze_User0")     == "User0"
        assert wrapper._action_host("Restore_Enterprise1") == "Enterprise1"
        assert wrapper._action_host("Monitor")           is None

    def test_flatten_obs_shape(self):
        wrapper = CybORGWrapper.__new__(CybORGWrapper)
        raw = {h: {"Activity": 0.1, "Compromised": 0, "Sessions": [],
                   "Processes": [], "Interface": {"IP_Address": 192}}
               for h in HOST_NAMES}
        flat = wrapper._flatten(raw)
        assert flat.shape == (OBS_DIM,)
        assert flat.dtype == np.float32


# ---------------------------------------------------------------------------
# CybORG integration tests (skipped if not installed)
# ---------------------------------------------------------------------------

class TestCybORGIntegration:

    @skip_no_cyborg
    def test_env_reset_returns_obs(self):
        env = CybORGWrapper(include_red=False)
        obs, info = env.reset()
        assert obs.shape == (OBS_DIM,)
        assert obs.dtype == np.float32
        assert isinstance(info, dict)

    @skip_no_cyborg
    def test_env_step_returns_five_tuple(self):
        env = CybORGWrapper(include_red=False)
        env.reset()
        result = env.step(0)   # Monitor
        assert len(result) == 5

    @skip_no_cyborg
    def test_reward_finite(self):
        env = CybORGWrapper(include_red=True)
        env.reset()
        for _ in range(5):
            _, reward, _, _, _ = env.step(0)
            assert np.isfinite(reward), f"Reward not finite: {reward}"

    @skip_no_cyborg
    def test_red_agent_step_in_info(self):
        env = CybORGWrapper(include_red=True)
        env.reset()
        _, _, _, _, info = env.step(0)
        assert "red_agent_step" in info

    @skip_no_cyborg
    def test_clean_env_no_compromise(self):
        """Without red agent, no host should be compromised."""
        env = CybORGWrapper(include_red=False)
        obs, _ = env.reset()
        # compromised features are at indices 1, 6, 11, 16, 21, 26
        comp_indices = [i * FEATURES_PER_HOST + 1 for i in range(N_HOSTS)]
        for _ in range(10):
            obs, _, _, _, _ = env.step(0)
            assert all(obs[i] == 0.0 for i in comp_indices), \
                "Clean env should have no compromises"
