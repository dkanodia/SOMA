"""tests/test_innate.py — Layer 1 (Innate) smoke tests. No CybORG dependency."""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from soma.envs.synthetic_network_gen import generate_clean_episodes, generate_attack_episode
from soma.layers.innate import InnateImmunityLayer


def _clean(n: int = 300) -> np.ndarray:
    return generate_clean_episodes(n_steps=n, seed=7)


class TestInnateImmunityLayer:

    def test_fit_calibrate_no_error(self):
        X = _clean(300)
        layer = InnateImmunityLayer()
        layer.fit(X[:200])
        layer.calibrate_threshold(X[200:])
        assert layer.threshold_ is not None

    def test_fpr_on_clean_data(self):
        X_tr  = _clean(500)
        X_val = generate_clean_episodes(n_steps=200, seed=99)
        layer = InnateImmunityLayer(fpr_target=0.01)
        layer.fit(X_tr)
        layer.calibrate_threshold(X_val)
        flags = np.array([layer.is_anomalous(x) for x in X_val])
        assert flags.mean() <= 0.025, f"FPR {flags.mean():.4f} too high"

    def test_anomaly_score_returns_float(self):
        X = _clean(200)
        layer = InnateImmunityLayer()
        layer.fit(X)
        score = layer.anomaly_score(X[0])
        assert isinstance(score, float)

    def test_obvious_attack_detected(self):
        X_clean = _clean(500)
        layer = InnateImmunityLayer(fpr_target=0.01)
        layer.fit(X_clean)
        layer.calibrate_threshold(generate_clean_episodes(200, seed=77))

        obs_attack, labels, _ = generate_attack_episode(stealth=0.0, n_steps=50, attack_start=10)
        attack_obs  = obs_attack[labels]
        if len(attack_obs) == 0:
            pytest.skip("No attack steps in episode")
        scores  = layer.anomaly_scores_batch(attack_obs)
        tpr     = float((scores > layer.threshold_).mean())
        assert tpr >= 0.50, f"Obvious attack TPR {tpr:.3f} too low"

    def test_per_host_scores_returns_all_hosts(self):
        from soma.envs.cyborg_wrapper import HOST_NAMES
        X = _clean(200)
        layer = InnateImmunityLayer()
        layer.fit(X)
        result = layer.per_host_scores(X[0])
        assert set(result.keys()) == set(HOST_NAMES)

    def test_save_load_roundtrip(self):
        X = _clean(300)
        layer = InnateImmunityLayer()
        layer.fit(X[:200])
        layer.calibrate_threshold(X[200:])

        x_probe = X[0]
        orig_score = layer.anomaly_score(x_probe)
        orig_thresh = layer.threshold_

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "innate.joblib"
            layer.save(path)
            layer2 = InnateImmunityLayer.load(path)

        assert abs(layer2.threshold_ - orig_thresh) < 1e-9
        assert abs(layer2.anomaly_score(x_probe) - orig_score) < 1e-6
