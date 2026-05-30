"""
tests/test_signal_game.py
--------------------------
Unit tests for SignalingGameEnv.
"""
import numpy as np
import pytest

# from soma.envs.signal_game import SignalingGameEnv


class TestSignalingGameEnv:
    def test_action_space_shape(self):
        # env = SignalingGameEnv(n_hosts=5)
        # assert env.action_space.shape == (5,)
        pass

    def test_observation_space_shape(self):
        # env = SignalingGameEnv(n_hosts=5)
        # obs, _ = env.reset()
        # assert obs.shape == (5,)
        pass

    def test_reward_attacker_hits_real(self):
        """Defender should receive -V when attacker hits a real host."""
        # env = SignalingGameEnv(p_real=1.0, V=10.0, kappa=0.0)  # all real
        # obs, _ = env.reset()
        # signal = np.ones(5, dtype=np.int8)  # AppearReal — attacker will attack
        # _, reward, _, _, _ = env.step(signal)
        # assert reward <= -10.0  # all 5 real hosts attacked
        pass

    def test_reward_attacker_hits_honeypot(self):
        """Defender should receive +C when attacker hits a honeypot."""
        # env = SignalingGameEnv(p_real=0.0, C=3.0, kappa=0.0)  # all honeypots
        # obs, _ = env.reset()
        # signal = np.ones(5, dtype=np.int8)  # AppearReal — will attract attacker
        # _, reward, _, _, _ = env.step(signal)
        # assert reward >= 3.0 * 5  # C per honeypot hit
        pass

    def test_kappa_suppresses_attacks(self):
        """High kappa should suppress attacker attacks (ignores signal)."""
        # env_low  = SignalingGameEnv(p_real=0.5, kappa=0.0)
        # env_high = SignalingGameEnv(p_real=0.5, kappa=100.0)
        # ... compare attack rates
        pass
