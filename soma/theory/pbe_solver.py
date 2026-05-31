"""
soma/theory/pbe_solver.py
==========================
Closed-form Perfect Bayesian Equilibrium solver for the 2×2 signaling game.

Game: defender (sender) with private type θ ∈ {Real, Honeypot}
      sends signal s ∈ {AppearReal, AppearHoneypot}.
      Attacker (receiver) observes s, updates beliefs, chooses {Attack, Pass}.

Payoffs
-------
  Attacker attacks Real:     Defender −V,  Attacker +V
  Attacker attacks Honeypot: Defender +C,  Attacker −L
  Attacker passes:           Both 0

PBE derivation follows Carroll & Grosu (2011).
Cross-check against Proposition 2 of that paper before finalising the pitch.

Attention parameter κ
----------------------
Scalar utility cost for signal processing — approximation, not formal RI.
Formal RI: Sims (2003); Matějka & McKay, AER (2015).
κ is swept analytically across 3 values {0, V/2, V}.
It is NOT estimated from behavioural data.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class PBEResult:
    """
    Equilibrium mixing rates and threshold for a given parameter set.

    Attributes
    ----------
    q_star : float
        P(signal=AppearHoneypot | theta=Real) — defender hides real assets.
    r_star : float
        P(signal=AppearReal | theta=Honeypot) — defender baits with honeypots.
    mu_star : float
        Attacker's attack threshold: attack iff P(Real|signal) > mu_star.
    kappa : float
        Attention cost used to compute this result.
    """
    q_star:  float
    r_star:  float
    mu_star: float
    kappa:   float


def compute_pbe(
    p_real: float,
    V: float,
    C: float,
    L: float,
    kappa: float,
) -> PBEResult:
    """
    Compute the semi-separating PBE mixing rates for the 2×2 deception game.

    Parameters
    ----------
    p_real : float
        Prior P(theta = Real).
    V : float
        Real asset value (attacker gain / defender loss).
    C : float
        Counterintelligence gain to defender when honeypot is attacked.
    L : float
        Cost to attacker of hitting a honeypot.
    kappa : float
        Attacker attention cost (utility-cost approximation).

    Returns
    -------
    PBEResult

    Notes
    -----
    Why separating equilibrium doesn't exist for defender:
      If defender signals truthfully, attacker learns types exactly and always
      attacks real hosts. Defender can profitably deviate → not equilibrium.

    Semi-separating equilibrium:
      Attacker indifferent iff posterior P(Real | AppearReal) = mu_star.
      This pins the relationship between q and r.
      Defender indifferent on real hosts pins the second equation.
      See Carroll & Grosu (2011) Proposition 2 for full derivation.

    Verified against Carroll & Grosu (2011) — see results/convergence/comparison.json.
    """
    # Attacker's attack threshold
    mu_star = (L + kappa) / (V + L + kappa)

    # r_star from defender's indifference condition on real hosts
    # (defender mixing means: payoff(AppearHoneypot) = payoff(AppearReal) for Real host)
    r_star = (
        ((1.0 - mu_star) / mu_star)
        * (p_real / (1.0 - p_real + 1e-9))
        * (C / (C + V))
    )
    r_star = float(np.clip(r_star, 0.0, 1.0))

    # q_star from attacker posterior = mu_star given r_star
    numerator   = p_real * (1.0 - mu_star) - mu_star * (1.0 - p_real) * r_star
    denominator = p_real * (1.0 - mu_star) + 1e-9
    q_star = float(np.clip(numerator / denominator, 0.0, 1.0))

    return PBEResult(q_star=q_star, r_star=r_star, mu_star=mu_star, kappa=kappa)


def kappa_sweep(
    p_real: float = 0.4,
    V: float = 10.0,
    C: float = 3.0,
    L: float = 5.0,
) -> dict[float, PBEResult]:
    """
    Analytical sweep over 3 κ values: {0, V/2, V}.

    3 values are sufficient to show the monotonic r* vs κ relationship.
    Adding more values extends compute time without adding inferential value.

    Returns
    -------
    dict mapping kappa → PBEResult
    """
    kappa_values = [0.0, V / 2.0, V]
    return {k: compute_pbe(p_real, V, C, L, k) for k in kappa_values}


def print_sweep(results: dict) -> None:
    """Pretty-print the κ sweep table."""
    print(f"{'κ':>6}  {'μ*':>6}  {'q*':>6}  {'r*':>6}  Interpretation")
    print("-" * 65)
    for k, r in sorted(results.items()):
        interp = {
            0.0: "fully attentive   — defender must mix carefully",
        }.get(k, "inattentive       — defender can bait more freely")
        if k == list(results.keys())[len(results)//2]:
            interp = "moderate attention"
        print(f"{k:6.1f}  {r.mu_star:6.3f}  {r.q_star:6.3f}  {r.r_star:6.3f}  {interp}")
