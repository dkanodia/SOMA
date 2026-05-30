# `docs/` — Project Documentation

Design documents, architecture diagrams, and implementation plan. Read these before writing any code.

---

## Reading order

1. **`SOMA_implementation_plan_v2.md`** — start here. Full build plan with time estimates, success criteria, and rationale for every major decision. Read the "What Changed From v1 and Why" section first.

2. **`SOMA_architecture_v2.mermaid`** — architecture diagram. Paste into [mermaid.live](https://mermaid.live) or any Mermaid renderer to visualize. Key nodes:
   - The `Limit` box: what the system explicitly does NOT claim
   - The `APPROX` box: κ is a utility-cost approximation, not formal RI
   - The labeled heuristic bridge between SignalingGameEnv and CybORG
   - FPR budgets in each layer subgraph header

3. **`theory/pbe_derivation.md`** — the math. Read before touching `pbe_solver.py`. Walk through the derivation, then cross-check against Carroll & Grosu (2011) Proposition 2.

---

## Files

| File | Purpose |
|---|---|
| `SOMA_implementation_plan_v2.md` | Full build plan (v2, post-steelman critique) |
| `SOMA_architecture_v2.mermaid` | Architecture diagram source |
| `theory/pbe_derivation.md` | PBE math derivation and κ sweep interpretation |

---

## Key decisions encoded in these docs

Every significant technical decision in the project has a rationale documented in `SOMA_implementation_plan_v2.md`. Before changing anything, find the relevant section and understand why the decision was made.

Decisions that must NOT be changed without updating documentation:
- Isolation Forest as primary detector (not VAE) — see "VAE replaced by Isolation Forest"
- 1% FPR budget for Layers 1 and 2, 0.1% for Layer 4 — see "False positive rate budget"
- κ sweep over {0, V/2, V} only — see "Compute budget"
- Signaling game and CybORG decoupled — see "Signaling game and CybORG are decoupled"
- κ NOT estimated from behavioral data — see "κ is not estimated"
- CMMC as table stakes, not differentiation — see "CMMC compliance"
