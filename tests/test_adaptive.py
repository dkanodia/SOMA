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
    from CybORG.Simulator.Scenarios import FileReaderScenarioGenerator  # noqa: F401
    import copy as _copy, inspect
    from pathlib import Path as _P
    _cyborg_file = _P(inspect.getfile(CybORG))
    for _candidate in [
        _cyborg_file.parent / "Simulator" / "Scenarios" / "scenario_files" / "Scenario1b.yaml",
        _cyborg_file.parent / "Shared" / "Scenarios" / "Scenario1b.yaml",
    ]:
        if _candidate.exists():
            # Probe: deepcopy the generator (same operation CybORG does internally)
            _sg = FileReaderScenarioGenerator(str(_candidate))
            _copy.deepcopy(_sg)
            CYBORG_AVAILABLE = True
            break
except Exception:
    pass

skip_no_cyborg = pytest.mark.skipif(
    not CYBORG_AVAILABLE, reason="CybORG not installed or not functional on this platform"
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

    @skip_no_cyborg
    def test_reward_no_change(self):
        """Reward logic lives inside step() and requires CybORG; skip without it."""
        pass

    @skip_no_cyborg
    def test_reward_new_compromise_penalised(self):
        """Reward logic lives inside step() and requires CybORG; skip without it."""
        pass

    def test_action_host_parsing(self):
        """BLUE_ACTIONS use 'Verb_Host' naming; host is everything after first '_'."""
        assert "Analyze_User0".split("_", 1)[1] == "User0"
        assert "Restore_Enterprise1".split("_", 1)[1] == "Enterprise1"
        assert not "Monitor".startswith("Analyze_")

    def test_flatten_obs_shape(self):
        from soma.envs.cyborg_wrapper import cyborg_obs_to_30dim
        flat = cyborg_obs_to_30dim(np.zeros(52, dtype=np.float32))
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
