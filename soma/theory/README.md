# `soma/theory/` — Game-Theoretic Foundation

This module contains the **only pure-math code** in the project. It has no runtime dependency on RL, CybORG, or PyTorch. It can be imported, tested, and reasoned about independently.

---

## `pbe_solver.py` — Perfect Bayesian Equilibrium Solver

### What this is

A closed-form solver for the semi-separating PBE of a 2×2 signaling game between a defender (sender with private type information) and an attacker (rational Bayesian receiver).

The mathematics follow Carroll & Grosu (2011), "Deception in Optimal Control." Cross-check the closed-form expressions against **Proposition 2** of that paper before the pitch. The paper is freely available.

### What to complete

The `compute_pbe` function is already implemented. The full `TODO` list is:

1. **Verify the closed-form against Carroll & Grosu (2011) Proposition 2.** The current expressions may have sign errors or missing cases. Read the paper, compare equation by equation. This is not optional — the convergence plot's validity depends on the PBE being correct.

2. **Add the separating/pooling equilibrium classification.** The current code always returns semi-separating rates. Add a check for when the separating equilibrium fails to exist and when pooling is the only equilibrium. Classification logic:
   - If `mu_star >= p_real`: no-attack equilibrium (attacker never attacks regardless of signal). Return `PBEResult(q_star=0.0, r_star=0.0, mu_star=mu_star)`.
   - If `mu_star <= 0`: attacker always attacks. Return `PBEResult(q_star=1.0, r_star=1.0, mu_star=mu_star)`.
   - Otherwise: semi-separating (current code path).

3. **Add `docs/theory/pbe_derivation.md`** with the full derivation. Judges from economics or game theory backgrounds will ask for it.

### The closed-form — what the current code computes

**Attack threshold:** The attacker attacks iff posterior belief `μ = P(Real | signal)` exceeds `μ*`:

```
μ* = (L + κ) / (V + L + κ)
```

At `κ = 0`: `μ* = L / (V + L) = 5 / 15 = 0.333` (test this in `test_pbe_solver.py::test_zero_kappa_baseline`).

**Defender's indifference condition on Honeypot type** gives `r*`:

The defender is indifferent between signaling AppearReal and AppearHoneypot for a Honeypot host when the posterior belief under AppearReal equals `μ*`. Solving Bayes' rule:

```
μ* = (p * (1 - q)) / (p * (1 - q) + (1 - p) * r)
```

Solving for `r`:

```
r* = ((1 - μ*) / μ*) * (p / (1 - p)) * (C / (C + V))
```

where `p = p_real`. Clipped to `[0, 1]`.

**Posterior pinning gives `q*`:** Given `r*`, the attacker's posterior under `AppearHoneypot` signal must equal `μ*` in the semi-separating equilibrium. Solving:

```
μ* = (p * q) / (p * q + (1 - p) * (1 - r*))
```

Solving for `q`:

```
q* = μ* * (1 - p) * (1 - r*) / (p * (1 - μ*))
```

Clipped to `[0, 1]`.

**Economic interpretation:**

| κ | μ* | r* | Meaning |
|---|---|---|---|
| 0.0 (fully attentive) | 0.333 | lower | Defender must be careful — attacker responds precisely to signals |
| 5.0 (V/2) | 0.500 | higher | Attacker needs 50% confidence — defender can bait more |
| 10.0 (V) | 0.600 | highest | Attacker is costly to persuade — defender bluffs freely |

The monotonic r* increase is the key theoretical result. The convergence plot shows RL learning to recover these values.

### `kappa_sweep` — what it produces

Returns a `dict[float, PBEResult]` for κ ∈ {0.0, V/2, V}. Three values are sufficient to characterize the monotonic relationship. More values extend compute time without adding inferential value.

Output printed by `print_sweep()` should look like:

```
     κ    μ*    q*    r*  Interpretation
---------------------------------------------------------
   0.0  0.333  0.XXX  0.XXX  fully attentive   — defend carefully
   5.0  0.500  0.XXX  0.XXX  moderate attention
  10.0  0.600  0.XXX  0.XXX  inattentive       — bait freely
```

### κ — what it is and what it is NOT

κ is a **scalar subtracted from the attacker's expected payoff** for processing the defender's signal. This is a **tractable approximation**, not formal rational inattention.

Formal RI (Sims 2003, "Implications of Rational Inattention"; Matějka & McKay, AER 2015, "Rational Inattention to Discrete Choices") constrains the mutual information between the attacker's state variable and their action using a Shannon entropy-measured information cost. Implementing true RI would require solving a constrained optimization problem over joint distributions — tractable only for special cases.

In the pitch: "We use κ as a tractable approximation to the attacker's attention cost. Formal rational inattention constrains mutual information via Shannon entropy — we don't implement that, and we say so."

### Testing requirements

All tests in `tests/test_pbe_solver.py` must pass. Key assertions:

1. `μ* = L / (V + L)` at `κ = 0` — exact to machine precision
2. `μ*` strictly increases with κ — verified over the sweep
3. `r*` strictly increases with κ — the main theoretical result
4. `0 ≤ q*, r* ≤ 1` for all κ in the sweep — mixing rates are probabilities
5. At `p_real = 0` (all honeypots): `r*` should be 0 (no real hosts to protect)
6. At `p_real = 1` (all real): q* should be high (defender must hide everything)

### `PBEResult` dataclass — fields and their roles

```python
@dataclass
class PBEResult:
    q_star:  float   # P(AppearHoneypot | θ=Real)   — defender hides real hosts
    r_star:  float   # P(AppearReal | θ=Honeypot)    — defender baits with honeypots
    mu_star: float   # attacker's attack threshold
    kappa:   float   # κ used to compute this result
```

`r_star` is the primary plot variable in the convergence panel. The hero visual shows the cyan RL line converging toward the purple PBE `r_star` line during training.

### Dependency graph

```
pbe_solver.py
  ← used by: soma/envs/signal_game.py  (_bayesian_update likelihoods)
  ← used by: soma/layers/deception.py  (run_convergence_study)
  ← used by: soma/viz/plots.py          (plot_convergence, plot_kappa_sweep)
  ← used by: tests/test_pbe_solver.py
  ← used by: notebooks/04_signaling_game_theory.ipynb
```

No dependency on any other SOMA module. Pure Python + NumPy only. This is intentional — the theory should be independently testable.

### Reference

Carroll, T., & Grosu, R. (2011). A game theoretic investigation of deception in network security. *Computer Networks*, 55(6), 1162–1175. Free on ResearchGate.

Read Section 4 (the honeypot game) and Proposition 2 specifically. The notation differs slightly from ours — their `α` corresponds to our `r` (honeypot baiting rate).
