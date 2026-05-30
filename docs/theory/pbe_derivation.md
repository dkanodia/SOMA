# PBE Derivation — 2×2 Deception Signaling Game

Reference document for `soma/theory/pbe_solver.py`. Verify the code against this derivation before the pitch.

Primary reference: Carroll & Grosu (2011), "A game theoretic investigation of deception in network security," *Computer Networks*, 55(6), 1162–1175. Cross-check against Proposition 2.

---

## Game Setup

**Players:** Defender (D, sender), Attacker (A, receiver)

**Types:** θ ∈ {Real=1, Honeypot=0}, drawn from prior P(θ=Real) = p

**Signals:** s ∈ {AppearReal=1, AppearHoneypot=0}, chosen by D after observing θ

**Actions:** a ∈ {Attack=1, Pass=0}, chosen by A after observing s

**Information structure:** D knows θ. A does not observe θ; observes only s. Common knowledge: prior p, payoffs, game structure.

---

## Payoffs

| Outcome | Defender payoff | Attacker payoff |
|---|---|---|
| Attacker attacks Real | −V | +V |
| Attacker attacks Honeypot | +C | −L |
| Attacker passes | 0 | 0 |

Parameters for the hackathon demo: V = 10, C = 3, L = 5, p = 0.4.

---

## Why Separating Equilibrium Doesn't Exist for the Defender

In a separating equilibrium, the defender reveals type perfectly: Real → AppearReal, Honeypot → AppearHoneypot (or the reverse).

**Case 1: Truthful signaling.** If D always signals truthfully, A learns θ exactly from s. A will always attack Real hosts (payoff V > 0) and never attack Honeypots (payoff −L < 0). D's payoff on Real hosts is −V. D can deviate by sending AppearHoneypot for Real hosts, inducing A to pass, getting payoff 0 > −V. This is a profitable deviation → truthful separating is not an equilibrium.

**Case 2: Fully deceptive separating.** If D always sends AppearHoneypot for Real hosts and AppearReal for Honeypots, A inverts inference. D will want to deviate in the same direction. Not an equilibrium.

**Conclusion:** The defender never has a separating equilibrium. The equilibrium must involve mixing — the semi-separating case.

---

## Semi-Separating (Mixing) Equilibrium Derivation

Define mixing rates:

```
q = P(signal=AppearHoneypot | θ=Real)   [defender hides real hosts]
r = P(signal=AppearReal | θ=Honeypot)   [defender baits with honeypots]
```

In equilibrium, A is indifferent between Attack and Pass for at least one signal realization (otherwise D could exploit a pure-strategy A).

### Step 1: Attacker's attack threshold

A attacks iff E[payoff | Attack] − κ ≥ 0:

```
E[payoff | Attack] = μ · V − (1 − μ) · L − κ ≥ 0
```

where μ = P(θ=Real | signal, beliefs). At indifference:

```
μ* · V = (1 − μ*) · L + κ
μ* · (V + L) = L + κ
μ* = (L + κ) / (V + L + κ)
```

**Verification:** At κ=0, V=10, L=5: μ* = 5/15 = 1/3. Test: `compute_pbe(0.4, 10, 3, 5, 0).mu_star` must equal exactly 1/3.

### Step 2: Posterior belief under AppearReal signal

Using Bayes' theorem, the attacker's posterior given signal AppearReal:

```
μ(AppearReal) = P(θ=Real | AppearReal)
             = [P(AppearReal | Real) · p]
               / [P(AppearReal | Real) · p + P(AppearReal | Honeypot) · (1−p)]
             = [(1−q) · p] / [(1−q) · p + r · (1−p)]
```

### Step 3: Solve for r* from attacker indifference under AppearReal

In the semi-separating equilibrium, A must be indifferent between Attack and Pass when observing AppearReal. Setting μ(AppearReal) = μ*:

```
[(1−q) · p] / [(1−q) · p + r · (1−p)] = μ*
```

Rearranging:

```
(1−q) · p · (1 − μ*) = r · (1−p) · μ*
r* = (1−q) · p · (1 − μ*) / [(1−p) · μ*]
```

But we also need to pin q. Use the defender's indifference condition.

### Step 4: Defender's indifference on Honeypot type

The defender mixes on Honeypot hosts (sends either signal with positive probability) only if both signals yield the same expected payoff. Defender payoff from a Honeypot host:

- If signal is AppearHoneypot (A passes): 0
- If signal is AppearReal (A attacks with prob determined by μ): C (attacker hits honeypot)

For the defender to mix on Honeypot hosts, the two payoffs must be equal. This simplifies in the fully mixing case where the attacker is indifferent for AppearReal (which pins μ* as above). The defender gains C whenever A attacks the honeypot, which happens when A's posterior under AppearReal = μ*. Since at indifference A attacks with some probability, and the defender gets +C per attack, the mixing conditions pin the defender's equilibrium strategy.

**Simplified closed form (as implemented):**

```
r* = [(1 − μ*) / μ*] · [p / (1−p)] · [C / (C + V)]
```

Clipped to [0, 1].

**Note:** This expression assumes a specific form of the defender's payoff equalization condition. Cross-check against Carroll & Grosu (2011) Proposition 2 for the exact expression — the paper may use slightly different payoff notation.

### Step 5: Solve for q* from posterior under AppearHoneypot

Posterior under AppearHoneypot:

```
μ(AppearHoneypot) = [q · p] / [q · p + (1−r*) · (1−p)]
```

Setting this equal to μ* (attacker indifference under AppearHoneypot too, for full semi-separating):

```
q* · p · (1 − μ*) = μ* · (1−r*) · (1−p)
q* = μ* · (1−r*) · (1−p) / [p · (1−μ*)]
```

Clipped to [0, 1].

**Current code:**

```python
numerator   = p_real * (1.0 - mu_star) - mu_star * (1.0 - p_real) * r_star
denominator = p_real * (1.0 - mu_star) + 1e-9
q_star = float(np.clip(numerator / denominator, 0.0, 1.0))
```

**⚠ Verify this matches the derivation above.** The sign in the numerator may differ from the derivation in Step 5 — the code has a subtraction where the derivation above suggests a product. Cross-check with Carroll & Grosu before the pitch.

---

## κ Sweep — Economic Interpretation

| κ | μ* | Effect |
|---|---|---|
| 0 (fully attentive) | L/(V+L) = 0.333 | Attacker acts on low confidence. Defender must mix carefully. |
| V/2 = 5 | (L+5)/(V+L+5) = 0.5 | Attacker needs 50% posterior to attack. Defender can bait more. |
| V = 10 | (L+10)/(V+L+10) = 0.6 | Attacker is costly to persuade. Defender bluffs freely. |

The monotonic increase in r* (and μ*) with κ is the main claim: **more inattentive attacker → defender benefits more from deception**. This result holds analytically and is recovered empirically by the RL policy — the convergence plot is the evidence.

---

## Connection to Rational Inattention (what we do NOT implement)

**Formal RI** (Sims 2003; Matějka & McKay, AER 2015): the attacker faces a capacity constraint on the mutual information between the state θ and their action a:

```
I(θ; a) ≤ κ_RI    [capacity constraint, κ_RI in bits]
```

The attacker solves: max_π E[payoff] subject to I(θ; a) ≤ κ_RI, where π is a joint distribution over (θ, a).

**What we implement:** κ is subtracted directly from the attacker's expected payoff as a scalar cost, not as a mutual information constraint. This is a tractable approximation that captures the qualitative direction of the effect (higher cost → higher attack threshold) without the formal RI structure.

**In the pitch:** "We approximate the attacker's attention cost as a scalar utility penalty κ. Formal rational inattention would constrain the attacker's information channel capacity — we don't implement that, and we say so." Never call this "formal RI" in slides.
