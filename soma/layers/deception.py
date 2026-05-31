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
    n_checkpoints: int = 10,
) -> dict:
    """
    Full κ sweep: train RL policy per κ, compare to PBE.
    Trains in n_checkpoints stages to collect learned_r_history for convergence plot.
    Returns dict of {kappa: {"learned_q", "learned_r", "learned_r_history", "pbe", "model"}}.
    Expected total compute: ~90 minutes on laptop CPU.
    """
    results = {}
    for k in KAPPA_VALUES:
        env_fn = lambda kappa=k: SignalingGameEnv(kappa=kappa)
        env    = DummyVecEnv([env_fn])
        model  = PPO("MlpPolicy", env, verbose=0, **SIGNAL_HYPERPARAMS)

        steps_per = SIGNAL_TOTAL_STEPS // n_checkpoints
        r_history = []
        for _ in range(n_checkpoints):
            model.learn(total_timesteps=steps_per, reset_num_timesteps=False)
            _, r_ckpt = evaluate_mixing_rates(model, k)
            r_history.append(r_ckpt)

        lq, lr = evaluate_mixing_rates(model, k, p_real=p_real)
        pbe    = compute_pbe(p_real, V, C, L, k)
        results[k] = {
            "learned_q": lq,
            "learned_r": lr,
            "learned_r_history": r_history,
            "pbe": pbe,
            "model": model,
        }
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


# ---------------------------------------------------------------------------
# Adaptive deception controller (stateful, per-episode)
# ---------------------------------------------------------------------------

class AdaptiveDeceptionController:
    """
    Stateful honeypot activation controller that adapts its threshold and
    rotation strategy based on observed attack activity.

    Extends the static heuristic_honeypot_trigger with:
      - Adaptive threshold: lowers when attacks are detected, recovers on quiet steps.
      - Activation cooldown: prevents flapping (min 3 steps between state changes).
      - Threat memory: tracks which hosts were previously flagged this episode.
      - Rotation budget: set by PBE q_star — floor(N_hosts × q_star) simultaneous honeypots.
      - Cooldown: set by PBE r_star — approximately 1/r_star steps between state changes.

    This is still explicitly NOT the signaling game policy — that requires a
    rational Bayesian attacker. This controller targets the scripted B_lineAgent.
    The PBE values inform the *budget* (how many honeypots) and *tempo* (how often
    to rotate), but the activation decision itself remains heuristic (score > threshold).
    """

    BASE_THRESHOLD   = 0.70  # static fallback
    MIN_THRESHOLD    = 0.45  # floor when under active attack
    DECAY_RATE       = 0.05  # threshold recovery per quiet step
    ATTACK_PRESSURE  = 0.08  # threshold drop per detected incident

    def __init__(self, kappa: float = 5.0):
        # Derive honeypot budget and rotation cooldown from PBE equilibrium.
        # q_star = P(mask real asset) → floor(N_hosts × q_star) simultaneous honeypots.
        # r_star = P(bait with honeypot) → rotation cooldown ≈ 1/r_star steps.
        # compute_pbe is already imported at the top of this module.
        _pbe = compute_pbe(p_real=0.4, V=10.0, C=3.0, L=5.0, kappa=kappa)
        self._kappa          = kappa
        self._pbe            = _pbe
        self._max_active     = max(1, int(6 * _pbe.q_star))
        self._cooldown_steps = max(1, round(1.0 / (_pbe.r_star + 1e-9)))

        self._threshold:     float           = self.BASE_THRESHOLD
        self._active:        dict[str, bool] = {}
        self._last_change:   dict[str, int]  = {}
        self._threat_memory: set[str]        = set()
        self._step: int = 0

    def reset(self) -> None:
        self._threshold    = self.BASE_THRESHOLD
        self._active       = {}
        self._last_change  = {}
        self._threat_memory.clear()
        self._step         = 0
        # _max_active, _cooldown_steps, _kappa, _pbe are kappa-derived constants —
        # they persist across episodes and must NOT be reset here.

    def update(
        self,
        host_scores: dict[str, float],
        incidents:   list,
    ) -> dict[str, bool]:
        """
        Update honeypot flags for all hosts given current scores and incidents.

        Parameters
        ----------
        host_scores : {host: suspicion_score in [0,1]}
        incidents   : list of Incident objects from correlator

        Returns
        -------
        {host: bool} — True = activate honeypot presentation on this host.
        """
        # Adapt threshold based on incident pressure
        n_high = sum(1 for inc in incidents if inc.confidence == "HIGH")
        if n_high > 0:
            self._threshold = max(
                self.MIN_THRESHOLD,
                self._threshold - self.ATTACK_PRESSURE * n_high,
            )
        else:
            self._threshold = min(
                self.BASE_THRESHOLD,
                self._threshold + self.DECAY_RATE,
            )

        # Determine desired activation for each host
        candidates = {
            h: score for h, score in host_scores.items()
            if score > self._threshold
        }

        # Rotation: if too many candidates, prefer hosts already active or
        # with the highest score; respect cooldown.
        sorted_candidates = sorted(candidates, key=lambda h: (
            self._active.get(h, False),     # keep active ones
            candidates[h],
        ), reverse=True)

        desired_active = set(sorted_candidates[:self._max_active])

        flags: dict[str, bool] = {}
        for host in host_scores:
            want = host in desired_active
            current = self._active.get(host, False)
            last_change = self._last_change.get(host, -self._cooldown_steps)

            # Enforce cooldown
            if want != current and (self._step - last_change) >= self._cooldown_steps:
                self._active[host]      = want
                self._last_change[host] = self._step

            flags[host] = self._active.get(host, False)
            if flags[host]:
                self._threat_memory.add(host)

        self._step += 1
        return flags

    @property
    def current_threshold(self) -> float:
        return self._threshold

    @property
    def threat_memory(self) -> list[str]:
        return sorted(self._threat_memory)

    def status(self) -> dict:
        return {
            "threshold":      round(self._threshold, 3),
            "active_hosts":   [h for h, v in self._active.items() if v],
            "threat_memory":  self.threat_memory,
            "step":           self._step,
            "kappa":          self._kappa,
            "max_active":     self._max_active,
            "cooldown_steps": self._cooldown_steps,
            "pbe_q_star":     round(self._pbe.q_star, 3),
            "pbe_r_star":     round(self._pbe.r_star, 3),
        }
