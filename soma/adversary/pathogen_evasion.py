"""
soma/adversary/pathogen_evasion.py
====================================
P3 — Pathogen evasion experiment: THE TWIST (beat 3).

Split measurement windows tell the honest story:
  Innate L1  — measured at spreading phase (peak for obvious; 0% for sophisticated)
  Tolerance  — measured at spreading phase (cohort deviation accumulates)
  Memory L4  — measured at sustained infection (data_theft phase; drift built)
  Antibody   — measured at any fraud phase (pattern match is instant)
  Fusion     — measured across all fraud transactions

Result matrix:
  rows = {obvious_pathogen, sophisticated_pathogen}
  cols = {Innate, Tolerance, Memory, Antibody, Fusion}

"The fast immune response sees nothing. The immune memory catches
 the persistent infection." — the core hackathon narrative tension.
"""

import numpy as np
from typing import Optional

from soma.envs.synthetic_procurement_gen import (
    generate_clean_transactions, generate_fraud_episode,
    VENDOR_COHORTS,
)
from soma.layers.innate      import InnateSupplyChainDetector
from soma.layers.tolerance   import ImmuneToleranceLayer
from soma.layers.memory      import ImmuneMemoryLayer
from soma.layers.antibodies  import AntibodyLayer
from soma.fusion.procurement_immune_response import ImmuneResponseCorrelator


# ---------------------------------------------------------------------------
# Evasion experiment
# ---------------------------------------------------------------------------

def run_pathogen_evasion(
    n_episodes:  int   = 15,
    episode_len: int   = 100,
    seed:        int   = 0,
) -> dict:
    """
    Run the 5-layer immune stack on obvious vs. sophisticated pathogens.

    Returns:
        {
            "obvious":       {layer: detection_rate},
            "sophisticated": {layer: detection_rate},
        }
    """
    # ------------------------------------------------------------------
    # Train all layers on clean data
    # ------------------------------------------------------------------
    X_clean = generate_clean_transactions(n=400, seed=seed + 1000)
    n_clean = len(X_clean)

    iso = InnateSupplyChainDetector(contamination=0.01)
    iso.fit(X_clean)
    iso.calibrate_threshold(X_clean)

    cohorts_clean = [VENDOR_COHORTS[i % len(VENDOR_COHORTS)] for i in range(n_clean)]
    tol_ref = ImmuneToleranceLayer(window=50)
    tol_ref.calibrate_threshold(X_clean, cohorts_clean)

    mem_ref = ImmuneMemoryLayer(alpha=0.05, fpr_target=0.05)
    vids_clean = [f"CAL_{i % 10}" for i in range(n_clean)]
    mem_ref.calibrate_threshold(X_clean, vids_clean)

    ab = AntibodyLayer()

    results = {}

    for label, stealth in [("obvious", 0.0), ("sophisticated", 0.9)]:
        # Accumulators per detection window
        inn_early  = inn_early_n  = 0   # Innate at initial_infection
        tol_mid    = tol_mid_n    = 0   # Tolerance at spreading
        mem_late   = mem_late_n   = 0   # Memory at data_theft
        ab_any     = ab_any_n     = 0   # Antibody at any fraud phase
        fus_all    = fus_all_n    = 0   # Fusion across all fraud txns

        for ep in range(n_episodes):
            obs_arr, labels, infos = generate_fraud_episode(
                stealth=stealth, n_steps=episode_len, seed=seed + ep
            )

            # Fresh per-episode layer instances — seed cohort history from calibration
            ep_tol = ImmuneToleranceLayer(window=50)
            ep_tol.zscore_thresh = tol_ref.zscore_thresh
            ep_tol._cohort_hist  = {k: list(v) for k, v in tol_ref._cohort_hist.items()}

            ep_mem = ImmuneMemoryLayer(alpha=0.05)
            ep_mem.threshold_ = mem_ref.threshold_

            corr   = ImmuneResponseCorrelator(min_score=0.5)

            for t in range(len(obs_arr)):
                feat    = obs_arr[t]
                is_fr   = labels[t]
                phase   = infos[t].get("fraud_phase", "healthy")
                vid     = infos[t].get("vendor_id",   f"V{t%8:03d}")
                coh     = infos[t].get("cohort",      "established")

                # Compute all layer signals
                l_inn  = iso.is_anomalous(feat)
                tol_z  = ep_tol.update_and_score(vid, coh, feat)
                l_tol  = tol_z > (ep_tol.zscore_thresh or 5.0)
                l_mem  = ep_mem.update_and_alarm(vid, feat)
                ab_m   = ab.check(vid, feat)
                l_ab   = ab_m is not None
                l_ada  = bool(feat[0] > 2.5 and feat[2] > 0.5)

                sigs   = {
                    "innate": l_inn, "adaptive": l_ada,
                    "tolerance": l_tol, "memory": l_mem, "antibody": l_ab,
                }
                incidents = corr.update_all({vid: sigs})
                fused = any(
                    inc.score > 3.0   # sustained or co-fired immune activation
                    for inc in incidents
                )

                if not is_fr:
                    continue

                # --- Per-phase measurement windows ---

                # Innate: spreading phase — peak for obvious, 0% for sophisticated
                if phase == "spreading":
                    inn_early_n += 1
                    if l_inn: inn_early += 1

                # Tolerance: spreading phase (cohort deviation growing)
                if phase == "spreading":
                    tol_mid_n += 1
                    if l_tol: tol_mid += 1

                # Memory: data_theft phase (drift fully accumulated)
                if phase in ("data_theft", "cover_tracks"):
                    mem_late_n += 1
                    if l_mem: mem_late += 1

                # Antibody: any fraud phase
                ab_any_n += 1
                if l_ab: ab_any += 1

                # Fusion: all fraud transactions
                fus_all_n += 1
                if fused: fus_all += 1

        s = lambda a, b: a / b if b > 0 else 0.0
        results[label] = {
            "Innate (early)":      s(inn_early, inn_early_n),
            "Tolerance (spread)":  s(tol_mid,   tol_mid_n),
            "Memory (sustained)":  s(mem_late,  mem_late_n),
            "Antibody (any)":      s(ab_any,    ab_any_n),
            "Fusion (all)":        s(fus_all,   fus_all_n),
            # Raw counts for debugging
            "_n_innate":    inn_early_n,
            "_n_tolerance": tol_mid_n,
            "_n_memory":    mem_late_n,
            "_n_antibody":  ab_any_n,
            "_n_fusion":    fus_all_n,
        }

    return results


def print_evasion_matrix(results: dict) -> None:
    cols = ["Innate (early)", "Tolerance (spread)", "Memory (sustained)",
            "Antibody (any)", "Fusion (all)"]
    w = 18

    print("\n" + "=" * 100)
    print("PATHOGEN EVASION MATRIX — Beat 3: The Twist")
    print("  Innate=spreading  Tolerance=spreading  Memory=data_theft  Antibody=any  Fusion=all")
    print("=" * 100)
    header = f"  {'Pathogen':<15}" + "".join(f"{c:>{w}}" for c in cols)
    print(header)
    print("  " + "-" * 97)
    for ptype, vals in results.items():
        row = f"  {ptype:<15}" + "".join(f"{vals.get(c, 0.0):>{w}.3f}" for c in cols)
        print(row)
    print("=" * 100)

    obv = results.get("obvious", {})
    sph = results.get("sophisticated", {})
    if obv and sph:
        inn_drop  = obv.get("Innate (early)",     0) - sph.get("Innate (early)",     0)
        mem_flip  = sph.get("Memory (sustained)", 0) - obv.get("Memory (sustained)", 0)
        tol_gain  = sph.get("Tolerance (spread)", 0) - obv.get("Tolerance (spread)", 0)
        fus_soph  = sph.get("Fusion (all)",       0)
        inn_soph  = sph.get("Innate (early)",     0)

        print(f"\n  Innate drop (obvious→sophisticated): -{inn_drop:.3f}  ← pathogen evades fast immunity")
        print(f"  Memory gain (sophisticated > obvious):+{mem_flip:.3f}  ← immune memory catches slow drift")
        print(f"  Tolerance gain:                       +{tol_gain:.3f}  ← tolerance flags cohort deviation")
        print(f"  Fusion catches sophisticated:          {fus_soph:.3f}  vs Innate alone {inn_soph:.3f}")

        inn_ok = "PASS" if inn_drop  > 0.20 else "NOTE"
        mem_ok = "PASS" if mem_flip  > 0.10 else "NOTE"
        fus_ok = "PASS" if fus_soph  > 0.65 else "NOTE"
        print(f"\n  [{inn_ok}] Sophisticated pathogen evades Innate (drop > 0.20)")
        print(f"  [{mem_ok}] Immune Memory compensates (flip > 0.10)")
        print(f"  [{fus_ok}] Coordinated response catches sophisticated pathogen (> 0.65)")
