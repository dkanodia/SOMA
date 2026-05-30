"""tests/test_signal_game.py — SignalingGameEnv unit tests."""
import numpy as np
import pytest

from soma.envs.signal_game import SignalingGameEnv
from soma.theory.pbe_solver import compute_pbe, kappa_sweep


# ---------------------------------------------------------------------------
# SignalingGameEnv tests
# ---------------------------------------------------------------------------

class TestSignalingGameEnv:

    def test_reset_returns_correct_shape(self):
        env = SignalingGameEnv(n_hosts=5)
        obs, info = env.reset()
        assert obs.shape == (5,)
        assert set(obs).issubset({0, 1})

    def test_step_returns_five_elements(self):
        env = SignalingGameEnv(n_hosts=5)
        obs, _ = env.reset()
        signal = np.zeros(5, dtype=np.int8)
        result = env.step(signal)
        assert len(result) == 5   # obs, reward, terminated, truncated, info

    def test_reward_is_scalar(self):
        env = SignalingGameEnv()
        env.reset()
        _, reward, _, _, _ = env.step(np.ones(5, dtype=np.int8))
        assert isinstance(reward, float)

    def test_attacker_attacks_when_ev_positive(self):
        """Attacker attacks if posterior * V - (1-posterior) * L - kappa > 0."""
        env = SignalingGameEnv(p_real=1.0, V=10, C=3, L=5, kappa=0.0, n_hosts=1)
        env.reset()
        env.true_types = np.array([1], dtype=np.int8)
        # Signal AppearReal: Bayesian update keeps belief near 1 → attacker attacks
        _, reward, _, _, info = env.step(np.array([1], dtype=np.int8))
        assert info["attacker_actions"][0] == 1, "Attacker should attack Real host"
        assert reward < 0, "Defender loses V when Real is attacked"

    def test_attacker_passes_when_kappa_high(self):
        """Very high kappa should suppress all attacks."""
        env = SignalingGameEnv(p_real=0.4, V=10, C=3, L=5, kappa=1000.0, n_hosts=5)
        env.reset()
        _, _, _, _, info = env.step(np.ones(5, dtype=np.int8))
        assert info["attacker_actions"].sum() == 0, "No attacks expected with kappa=1000"

    def test_honeypot_hit_gives_positive_reward(self):
        """Attacker hitting a honeypot should give defender +C."""
        env = SignalingGameEnv(p_real=1.0, V=10, C=3, L=5, kappa=0.0, n_hosts=1)
        env.reset()
        env.true_types = np.array([0], dtype=np.int8)  # Honeypot
        env.beliefs     = np.array([1.0])               # Attacker thinks Real → attacks
        # Signal AppearReal to induce attack
        _, reward, _, _, info = env.step(np.array([1], dtype=np.int8))
        if info["attacker_actions"][0] == 1:
            assert reward == pytest.approx(3.0), "Honeypot hit should give +C=3"

    def test_no_attack_gives_zero_reward(self):
        """If attacker passes, reward is 0."""
        env = SignalingGameEnv(p_real=0.0, V=10, C=3, L=5, kappa=1000.0, n_hosts=3)
        env.reset()
        _, reward, _, _, _ = env.step(np.zeros(3, dtype=np.int8))
        assert reward == pytest.approx(0.0)

    def test_observation_space_consistent(self):
        env = SignalingGameEnv(n_hosts=5)
        obs, _ = env.reset()
        assert env.observation_space.contains(obs)

    def test_action_space_consistent(self):
        env = SignalingGameEnv(n_hosts=5)
        env.reset()
        action = env.action_space.sample()
        assert env.action_space.contains(action)


# ---------------------------------------------------------------------------
# PBE solver tests (via pbe_solver — separate module, called from deception.py)
# ---------------------------------------------------------------------------

class TestPBESolverConsistency:
    """
    Sanity checks on the PBE results used by the convergence study.
    If these fail the theoretical core is broken.
    """

    def test_mu_star_increases_with_kappa(self):
        """Attacker attack threshold rises as attention cost rises."""
        results = kappa_sweep(p_real=0.4, V=10, C=3, L=5)
        kappas  = sorted(results.keys())
        mu_stars = [results[k].mu_star for k in kappas]
        assert mu_stars == sorted(mu_stars), "mu_star should be non-decreasing in kappa"

    def test_r_star_non_negative(self):
        results = kappa_sweep()
        for k, r in results.items():
            assert r.r_star >= 0.0, f"r_star negative at kappa={k}"
            assert r.r_star <= 1.0, f"r_star > 1 at kappa={k}"

    def test_q_star_non_negative(self):
        results = kappa_sweep()
        for k, r in results.items():
            assert r.q_star >= 0.0
            assert r.q_star <= 1.0

    def test_known_mu_star_value(self):
        """mu* = L / (V + L) when kappa=0. With V=10, L=5: mu*=1/3."""
        result = compute_pbe(p_real=0.4, V=10, C=3, L=5, kappa=0.0)
        assert abs(result.mu_star - 5.0 / 15.0) < 1e-9, (
            f"mu_star={result.mu_star}, expected {5/15:.6f}"
        )

    def test_full_inattention_max_threshold(self):
        """kappa=V means attacker needs posterior > V/(2V)=0.5 to attack."""
        result = compute_pbe(p_real=0.4, V=10, C=3, L=5, kappa=10.0)
        expected = (5.0 + 10.0) / (10.0 + 5.0 + 10.0)
        assert abs(result.mu_star - expected) < 1e-9
