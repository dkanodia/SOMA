"""
tests/test_fpr_calibration.py
------------------------------
Tests that FPR calibration produces thresholds meeting budget targets.
"""
import numpy as np
import pytest

from soma.eval.fpr_calibration import calibrate_layer1, validate_all_fpr


class TestFPRCalibration:
    def test_layer1_fpr_within_budget(self):
        """Calibrated threshold should yield FPR <= 1% on clean val data."""
        rng   = np.random.default_rng(42)
        X_val = rng.standard_normal((1000, 25))
        thresh = calibrate_layer1(lambda x: float(np.linalg.norm(x)), X_val)
        scores = np.array([float(np.linalg.norm(x)) for x in X_val])
        measured_fpr = float(np.mean(scores > thresh))
        assert measured_fpr <= 0.01 + 0.005

    def test_validate_all_passes_when_under_budget(self):
        results = {"layer1_fpr": 0.009, "layer2_fpr": 0.008, "layer4_fpr": 0.0005}
        assert validate_all_fpr(results) is True

    def test_validate_all_fails_when_over_budget(self):
        results = {"layer1_fpr": 0.05, "layer2_fpr": 0.01, "layer4_fpr": 0.001}
        assert validate_all_fpr(results) is False
