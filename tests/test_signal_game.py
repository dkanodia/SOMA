"""tests/test_signal_game.py — Learned attack recognizer + fusion correlator tests."""
import numpy as np
import pytest

from soma.envs.synthetic_network_gen import (
    generate_clean_episodes, generate_attack_episode,
)
from soma.layers.learned_attacks import LearnedAttackRecognizer
from soma.fusion.network_correlator import NetworkImmuneCorrelator, ImmuneIncident


class TestLearnedAttackRecognizer:

    def test_fit_no_error(self):
        X = generate_clean_episodes(n_steps=200, seed=0)
        rec = LearnedAttackRecognizer()
        rec.fit(X, epochs=5)
        assert rec._fitted
        assert rec.recon_threshold_ is not None

    def test_learn_attack_grows_gallery(self):
        X = generate_clean_episodes(n_steps=200, seed=2)
        rec = LearnedAttackRecognizer()
        rec.fit(X, epochs=5)
        assert rec.gallery_size == 0

        obs_atk, labels, _ = generate_attack_episode(stealth=0.0, n_steps=30, attack_start=5, seed=3)
        attack_obs = obs_atk[labels]
        if len(attack_obs) > 0:
            rec.learn_attack(attack_obs, "lateral_move", ["User0", "Enterprise0"])
        assert rec.gallery_size == 1

    def test_recognize_returns_valid_tuple(self):
        X = generate_clean_episodes(n_steps=200, seed=4)
        rec = LearnedAttackRecognizer()
        rec.fit(X, epochs=5)

        obs_atk, labels, _ = generate_attack_episode(stealth=0.0, n_steps=30, attack_start=5, seed=5)
        attack_obs = obs_atk[labels]
        if len(attack_obs) == 0:
            pytest.skip("No attack obs")
        rec.learn_attack(attack_obs, "obvious", [])
        conf, atype = rec.recognize(attack_obs)
        assert 0.0 <= conf <= 1.0
        assert isinstance(atype, str)

    def test_reconstruction_error_is_float(self):
        X = generate_clean_episodes(n_steps=200, seed=6)
        rec = LearnedAttackRecognizer()
        rec.fit(X, epochs=5)
        err = rec.reconstruction_error(X[0])
        assert isinstance(err, float)
        assert err >= 0.0


class TestNetworkImmuneCorrelator:

    def test_update_step_returns_list(self):
        corr = NetworkImmuneCorrelator()
        obs  = generate_clean_episodes(n_steps=1, seed=0)[0]
        from soma.envs.cyborg_wrapper import HOST_NAMES
        mem_scores = {h: 0.0 for h in HOST_NAMES}
        incidents = corr.update_step(
            obs=obs,
            innate_score=0.1,
            innate_threshold=0.5,
            memory_scores=mem_scores,
            memory_threshold=1.0,
            tolerance_suppressed=set(),
            tolerance_breached=set(),
        )
        assert isinstance(incidents, list)

    def test_high_innate_score_creates_incident(self):
        corr = NetworkImmuneCorrelator(min_score=0.1)
        obs  = generate_clean_episodes(n_steps=1, seed=0)[0]
        from soma.envs.cyborg_wrapper import HOST_NAMES
        host_scores = {h: 5.0 for h in HOST_NAMES}
        mem_scores  = {h: 0.0 for h in HOST_NAMES}
        incidents = corr.update_step(
            obs=obs,
            innate_score=5.0,
            innate_threshold=0.5,
            memory_scores=mem_scores,
            memory_threshold=1.0,
            tolerance_suppressed=set(),
            tolerance_breached=set(),
            innate_host_scores=host_scores,
        )
        assert len(incidents) > 0

    def test_reset_clears_state(self):
        corr = NetworkImmuneCorrelator()
        corr._acc["User0"] = 5.0
        corr._step = 10
        corr.reset()
        assert len(corr._acc) == 0
        assert corr._step == 0

    def test_incident_confidence_levels(self):
        inc_high = ImmuneIncident(host="User0", score=4.5, step=1, layers_fired=["innate", "memory"])
        inc_med  = ImmuneIncident(host="User0", score=2.5, step=1, layers_fired=["innate"])
        inc_low  = ImmuneIncident(host="User0", score=0.5, step=1, layers_fired=[])
        assert inc_high.confidence == "HIGH"
        assert inc_med.confidence  == "MEDIUM"
        assert inc_low.confidence  == "LOW"
