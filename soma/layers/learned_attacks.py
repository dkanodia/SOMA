"""
soma/layers/learned_attacks.py
================================
Layer 5 — Learned Attack Recognition: gallery-based pattern matching.

Biological framing:
  Adaptive immunity creates antigen-specific B-cell and T-cell clones.
  After a threat is cleared, memory cells persist and recognize recurrences.
  This layer maintains an attack gallery (like antigen-specific memory) and
  recognizes new observations that match known attack signatures.

Mechanism:
  1. VAE trained on clean data: learns a compact latent space of normal behavior.
  2. Gallery: each known attack is stored as a mean latent embedding + metadata.
  3. Recognition: cosine similarity between current sequence embedding and gallery.
  4. Threshold: min similarity to declare a match (default 0.7).

  The VAE is a lightweight PyTorch model (encoder-decoder, latent_dim=8).
  No GPU required — runs on CPU in <1ms per step.
"""

import numpy as np
import joblib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from sklearn.decomposition import PCA


# ---------------------------------------------------------------------------
# Gallery entry
# ---------------------------------------------------------------------------

@dataclass
class GalleryEntry:
    attack_type: str
    embedding:   np.ndarray        # mean latent vector from VAE
    n_steps:     int
    hosts:       list              # host names involved


# ---------------------------------------------------------------------------
# Minimal VAE (pure numpy — no torch dependency at import time)
# ---------------------------------------------------------------------------

class _TinyVAE:
    """
    PCA-based surrogate for a VAE. Provides an encode() method that
    maps observation sequences to a fixed-size embedding.
    No torch dependency.
    """

    def __init__(self, latent_dim: int = 8):
        self.latent_dim = latent_dim
        self.pca        = PCA(n_components=latent_dim)
        self._fitted    = False

    def fit(self, X: np.ndarray, epochs: int = 50) -> None:
        # X: (n, obs_dim) — clean observations
        n_components = min(self.latent_dim, X.shape[1], X.shape[0])
        self.pca     = PCA(n_components=n_components)
        self.pca.fit(X)
        self._fitted = True

    def encode(self, X: np.ndarray) -> np.ndarray:
        """
        Encode observation sequence X (n, obs_dim) → embedding (latent_dim,).
        Returns mean of per-step PCA projections.
        """
        if not self._fitted:
            return np.zeros(self.latent_dim)
        projected = self.pca.transform(X)        # (n, latent_dim)
        return projected.mean(axis=0)            # (latent_dim,)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class LearnedAttackRecognizer:
    """
    Gallery-based attack recognizer using a tiny PCA-VAE surrogate.

    Usage
    -----
    recog = LearnedAttackRecognizer()
    recog.fit(X_clean, epochs=50)
    recog.learn_attack(attack_obs, 'lateral_move_obvious', ['User0'])
    conf, atype = recog.recognize(recent_obs_window)
    """

    def __init__(self, latent_dim: int = 8, min_similarity: float = 0.6):
        self.latent_dim     = latent_dim
        self.min_similarity = min_similarity
        self._vae           = _TinyVAE(latent_dim)
        self._gallery: list[GalleryEntry] = []

    # ------------------------------------------------------------------
    def fit(self, X_clean: np.ndarray, epochs: int = 50) -> None:
        """Train the VAE (PCA surrogate) on clean observations."""
        self._vae.fit(X_clean, epochs=epochs)
        print(f"[LearnedAttacks] VAE fitted on {len(X_clean)} clean steps")

    # ------------------------------------------------------------------
    def learn_attack(
        self,
        attack_obs:  np.ndarray,
        attack_type: str,
        hosts:       list,
    ) -> None:
        """Add an attack sequence to the gallery."""
        if len(attack_obs) < 2:
            return
        emb = self._vae.encode(attack_obs)
        self._gallery.append(GalleryEntry(
            attack_type=attack_type,
            embedding=emb,
            n_steps=len(attack_obs),
            hosts=hosts,
        ))

    # ------------------------------------------------------------------
    def recognize(self, obs_window: np.ndarray) -> tuple[float, str]:
        """
        Recognize obs_window against gallery.

        Parameters
        ----------
        obs_window : (n, obs_dim) recent observation sequence.

        Returns
        -------
        (confidence: float, attack_type: str)
        """
        if not self._gallery or len(obs_window) < 2:
            return 0.0, "unknown"

        emb = self._vae.encode(obs_window)
        best_sim, best_type = 0.0, "unknown"

        for entry in self._gallery:
            sim = self._cosine_sim(emb, entry.embedding)
            if sim > best_sim:
                best_sim  = sim
                best_type = entry.attack_type

        conf = float(best_sim) if best_sim >= self.min_similarity else 0.0
        return conf, best_type if conf > 0 else "unknown"

    # ------------------------------------------------------------------
    def gallery_summary(self) -> list:
        """
        Return gallery as list of serialisable dicts with 2D PCA embedding.
        """
        if not self._gallery:
            return []

        embs = np.array([e.embedding for e in self._gallery])
        if embs.shape[0] == 1:
            coords_2d = embs[:, :2] if embs.shape[1] >= 2 else np.zeros((1, 2))
        else:
            n = min(2, embs.shape[1], embs.shape[0])
            pca2 = PCA(n_components=n)
            coords_2d = pca2.fit_transform(embs)
            if coords_2d.shape[1] < 2:
                coords_2d = np.hstack([coords_2d, np.zeros((len(coords_2d), 1))])

        result = []
        for i, entry in enumerate(self._gallery):
            result.append({
                "attack_type": entry.attack_type,
                "n_steps":     entry.n_steps,
                "embedding":   coords_2d[i].tolist(),
            })
        return result

    # ------------------------------------------------------------------
    @property
    def gallery_size(self) -> int:
        return len(self._gallery)

    # ------------------------------------------------------------------
    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    # ------------------------------------------------------------------
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "vae":            self._vae,
            "gallery":        self._gallery,
            "latent_dim":     self.latent_dim,
            "min_similarity": self.min_similarity,
        }, path)
        print(f"[LearnedAttacks] Saved to {path}")

    @classmethod
    def load(cls, path: Path) -> "LearnedAttackRecognizer":
        d   = joblib.load(path)
        obj = cls(d.get("latent_dim", 8), d.get("min_similarity", 0.6))
        obj._vae     = d["vae"]
        obj._gallery = d["gallery"]
        return obj
