"""
soma/layers/deception.py
=========================
Layer 3 — Deception: signaling game policy + heuristic bridge to CybORG.

ARCHITECTURE NOTE — two separate systems:

1. SignalingGameEnv (soma/envs/signal_game.py)
   Standalone RL training environment. Defender learns optimal deception
   mixing rates (q*, r*) against a rational Bayesian attacker.
   Validated against closed-form PBE (soma/theory/pbe_solver.py).
   This is the THEORETICAL CONTRIBUTION.

2. Heuristic bridge to CybORG (heuristic_honeypot_trigger below)
   Simple threshold trigger — if PPO suspicion score > 0.7, activate
   honeypot presentation. NOT the signaling game policy.
   B_lineAgent does not respond to signals, so the game-theoretic policy
   cannot be applied here. This is stated explicitly in the demo.

The distinction is a feature: showing you understand the gap between
theory (rational adversary, clean environment) and implementation
(scripted adversary, simulation) is more credible than pretending
the transfer is justified.
"""

import numpy as np
from pathlib import Path
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

from soma.envs.signal_game import SignalingGameEnv
from soma.theory.pbe_solver import compute_pbe, kappa_sweep, PBEResult


# ---------------------------------------------------------------------------
# Signaling game RL training
# ---------------------------------------------------------------------------

SIGNAL_HYPERPARAMS = dict(
    n_steps       = 512,
    learning_rate = 1e-3,
    ent_coef      = 0.05,   # higher entropy encourages mixing — important for semi-sep equilibrium
    batch_size    = 64,
    n_epochs      = 10,
)

SIGNAL_TOTAL_STEPS  = 100_000   # per kappa value — ~30 min per run on CPU
KAPPA_VALUES        = [0.0, 5.0, 10.0]  # {0, V/2, V} for V=10


def train_signal_policy(kappa: float, total_steps: int = SIGNAL_TOTAL_STEPS) -> PPO:
    """
    Train a deception RL policy on SignalingGameEnv for a given κ.
    Compare learned mixing rates to PBE benchmark after training.
    """
    env_fn = lambda: SignalingGameEnv(kappa=kappa)
    env    = DummyVecEnv([env_fn])
    model  = PPO("MlpPolicy", env, verbose=0, **SIGNAL_HYPERPARAMS)
    model.learn(total_timesteps=total_steps)
    return model


def evaluate_mixing_rates(
    model: PPO,
    kappa: float,
    n_eval: int = 500,
    p_real: float = 0.4,
) -> tuple[float, float]:
    """
    Measure the learned policy's empirical mixing rates (q, r).

    q = P(signal=AppearHoneypot | theta=Real)    estimated from n_eval steps
    r = P(signal=AppearReal     | theta=Honeypot) estimated from n_eval steps

    Use stochastic (not deterministic) prediction to capture mixed strategies.
    """
    env = SignalingGameEnv(kappa=kappa, p_real=p_real)
    real_hid = real_tot = hp_bait = hp_tot = 0

    for _ in range(n_eval):
        obs, _ = env.reset()
        action, _ = model.predict(obs, deterministic=False)
        for i in range(env.n):
            if obs[i] == 1:          # Real host
                real_tot += 1
                if action[i] == 0:   # sent AppearHoneypot
                    real_hid += 1
            else:                    # Honeypot host
                hp_tot  += 1
                if action[i] == 1:   # sent AppearReal
                    hp_bait += 1

    q = real_hid / (real_tot + 1e-9)
    r = hp_bait  / (hp_tot  + 1e-9)
    return q, r


def run_convergence_study(
    V: float = 10.0, C: float = 3.0, L: float = 5.0, p_real: float = 0.4,
) -> dict:
    """
    Full κ sweep: train RL policy per κ, compare to PBE.
    Returns dict of {kappa: {"learned_q", "learned_r", "pbe": PBEResult}}.
    Expected total compute: ~90 minutes on laptop GPU.
    """
    results = {}
    for k in KAPPA_VALUES:
        model  = train_signal_policy(k)
        lq, lr = evaluate_mixing_rates(model, k, p_real=p_real)
        pbe    = compute_pbe(p_real, V, C, L, k)
        results[k] = {"learned_q": lq, "learned_r": lr, "pbe": pbe, "model": model}
        print(
            f"κ={k:.1f}:  learned q={lq:.3f} (PBE {pbe.q_star:.3f})"
            f"  learned r={lr:.3f} (PBE {pbe.r_star:.3f})"
        )
    return results


# ---------------------------------------------------------------------------
# Heuristic bridge to CybORG (labeled — not the game-theoretic policy)
# ---------------------------------------------------------------------------

SUSPICION_THRESHOLD = 0.7   # manually chosen — no principled basis


def heuristic_honeypot_trigger(suspicion_score: float) -> bool:
    """
    Activate deceptive honeypot presentation when PPO suspicion exceeds threshold.

    THIS IS NOT THE SIGNALING GAME POLICY.
    The signaling game policy was trained against a rational Bayesian receiver.
    B_lineAgent does not respond to signals — deploying the game-theoretic
    policy against it would be applying it to a different game.
    This heuristic is an explicit approximation and is labeled as such in the demo.

    Parameters
    ----------
    suspicion_score : float in [0, 1]
        Proxy for P(host is compromised), derived from Layer 1 anomaly scores
        and Layer 2 PPO investigation outputs.

    Returns
    -------
    bool: True = activate deceptive presentation on this host.
    """
    return suspicion_score > SUSPICION_THRESHOLD
