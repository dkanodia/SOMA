"""tests/test_innate.py — Layer 1 (Innate) unit tests. No CybORG dependency."""
import tempfile
from pathlib import Path

import numpy as np
import pytest

from soma.layers.innate import InnateImmunityLayer
from soma.envs.cyborg_wrapper import N_HOSTS, FEATURES_PER_HOST, HOST_NAMES

OBS_DIM = N_HOSTS * FEATURES_PER_HOST


# ---------------------------------------------------------------------------
# Synthetic data helpers (no CybORG required)
# ---------------------------------------------------------------------------

def _clean(n: int = 300, seed: int = 7) -> np.ndarray:
    """Synthetic clean observations: low activity, no compromise."""
    rng = np.random.default_rng(seed)
    X = np.zeros((n, OBS_DIM), dtype=np.float32)
    X[:, 0::5] = rng.uniform(0.0, 0.1, (n, N_HOSTS))   # activity: low
    X[:, 1::5] = 0.0                                     # compromised: 0
    X[:, 2::5] = rng.integers(0, 3, (n, N_HOSTS)).astype(np.float32)  # sessions
    X[:, 3::5] = rng.integers(0, 5, (n, N_HOSTS)).astype(np.float32)  # processes
    X[:, 4::5] = rng.uniform(0.0, 1.0, (n, N_HOSTS))   # network_pos
    return X


def _anomalous(n: int = 50, seed: int = 42) -> np.ndarray:
    """Synthetic attack observations: high activity, compromised flags set."""
    rng = np.random.default_rng(seed)
    X = np.ones((n, OBS_DIM), dtype=np.float32)         # spike everything
    X[:, 0::5] = rng.uniform(0.7, 1.0, (n, N_HOSTS))   # activity: high
    X[:, 1::5] = 1.0                                     # compromised: 1
    X[:, 2::5] = rng.integers(5, 10, (n, N_HOSTS)).astype(np.float32)
    X[:, 3::5] = rng.integers(10, 20, (n, N_HOSTS)).astype(np.float32)
    return X


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInnateImmunityLayer:

    def test_fit_calibrate_no_error(self):
        X = _clean(300)
        layer = InnateImmunityLayer()
        layer.fit(X[:200])
        layer.calibrate_threshold(X[200:])
        assert layer.threshold_ is not None

    def test_fpr_on_clean_data(self):
        X_tr  = _clean(500)
        X_val = _clean(200, seed=99)
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
        X_val   = _clean(200, seed=77)
        layer   = InnateImmunityLayer(fpr_target=0.01)
        layer.fit(X_clean)
        layer.calibrate_threshold(X_val)

        X_atk  = _anomalous(50)
        scores = layer.anomaly_scores_batch(X_atk)
        tpr    = float((scores > layer.threshold_).mean())
        assert tpr >= 0.50, f"Obvious attack TPR {tpr:.3f} too low"

    def test_anomalous_higher_than_clean(self):
        X_clean = _clean(200)
        layer   = InnateImmunityLayer()
        layer.fit(X_clean)

        clean_score = layer.anomaly_score(X_clean[0])
        anom_obs    = _anomalous(1)[0]
        anom_score  = layer.anomaly_score(anom_obs)
        assert anom_score > clean_score, (
            f"Anomaly score {anom_score:.4f} not higher than clean {clean_score:.4f}"
        )

    def test_per_host_scores_returns_all_hosts(self):
        X = _clean(200)
        layer = InnateImmunityLayer()
        layer.fit(X)
        result = layer.per_host_scores(X[0])
        assert set(result.keys()) == set(HOST_NAMES)
        assert all(isinstance(v, float) for v in result.values())

    def test_save_load_roundtrip(self):
        X = _clean(300)
        layer = InnateImmunityLayer()
        layer.fit(X[:200])
        layer.calibrate_threshold(X[200:])

        x_probe     = X[0]
        orig_score  = layer.anomaly_score(x_probe)
        orig_thresh = layer.threshold_

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "innate.joblib"
            layer.save(path)
            layer2 = InnateImmunityLayer.load(path)

        assert abs(layer2.threshold_ - orig_thresh) < 1e-9
        assert abs(layer2.anomaly_score(x_probe) - orig_score) < 1e-6

    def test_uncalibrated_raises(self):
        X = _clean(100)
        layer = InnateImmunityLayer()
        layer.fit(X)
        with pytest.raises(RuntimeError):
            layer.is_anomalous(X[0])
