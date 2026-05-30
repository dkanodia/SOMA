"""tests/test_innate.py — Layer 1 smoke tests. No CybORG dependency."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch

from soma.layers.innate import DualTimescaleBaseline, InnateIsolationForest, InnateVAE
from scripts.train_innate import train_vae


def _clean(n=500):
    return np.random.randn(n, 25).astype(np.float32)


class TestInnateLayer:

    def test_isolation_forest_fits_without_error(self):
        iso = InnateIsolationForest()
        iso.fit(_clean(500))
        iso.calibrate_threshold(_clean(100))
        assert iso.threshold_ is not None

    def test_isolation_forest_threshold_gives_target_fpr(self):
        rng = np.random.default_rng(0)
        X_tr  = rng.standard_normal((1000, 25)).astype(np.float32)
        X_val = rng.standard_normal((500,  25)).astype(np.float32)
        X_te  = rng.standard_normal((500,  25)).astype(np.float32)

        iso = InnateIsolationForest(fpr_target=0.01)
        iso.fit(X_tr)
        iso.calibrate_threshold(X_val)

        flags = np.array([iso.is_anomalous(x) for x in X_te])
        measured_fpr = flags.mean()
        assert measured_fpr <= 0.015, f"FPR {measured_fpr:.4f} exceeds tolerance"

    def test_vae_trains_without_error(self):
        vae = InnateVAE()
        train_vae(vae, _clean(200), epochs=2)
        assert True  # no exception raised

    def test_vae_calibrate_threshold(self):
        rng = np.random.default_rng(1)
        X_tr  = rng.standard_normal((500, 25)).astype(np.float32)
        X_val = rng.standard_normal((500, 25)).astype(np.float32)
        X_te  = rng.standard_normal((500, 25)).astype(np.float32)

        vae = InnateVAE()
        train_vae(vae, X_tr, epochs=5)
        vae.calibrate_threshold(X_val, fpr_target=0.01)
        assert vae.threshold_ is not None

        flags = np.array([vae.is_anomalous(x) for x in X_te])
        measured_fpr = flags.mean()
        assert measured_fpr <= 0.015, f"VAE FPR {measured_fpr:.4f} exceeds tolerance"

    def test_dual_timescale_does_not_alarm_on_flat_signal(self):
        dtb = DualTimescaleBaseline()
        fired = False
        for _ in range(200):
            fired = dtb.update_and_flag(1.0)
        assert not fired

    def test_isolation_forest_save_load_roundtrip(self):
        X = _clean(300)
        iso = InnateIsolationForest()
        iso.fit(X[:200])
        iso.calibrate_threshold(X[200:250])

        x_probe = X[250]
        original_score     = iso.anomaly_score(x_probe)
        original_threshold = iso.threshold_
        original_flag      = iso.is_anomalous(x_probe)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iso.joblib"
            iso.save(path)
            iso2 = InnateIsolationForest.load(path)

        assert abs(iso2.threshold_ - original_threshold) < 1e-9
        assert abs(iso2.anomaly_score(x_probe) - original_score) < 1e-6
        assert iso2.is_anomalous(x_probe) == original_flag
