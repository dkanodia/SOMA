"""
soma/layers/innate.py
======================
Layer 1 — Innate Immunity: per-step anomaly detection.

Primary model:  Isolation Forest (sklearn)
Benchmark:      Variational Autoencoder (PyTorch)
Decision rule:  whichever achieves higher TPR at fixed 1% FPR on held-out
                clean CAGE 2 episodes. State the benchmark result in the pitch.

FPR budget: 1%
  At 10-second monitoring intervals on 5 hosts: ~72 false alarms/host/day.
  Calibrated on clean validation episodes (see soma/eval/fpr_calibration.py).

Known limitation (VAE):
  Reconstruction error is not a reliable anomaly score due to the typicality
  gap — OOD inputs can produce low reconstruction error when they project near
  high-density regions of the learned decoder manifold.
  Reference: Nalisnick et al., ICLR 2019.

Dual-timescale baseline:
  High-pass filter on the anomaly score stream. Two manually set parameters
  (fast_alpha, slow_alpha) with no principled basis. Stated as such.
"""

import numpy as np
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Isolation Forest (primary)
# ---------------------------------------------------------------------------

class InnateIsolationForest:
    """
    Isolation Forest anomaly detector.
    Trained on clean (no red agent) CAGE 2 episode data.

    Parameters
    ----------
    n_estimators : int
        Number of trees. 100 is typically sufficient for 25-dim input.
    contamination : float
        Expected fraction of anomalies in training data. Set to 0.0 for
        clean-only training data (equivalent to setting threshold manually).
    fpr_target : float
        Target false positive rate. Threshold calibrated on validation set.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        contamination: float = 0.01,
        fpr_target: float = 0.01,
    ):
        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=42,
        )
        self.fpr_target = fpr_target
        self.threshold_: Optional[float] = None   # set during calibration

    def fit(self, X_clean: np.ndarray) -> "InnateIsolationForest":
        """Train on clean episode data."""
        self.model.fit(X_clean)
        return self

    def calibrate_threshold(self, X_val_clean: np.ndarray) -> float:
        """
        Set decision threshold so FPR on clean validation data = fpr_target.
        Threshold = (fpr_target)-th percentile of anomaly scores on clean val.
        More negative score = more anomalous in IsolationForest.
        """
        scores = self.model.score_samples(X_val_clean)
        self.threshold_ = float(np.percentile(scores, self.fpr_target * 100))
        return self.threshold_

    def anomaly_score(self, x: np.ndarray) -> float:
        """Raw anomaly score (more negative = more anomalous)."""
        return float(self.model.score_samples(x.reshape(1, -1))[0])

    def is_anomalous(self, x: np.ndarray) -> bool:
        """True if anomaly score is below calibrated threshold."""
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() before is_anomalous().")
        return self.anomaly_score(x) < self.threshold_

    def save(self, path: Path) -> None:
        joblib.dump({"model": self.model, "threshold": self.threshold_}, path)

    @classmethod
    def load(cls, path: Path) -> "InnateIsolationForest":
        obj = cls()
        d = joblib.load(path)
        obj.model      = d["model"]
        obj.threshold_ = d["threshold"]
        return obj


# ---------------------------------------------------------------------------
# VAE (benchmark — used for comparison only)
# ---------------------------------------------------------------------------

class _Encoder(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int):
        super().__init__()
        self.net    = nn.Sequential(nn.Linear(input_dim, 64), nn.ReLU(),
                                    nn.Linear(64, 32),         nn.ReLU())
        self.mu     = nn.Linear(32, latent_dim)
        self.logvar = nn.Linear(32, latent_dim)

    def forward(self, x):
        h = self.net(x)
        return self.mu(h), self.logvar(h)


class _Decoder(nn.Module):
    def __init__(self, latent_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(latent_dim, 32), nn.ReLU(),
                                 nn.Linear(32, 64),          nn.ReLU(),
                                 nn.Linear(64, output_dim))

    def forward(self, z):
        return self.net(z)


class InnateVAE(nn.Module):
    """
    Variational Autoencoder anomaly detector — BENCHMARK ONLY.

    Known failure mode: typicality gap (Nalisnick et al. ICLR 2019).
    Reconstruction error is not guaranteed to be a monotone anomaly score.
    Use only if it outperforms IsolationForest at the fixed 1% FPR budget.
    """

    def __init__(self, input_dim: int = 25, latent_dim: int = 8):
        super().__init__()
        self.encoder    = _Encoder(input_dim, latent_dim)
        self.decoder    = _Decoder(latent_dim, input_dim)
        self.threshold_: Optional[float] = None

    def forward(self, x: torch.Tensor):
        mu, logvar = self.encoder(x)
        std = torch.exp(0.5 * logvar)
        z   = mu + std * torch.randn_like(std)
        return self.decoder(z), mu, logvar

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        recon, _, _ = self.forward(x)
        return F.mse_loss(recon, x, reduction="none").mean(dim=-1)

    def calibrate_threshold(self, X_val_clean: np.ndarray, fpr_target: float = 0.01) -> float:
        """Calibrate on clean validation data. threshold = (1-fpr)-th percentile."""
        self.eval()
        with torch.no_grad():
            x   = torch.tensor(X_val_clean, dtype=torch.float32)
            err = self.reconstruction_error(x).numpy()
        self.threshold_ = float(np.percentile(err, (1.0 - fpr_target) * 100))
        return self.threshold_

    def is_anomalous(self, x: np.ndarray) -> bool:
        if self.threshold_ is None:
            raise RuntimeError("Call calibrate_threshold() before is_anomalous().")
        self.eval()
        with torch.no_grad():
            t   = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
            err = self.reconstruction_error(t).item()
        return err > self.threshold_


# ---------------------------------------------------------------------------
# Dual-timescale baseline (high-pass filter)
# ---------------------------------------------------------------------------

class DualTimescaleBaseline:
    """
    Exponential moving average anomaly flag.

    Fires when the fast EMA of anomaly scores exceeds the slow EMA by
    sigma standard deviations. This is a high-pass filter — stated as such.
    Parameters fast_alpha and slow_alpha are manually chosen with no
    principled derivation.

    Parameters
    ----------
    fast_alpha : float   Short-timescale EMA weight.
    slow_alpha : float   Long-timescale EMA weight (reference distribution).
    sigma : float        Number of slow-std deviations to trigger alarm.
    """

    def __init__(
        self,
        fast_alpha: float = 0.1,
        slow_alpha: float = 0.001,
        sigma: float      = 2.5,
    ):
        self.fa = fast_alpha
        self.sa = slow_alpha
        self.sigma = sigma
        self._fast = self._slow = self._slow_var = None

    def update_and_flag(self, score: float) -> bool:
        if self._slow is None:
            self._fast = self._slow = score
            self._slow_var = 0.0
            return False
        self._fast     = (1 - self.fa) * self._fast + self.fa * score
        self._slow     = (1 - self.sa) * self._slow + self.sa * score
        self._slow_var = (1 - self.sa) * self._slow_var + self.sa * (score - self._slow) ** 2
        slow_std = max(self._slow_var ** 0.5, 1e-6)
        return self._fast > self._slow + self.sigma * slow_std
