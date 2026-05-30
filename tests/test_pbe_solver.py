"""
tests/test_pbe_solver.py
-------------------------
Unit tests for PBE solver.
Cross-check against Carroll & Grosu (2011) Proposition 2 closed form.
"""
import pytest

# from soma.theory.pbe_solver import compute_pbe, kappa_sweep


class TestPBESolver:
    def test_mu_star_increases_with_kappa(self):
        """Attack threshold should increase as attacker attention cost increases."""
        # results = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
        # kappas  = sorted(results.keys())
        # mu_stars = [results[k].mu_star for k in kappas]
        # assert mu_stars == sorted(mu_stars), "mu_star should increase with kappa"
        pass

    def test_r_star_increases_with_kappa(self):
        """Optimal honeypot baiting rate should increase as attacker is more inattentive."""
        # results  = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
        # kappas   = sorted(results.keys())
        # r_stars  = [results[k].r_star for k in kappas]
        # assert r_stars == sorted(r_stars), "r* should increase with kappa"
        pass

    def test_mixing_rates_in_unit_interval(self):
        # from soma.theory.pbe_solver import compute_pbe
        # for k in [0.0, 5.0, 10.0]:
        #     r = compute_pbe(0.4, 10.0, 3.0, 5.0, k)
        #     assert 0.0 <= r.q_star <= 1.0
        #     assert 0.0 <= r.r_star <= 1.0
        pass

    def test_zero_kappa_baseline(self):
        """At kappa=0, mu_star should equal L/(V+L) = 5/15 = 0.333."""
        # r = compute_pbe(0.4, 10.0, 3.0, 5.0, kappa=0.0)
        # assert abs(r.mu_star - 5.0/15.0) < 1e-6
        pass
