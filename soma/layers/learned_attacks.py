"""
soma/layers/learned_attacks.py
================================
Layer 5 — Learned Attack Recognition: system learns from its own catches.

Biological framing:
  After the innate or memory layer catches an infection, the adaptive
  immune system studies that pathogen and creates specific antibodies.
  These antibodies let the system recognize future infections of the
  SAME type immediately — without needing an external registry.

  SOMA does the same: each caught attack is embedded into a latent
  space (via VAE) and stored in an attack gallery. Future anomalies are
  compared against the gallery — high cosine similarity → known attack.

Mechanism:
  1. VAE trained on clean network data (learns to encode "self")
  2. Anomalous observations reconstruct POORLY → high reconstruction error
  3. Caught attack → encode its observation sequence → store embedding
  4. New anomaly → encode → compare to gallery → max cosine similarity

VAE architecture:
  Encoder: 30 → 16 → 8 → LATENT_DIM (default 4)
  Decoder: LATENT_DIM → 8 → 16 → 30
  Loss: reconstruction MSE + KL divergence (β-VAE with β=0.5)

Gallery:
  list of {embedding: np.ndarray, attack_type: str, confidence: float}
  Grows as the system catches new attacks (no maximum size for demo).
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


OBS_DIM    = 30    # 6 hosts × 5 features (matches cyborg_wrapper)
LATENT_DIM = 4     # small = interpretable + visualizable


# ---------------------------------------------------------------------------
# VAE architecture
# ---------------------------------------------------------------------------

class _Encoder(nn.Module):
    def __init__(self, obs_dim: int = OBS_DIM, latent_dim: int = LATENT_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 16), nn.ReLU(),
            nn.Linear(16, 8),       nn.ReLU(),
        )
        self.mu_head  = nn.Linear(8, latent_dim)
        self.log_var_head = nn.Linear(8, latent_dim)

    def forward(self, x):
        h       = self.net(x)
        mu      = self.mu_head(h)
        log_var = self.log_var_head(h)
        return mu, log_var


class _Decoder(nn.Module):
    def __init__(self, latent_dim: int = LATENT_DIM, obs_dim: int = OBS_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, 8), nn.ReLU(),
            nn.Linear(8, 16),          nn.ReLU(),
            nn.Linear(16, obs_dim),    nn.Sigmoid(),
        )

    def forward(self, z):
        return self.net(z)


class _VAE(nn.Module):
    def __init__(self, obs_dim: int = OBS_DIM, latent_dim: int = LATENT_DIM):
        super().__init__()
        self.encoder = _Encoder(obs_dim, latent_dim)
        self.decoder = _Decoder(latent_dim, obs_dim)

    def reparameterize(self, mu, log_var):
        std = torch.exp(0.5 * log_var)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward(self, x):
        mu, log_var = self.encoder(x)
        z           = self.reparameterize(mu, log_var)
        recon       = self.decoder(z)
        return recon, mu, log_var

    def encode(self, x) -> np.ndarray:
        """Return mean embedding (no sampling)."""
        with torch.no_grad():
            mu, _ = self.encoder(x)
        return mu.cpu().numpy()


# ---------------------------------------------------------------------------
# Gallery entry
# ---------------------------------------------------------------------------

@dataclass
class AttackEmbedding:
    embedding:   np.ndarray   # shape (LATENT_DIM,)
    attack_type: str
    host_sequence: list[str]  # hosts visited during attack
    n_steps:     int
    confidence:  float = 1.0


# ---------------------------------------------------------------------------
# Public layer
# ---------------------------------------------------------------------------

class LearnedAttackRecognizer:
    """
    VAE-based attack signature learner and recognizer.

    The system learns what "self" looks like (clean network traffic).
    When it catches an attack, it stores its embedding. Future attacks
    are recognized by similarity to stored embeddings.

    Usage:
        rec = LearnedAttackRecognizer()
        rec.fit(X_clean)                           # train VAE on clean data
        rec.learn_attack(obs_seq, "lateral_move", ["User0", "Enterprise0"])
        conf, atype = rec.recognize(obs_seq)       # match against gallery
    """

    def __init__(
        self,
        obs_dim:    int   = OBS_DIM,
        latent_dim: int   = LATENT_DIM,
        beta:       float = 0.5,         # KL weight in β-VAE
        lr:         float = 1e-3,
        device:     str   = "cpu",
    ):
        self.obs_dim    = obs_dim
        self.latent_dim = latent_dim
        self.beta       = beta
        self.lr         = lr
        self.device     = torch.device(device)

        self._vae:     Optional[_VAE] = None
        self._gallery: list[AttackEmbedding] = []
        self._fitted   = False

        # Reconstruction error threshold (calibrated on clean data)
        self.recon_threshold_: Optional[float] = None

    # ------------------------------------------------------------------
    def fit(
        self,
        X_clean: np.ndarray,
        epochs:  int   = 50,
        batch:   int   = 64,
        verbose: bool  = False,
    ) -> "LearnedAttackRecognizer":
        """
        Train VAE on clean observations.
        X_clean: shape (n, 30).
        """
        # Normalize to [0, 1] (sigmoid output matches this range)
        self._X_min  = X_clean.min(axis=0)
        self._X_range = np.maximum(X_clean.max(axis=0) - self._X_min, 1e-6)

        X_norm = (X_clean - self._X_min) / self._X_range
        X_t    = torch.tensor(X_norm, dtype=torch.float32, device=self.device)

        self._vae = _VAE(self.obs_dim, self.latent_dim).to(self.device)
        opt       = optim.Adam(self._vae.parameters(), lr=self.lr)

        self._vae.train()
        n = len(X_t)
        for epoch in range(epochs):
            perm    = torch.randperm(n)
            ep_loss = 0.0
            for i in range(0, n, batch):
                idx  = perm[i:i + batch]
                xb   = X_t[idx]
                recon, mu, log_var = self._vae(xb)
                recon_loss = nn.functional.mse_loss(recon, xb)
                kl_loss    = -0.5 * torch.mean(1 + log_var - mu.pow(2) - log_var.exp())
                loss       = recon_loss + self.beta * kl_loss
                opt.zero_grad()
                loss.backward()
                opt.step()
                ep_loss += loss.item()
            if verbose and (epoch + 1) % 10 == 0:
                print(f"  [VAE] epoch {epoch+1}/{epochs}  loss={ep_loss:.4f}")

        self._vae.eval()
        self._fitted = True

        # Calibrate reconstruction error threshold on clean data
        errors = self._recon_errors(X_norm)
        self.recon_threshold_ = float(np.percentile(errors, 95))
        print(f"[LearnedAttacks] VAE trained on {n} clean obs  "
              f"recon_threshold={self.recon_threshold_:.4f}")
        return self

    # ------------------------------------------------------------------
    def learn_attack(
        self,
        obs_sequence:  np.ndarray,   # shape (T, 30)
        attack_type:   str,
        host_sequence: Optional[list[str]] = None,
    ) -> AttackEmbedding:
        """
        Store the embedding of a caught attack in the gallery.
        obs_sequence: steps during which the attack occurred.
        """
        if not self._fitted:
            raise RuntimeError("Call fit() before learn_attack().")

        emb = self._embed_sequence(obs_sequence)
        entry = AttackEmbedding(
            embedding    = emb,
            attack_type  = attack_type,
            host_sequence= host_sequence or [],
            n_steps      = len(obs_sequence),
            confidence   = 1.0,
        )
        self._gallery.append(entry)
        print(f"[LearnedAttacks] Learned '{attack_type}' — gallery size={len(self._gallery)}")
        return entry

    def recognize(
        self,
        obs_sequence: np.ndarray,   # shape (T, 30)
        top_k: int = 1,
    ) -> tuple[float, str]:
        """
        Compare obs_sequence against the learned gallery.
        Returns (max_similarity, attack_type) of the best match.
        If gallery is empty: returns (recon_error_normalized, "unknown").
        """
        if not self._fitted:
            raise RuntimeError("Call fit() before recognize().")

        emb = self._embed_sequence(obs_sequence)

        # Reconstruction error as base signal (even without gallery)
        norm_obs = self._normalize(obs_sequence)
        recon_err = float(np.mean(self._recon_errors(norm_obs)))
        norm_err  = min(recon_err / max(self.recon_threshold_ or 1.0, 1e-6), 1.0)

        if not self._gallery:
            return norm_err, "unknown"

        # Cosine similarity to each gallery entry
        sims = []
        for entry in self._gallery:
            sim = float(self._cosine_sim(emb, entry.embedding))
            sims.append((sim, entry.attack_type))

        sims.sort(key=lambda x: -x[0])
        best_sim, best_type = sims[0]

        # Blend: gallery similarity + reconstruction error signal
        sim_val  = best_sim if np.isfinite(best_sim) else 0.0
        combined = 0.6 * max(sim_val, 0.0) + 0.4 * norm_err
        return float(np.clip(combined, 0.0, 1.0)), best_type

    def reconstruction_error(self, obs: np.ndarray) -> float:
        """Single-observation reconstruction error (higher = more attack-like)."""
        if not self._fitted:
            return 0.0
        norm = self._normalize(obs.reshape(1, -1))
        err  = self._recon_errors(norm)
        return float(err[0])

    def is_known_attack(self, obs_sequence: np.ndarray, threshold: float = 0.5) -> bool:
        """True if obs_sequence resembles a previously caught attack."""
        conf, _ = self.recognize(obs_sequence)
        return conf >= threshold

    # ------------------------------------------------------------------
    @property
    def gallery_size(self) -> int:
        return len(self._gallery)

    def gallery_summary(self) -> list[dict]:
        return [
            {"attack_type": e.attack_type, "n_steps": e.n_steps,
             "embedding": e.embedding.tolist()}
            for e in self._gallery
        ]

    # ------------------------------------------------------------------
    def _embed_sequence(self, obs_seq: np.ndarray) -> np.ndarray:
        """Mean embedding of an observation sequence."""
        norm = self._normalize(obs_seq)
        X_t  = torch.tensor(norm, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            mu, _ = self._vae.encoder(X_t)
        return mu.mean(dim=0).cpu().numpy()

    def _normalize(self, X: np.ndarray) -> np.ndarray:
        return np.clip((X - self._X_min) / self._X_range, 0.0, 1.0)

    def _recon_errors(self, X_norm: np.ndarray) -> np.ndarray:
        """MSE reconstruction error for each row of X_norm."""
        X_t = torch.tensor(X_norm, dtype=torch.float32, device=self.device)
        with torch.no_grad():
            recon, _, _ = self._vae(X_t)
        return ((X_t - recon) ** 2).mean(dim=1).cpu().numpy()

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        import joblib
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "vae_state":       self._vae.state_dict() if self._vae else None,
            "gallery":         self._gallery,
            "X_min":           self._X_min,
            "X_range":         self._X_range,
            "recon_threshold": self.recon_threshold_,
            "obs_dim":         self.obs_dim,
            "latent_dim":      self.latent_dim,
        }
        joblib.dump(state, path)
        print(f"[LearnedAttacks] Saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "LearnedAttackRecognizer":
        import joblib
        state = joblib.load(path)
        obj = cls(obs_dim=state["obs_dim"], latent_dim=state["latent_dim"])
        obj._vae = _VAE(obj.obs_dim, obj.latent_dim)
        obj._vae.load_state_dict(state["vae_state"])
        obj._vae.eval()
        obj._gallery         = state["gallery"]
        obj._X_min           = state["X_min"]
        obj._X_range         = state["X_range"]
        obj.recon_threshold_ = state["recon_threshold"]
        obj._fitted          = True
        return obj
