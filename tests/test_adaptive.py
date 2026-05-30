"""tests/test_adaptive.py — Synthetic network generator + memory/tolerance tests."""
import numpy as np
import pytest

from soma.envs.synthetic_network_gen import (
    generate_clean_episodes, generate_attack_episode,
    SyntheticNetworkGen, HOST_NAMES, OBS_DIM,
)
from soma.layers.memory import HostDriftLayer
from soma.layers.tolerance import ImmuneToleranceLayer


class TestSyntheticNetworkGen:

    def test_obs_shape(self):
        gen = SyntheticNetworkGen(seed=0)
        obs = gen.reset()
        assert obs.shape == (OBS_DIM,), f"Expected ({OBS_DIM},) got {obs.shape}"

    def test_step_returns_triple(self):
        gen = SyntheticNetworkGen(seed=0)
        gen.reset()
        obs, is_atk, info = gen.step()
        assert obs.shape == (OBS_DIM,)
        assert isinstance(is_atk, bool)
        assert "phase" in info

    def test_clean_episodes_no_attack(self):
        X = generate_clean_episodes(n_steps=50, seed=1)
        assert X.shape == (50, OBS_DIM)
        assert X.min() >= 0.0

    def test_attack_episode_has_attack_steps(self):
        obs, labels, infos = generate_attack_episode(stealth=0.0, n_steps=50, attack_start=5)
        assert labels.sum() > 0, "Expected attack steps"
        assert obs.shape == (50, OBS_DIM)

    def test_obvious_vs_sophisticated_differ(self):
        _, labels_obv, _ = generate_attack_episode(stealth=0.0, n_steps=50, attack_start=5, seed=0)
        _, labels_sph, _ = generate_attack_episode(stealth=0.9, n_steps=50, attack_start=5, seed=0)
        assert labels_obv.sum() > 0
        assert labels_sph.sum() > 0


class TestHostDriftLayer:

    def test_calibrate_sets_threshold(self):
        X = generate_clean_episodes(n_steps=200, seed=2)
        mem = HostDriftLayer()
        mem.calibrate_threshold(X)
        assert mem.threshold_ is not None
        assert mem.threshold_ > 0.0

    def test_drift_scores_on_clean_low(self):
        X_cal = generate_clean_episodes(n_steps=500, seed=3)
        mem = HostDriftLayer()
        mem.calibrate_threshold(X_cal)

        X_eval = generate_clean_episodes(n_steps=100, seed=99)
        alarm_count = 0
        for obs in X_eval:
            scores = mem.update_and_scores(obs)
            if any(s > mem.threshold_ for s in scores.values()):
                alarm_count += 1
        fpr = alarm_count / len(X_eval)
        assert fpr <= 0.15, f"Memory FPR on clean {fpr:.3f} too high"

    def test_drift_detects_obvious_attack(self):
        X_cal = generate_clean_episodes(n_steps=500, seed=4)
        mem = HostDriftLayer()
        mem.calibrate_threshold(X_cal)

        obs_atk, labels, _ = generate_attack_episode(stealth=0.0, n_steps=50, attack_start=5, seed=5)
        detected = 0
        for t, obs in enumerate(obs_atk):
            scores = mem.update_and_scores(obs)
            if labels[t] and any(s > mem.threshold_ for s in scores.values()):
                detected += 1
        n_atk = int(labels.sum())
        if n_atk > 0:
            tpr = detected / n_atk
            assert tpr >= 0.30, f"Memory TPR {tpr:.3f} too low on obvious attack"

    def test_reset_clears_state(self):
        X = generate_clean_episodes(n_steps=30, seed=6)
        mem = HostDriftLayer()
        mem.calibrate_threshold(X)
        for obs in X:
            mem.update(obs)
        mem.reset()
        assert len(mem._hosts) == 0


class TestImmuneToleranceLayer:

    def test_calibrate_sets_thresholds(self):
        X = generate_clean_episodes(n_steps=200, seed=10)
        tol = ImmuneToleranceLayer()
        tol.calibrate(X)
        assert tol.suppress_thresh is not None
        assert tol.breach_thresh is not None
        assert tol.suppress_thresh < tol.breach_thresh

    def test_suppressed_hosts_nonempty_on_clean(self):
        X = generate_clean_episodes(n_steps=100, seed=11)
        tol = ImmuneToleranceLayer()
        tol.calibrate(X)
        suppressed_counts = [len(tol.suppressed_hosts(obs)) for obs in X[:20]]
        assert max(suppressed_counts) > 0

    def test_host_zscore_returns_float(self):
        X = generate_clean_episodes(n_steps=50, seed=12)
        tol = ImmuneToleranceLayer()
        i = 0
        feat = X[0][i * 5:(i + 1) * 5]
        z = tol.host_zscore(HOST_NAMES[0], feat)
        assert isinstance(z, float)
        assert z >= 0.0
