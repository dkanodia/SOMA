"""
soma/envs/signal_game.py
========================
2-type signaling game environment for the SOMA deception layer.

STANDALONE — does not depend on CybORG.
The RL policy trained here is validated against the closed-form PBE
benchmark (see soma/theory/pbe_solver.py). It is NOT directly transferred
to CybORG because B_lineAgent does not respond to signals.

Game structure
--------------
Types:   θ ∈ {Real=1, Honeypot=0}  drawn with prior p = P(Real)
Signals: s ∈ {AppearReal=1, AppearHoneypot=0}  chosen by defender
Actions: a ∈ {Attack=1, Pass=0}  chosen by attacker

Payoffs (defender perspective):
  Attacker attacks Real host:    -V  (asset compromised)
  Attacker attacks Honeypot:     +C  (counterintelligence gain)
  Attacker passes:                0  (no event)

Attacker rationality assumption
--------------------------------
Receiver is a rational Bayesian agent. This is stated explicitly and is
NOT a characterisation of real adversary behaviour. B_lineAgent in CybORG
is not this receiver.

Attention parameter κ
----------------------
Utility-cost approximation: attacker pays κ to process the signal.
This is NOT formal rational inattention (Sims 2003; Matějka & McKay 2015).
Formal RI constrains mutual information via Shannon entropy — not done here.
κ is swept analytically in pbe_solver.py across 3 values {0, V/2, V}.
It is NOT estimated from behavioural data (unidentified without structural model).
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces


class SignalingGameEnv(gym.Env):
    """
    2-type, 2-signal, 2-action signaling game.

    Parameters
    ----------
    p_real : float
        Prior probability that a host is Real (vs Honeypot).
    V : float
        Value of a Real asset to the attacker (and loss to defender).
    C : float
        Counterintelligence gain to defender when attacker hits Honeypot.
    L : float
        Cost to attacker of hitting a Honeypot.
    kappa : float
        Attacker attention cost (utility-cost approximation, see module docstring).
    n_hosts : int
        Number of hosts in the game per episode step.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        p_real: float = 0.4,
        V: float = 10.0,
        C: float = 3.0,
        L: float = 5.0,
        kappa: float = 0.0,
        n_hosts: int = 5,
    ):
        super().__init__()
        self.p = p_real
        self.V = V
        self.C = C
        self.L = L
        self.kappa = kappa
        self.n = n_hosts

        # Defender chooses signal per host: 0=AppearHoneypot, 1=AppearReal
        self.action_space = spaces.MultiBinary(n_hosts)

        # Observation: true host types (known to defender, not attacker)
        self.observation_space = spaces.MultiBinary(n_hosts)

        self.true_types: np.ndarray = np.zeros(n_hosts, dtype=np.int8)
        self.beliefs: np.ndarray = np.full(n_hosts, p_real)

    # ------------------------------------------------------------------
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.true_types = self.np_random.binomial(1, self.p, self.n).astype(np.int8)
        self.beliefs = np.full(self.n, self.p)
        return self.true_types.copy(), {}

    # ------------------------------------------------------------------
    def step(self, defender_signal: np.ndarray):
        """
        Defender sends signal vector. Attacker updates beliefs and decides.

        Returns
        -------
        obs, reward, terminated, truncated, info
        """
        defender_signal = np.asarray(defender_signal, dtype=np.int8)
        assert defender_signal.shape == (self.n,)

        attacker_actions = np.zeros(self.n, dtype=np.int8)
        defender_reward = 0.0

        for i in range(self.n):
            s     = int(defender_signal[i])
            theta = int(self.true_types[i])

            mu = self._bayesian_update(s, float(self.beliefs[i]))
            self.beliefs[i] = mu

            # Attacker attacks iff E[payoff] - kappa > 0
            # E[payoff | attack] = mu * V - (1 - mu) * L   (attacker perspective)
            ev_attack = mu * self.V - (1.0 - mu) * self.L - self.kappa
            attacker_actions[i] = 1 if ev_attack > 0.0 else 0

            if attacker_actions[i] == 1:
                defender_reward += -self.V if theta == 1 else self.C

        # Draw new types for next step
        self.true_types = self.np_random.binomial(1, self.p, self.n).astype(np.int8)

        info = {"attacker_actions": attacker_actions.copy()}
        return self.true_types.copy(), defender_reward, False, False, info

    # ------------------------------------------------------------------
    def _bayesian_update(self, signal: int, prior: float) -> float:
        """
        Posterior P(Real | signal) under uniform attacker prior on defender strategy.
        In equilibrium this would use the true equilibrium mixing rates.
        Off-equilibrium: attacker uses symmetric likelihood (0.6 / 0.4).
        TODO: update to use equilibrium mixing rates once PBE is solved.
        """
        if signal == 1:  # AppearReal
            lr, lh = 0.6, 0.4   # P(AppearReal | Real), P(AppearReal | Honeypot)
        else:            # AppearHoneypot
            lr, lh = 0.4, 0.6

        num = lr * prior
        den = lr * prior + lh * (1.0 - prior)
        return num / (den + 1e-9)

    # ------------------------------------------------------------------
    def render(self):
        pass   # no rendering needed for training

    def close(self):
        pass
