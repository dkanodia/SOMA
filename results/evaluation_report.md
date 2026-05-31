# SOMA Evaluation Report

**System:** SOMA — Biologically-Framed Autonomous Cyber Defense  
**Scenario:** CybORG CAGE 2 Scenario1b, B_lineAgent (deterministic 13-step attack chain)  
**Training:** PPO Blue agent, 200k steps, frozen at deployment  
**Date:** 2026-05-30

---

## 1. Per-Layer Detection Performance

| Layer | Description | TPR | FPR |
|-------|-------------|-----|-----|
| Layer 1 — Innate | Rule-based anomaly scoring (activity × 0.5 + compromised × 0.8) | 45.5% | 0.95% |
| Layer 2 — Adaptive (PPO) | Discrete(54) trained defender policy | 47.5% | 0.48% |
| Layer 3a — Tolerance | Per-host Gaussian self-model, breach_sigma=3.0 | 18.8% | 17.6% |
| Layer 4 — Memory/Drift | PCA centroid drift, LongDwellDetector | 64.4% | 0.0% |
| Layer 5 — Antibody | PCA-VAE learned attack gallery, cosine similarity | 66.7% | 0.0% |
| **Fused (all layers)** | NetworkImmuneCorrelator, weighted aggregation | **89.8%** | **35%** |

**Notes:**
- Layer 3a (Tolerance) has elevated FPR (17.6%) — per-host Gaussian model fires broadly on minor deviations from CybORG's near-deterministic clean baseline. Its weight in fusion is 0.20 and is partially offset by the multi-layer gating requirement.
- Fused FPR of 35% reflects the correlator surfacing incidents when any weighted combination of layer signals crosses the LOW threshold (0.15). The multi-layer gate (≥2 layers OR score ≥0.50) is in place but the tolerance layer's high FPR bleeds through as a soft signal.
- Best single-layer FPR: 0.0% (Antibody / Memory layers).

---

## 2. PPO Layer 2 Evaluation (scripts/evaluate.py, 100 episodes)

| Metric | Value | Threshold | Result |
|--------|-------|-----------|--------|
| Lateral movement detection rate | **98.2%** | ≥ 50% | PASS |
| Impact detection rate | **100.0%** | ≥ 80% | PASS |
| Analyze fraction (reward hacking) | **0.0%** | ≤ 70% | PASS |

Source: `results/fpr_calibration/layer2_eval.txt`

---

## 3. Evasion Matrix — Obvious vs. Sophisticated Attacks

| Layer | Obvious Attack DR | Sophisticated Attack DR |
|-------|-------------------|------------------------|
| Innate (early) | 100.0% | 0.9% |
| Tolerance (spread) | 74.8% | 8.1% |
| Memory (sustained) | 100.0% | 100.0% |
| Antibody (any) | 63.2% | 28.5% |
| **Fusion (all)** | **99.3%** | **97.8%** |

**Key headline:** The sophisticated evasion attack reduces Innate detection from 100% → 0.9%, but Memory (long-dwell drift) maintains 100% detection, and Fusion recovers to **97.8%** — validating the multi-layer immune architecture.

Source: `results/evasion/evasion_matrix.json`

---

## 4. Signal Game — RL vs. PBE Analytical Benchmark

The signaling game (Layer 3b deception) trains a PPO policy on a 2×2 signaling game across three attention-cost values κ ∈ {0, 5, 10}. Learned mixing rates are compared against the closed-form Perfect Bayesian Equilibrium (Carroll & Grosu 2011, Proposition 2).

| κ | RL q* (learned) | PBE q* (analytical) | RL r* (learned) | PBE r* (analytical) | PBE μ* |
|---|-----------------|---------------------|-----------------|---------------------|--------|
| 0.0 | 0.510 | 0.769 | 0.507 | 0.308 | 0.333 |
| 5.0 | 0.534 | 0.769 | 0.558 | 0.154 | 0.500 |
| 10.0 | 0.536 | 0.769 | 0.486 | 0.103 | 0.600 |

**Interpretation:**  
- RL q* (probability defender masks real assets) converges to ~0.51–0.54 across all κ, while the PBE analytical q* is ~0.77. The RL agent under-masks relative to the equilibrium prediction.  
- RL r* (honeypot baiting rate) shows the correct monotonic relationship with κ at κ=0 and κ=5 but inverts at κ=10, suggesting incomplete convergence at high attention costs.  
- μ* (attacker attack threshold) increases with κ as predicted: 0.33 → 0.50 → 0.60. This monotonic trend is confirmed by the PBE solver and motivates the AdaptiveDeceptionController's threshold range (0.45–0.70).
- The RL policies approach but do not fully converge to the analytical PBE, consistent with known limitations of PPO on low-dimensional mixed-strategy games (sparse reward landscape near mixing indifference).

Source: `results/convergence/comparison.json`

---

## 5. Pre- vs. Post-Fusion Comparison

| Metric | Best Single Layer | Fused |
|--------|------------------|-------|
| TPR | 66.7% (Antibody) | 89.8% |
| FPR | 0.0% (Antibody / Memory) | 35.0% |
| FPR reduction factor | — | 0.0 (no improvement) |

The fusion layer improves TPR by +23.1 pp over the best single layer but increases FPR significantly. The current correlator weights (innate 0.30, memory 0.30, tolerance_breach 0.20, learned 0.20) allow the high-FPR tolerance signal to elevate fused scores above the LOW threshold on clean steps. A stricter minimum threshold or a higher multi-layer gate would reduce fused FPR at the cost of some TPR.

---

## 6. Summary

| System Area | Key Number |
|-------------|-----------|
| PPO lateral movement DR | **98.2%** |
| PPO impact DR | **100.0%** |
| Fused TPR | **89.8%** |
| Sophisticated attack fused DR | **97.8%** |
| Innate FPR | **0.95%** (within 1% budget) |
| Memory FPR | **0.0%** |
| Fused FPR | **35%** (above target — tolerance layer contribution) |
| Signal game RL vs PBE (q* gap at κ=0) | **0.51 vs 0.77** |
