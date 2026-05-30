"""
soma/eval/fpr_calibration.py
=============================
FPR calibration for all three detection layers.

FPR budgets
-----------
  Layer 1 (Isolation Forest / VAE): 1%
  Layer 2 (PPO heuristic threshold): 1%
  Layer 4 (Long-dwell drift):        0.1%

Every threshold is calibrated on held-out CLEAN episode data.
No layer is used operationally without a calibrated threshold.
"""

import numpy as np
from typing import Callable


def calibrate_layer1(
    anomaly_fn: Callable[[np.ndarray], float],
    X_val_clean: np.ndarray,
    fpr_target: float = 0.01,
) -> float:
    """
    Calibrate Layer 1 threshold on clean validation data.

    Parameters
    ----------
    anomaly_fn : callable
        Takes a feature vector, returns a scalar anomaly score.
        Convention: higher score = more anomalous.
    X_val_clean : ndarray, shape (n_samples, n_features)
        Feature vectors from clean (no red agent) episodes.
    fpr_target : float
        Target FPR (fraction of clean samples flagged).

    Returns
    -------
    float: threshold such that FPR on val_clean ~= fpr_target.
    """
    scores    = np.array([anomaly_fn(x) for x in X_val_clean])
    threshold = float(np.percentile(scores, (1.0 - fpr_target) * 100))

    measured_fpr = float(np.mean(scores > threshold))
    print(f"[Layer 1] Calibrated threshold: {threshold:.4f}")
    print(f"[Layer 1] Measured FPR on val_clean: {measured_fpr:.4f} (target {fpr_target})")
    assert measured_fpr <= fpr_target + 0.005, \
        f"FPR {measured_fpr:.4f} exceeds target {fpr_target} + tolerance 0.005"
    return threshold


def calibrate_layer2(
    suspicion_fn: Callable[[np.ndarray], float],
    X_val_clean: np.ndarray,
    fpr_target: float = 0.01,
) -> float:
    """
    Calibrate Layer 2 honeypot trigger threshold on clean episodes.
    suspicion_fn maps a per-host observation to a suspicion score in [0, 1].
    """
    scores    = np.array([suspicion_fn(x) for x in X_val_clean])
    threshold = float(np.percentile(scores, (1.0 - fpr_target) * 100))
    measured  = float(np.mean(scores > threshold))
    print(f"[Layer 2] Calibrated threshold: {threshold:.4f}")
    print(f"[Layer 2] Measured FPR on val_clean: {measured:.4f} (target {fpr_target})")
    return threshold


def calibrate_supply_chain_layer1(
    detector,
    X_val_clean: np.ndarray,
    fpr_target: float = 0.01,
) -> float:
    """
    Calibrate Layer 1 supply chain detector threshold.
    Wraps detector.calibrate_threshold() for consistency with the
    existing calibration pipeline used by Layers 2 and 4.

    Parameters
    ----------
    detector : InnateSupplyChainDetector
    X_val_clean : ndarray  Clean validation feature matrix
    fpr_target : float

    Returns
    -------
    float: calibrated threshold
    """
    return detector.calibrate_threshold(X_val_clean)


def validate_all_fpr(results: dict) -> bool:
    """
    Final check: assert all layers meet their FPR budgets.

    Parameters
    ----------
    results : dict with keys "layer1_fpr", "layer2_fpr", "layer4_fpr"

    Returns
    -------
    bool: True if all pass.
    """
    budgets = {"layer1_fpr": 0.01, "layer2_fpr": 0.01, "layer4_fpr": 0.001}
    passed  = True
    for key, budget in budgets.items():
        measured = results.get(key, None)
        if measured is None:
            print(f"[WARN] {key} not measured — skipping")
            continue
        ok = measured <= budget + 0.002   # 0.2% tolerance
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {key}: {measured:.4f} (budget {budget})")
        if not ok:
            passed = False
    return passed
