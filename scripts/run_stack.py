"""
scripts/run_stack.py
=====================
Full immune stack validation on synthetic procurement data.
Prints the pathogen-evasion matrix and immune-response fusion table.
Pre-renders all demo assets. Use before the pitch.

Usage:
  python -m scripts.run_stack               # full run
  python -m scripts.run_stack --quick       # fewer episodes (fast sanity check)
  python -m scripts.run_stack --demo        # also export static demo episode
"""

import argparse
import json
import sys
from pathlib import Path

RESULTS   = Path("results")
RESULTS_FUSION  = RESULTS / "fusion"
RESULTS_EVASION = RESULTS / "evasion"
RESULTS_DEMO    = RESULTS

for p in [RESULTS_FUSION, RESULTS_EVASION]:
    p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Step 0: Synthetic environment sanity check
# ---------------------------------------------------------------------------

def run_env_check() -> bool:
    print("\n" + "=" * 60)
    print("STEP 0: Synthetic Procurement Environment")
    print("=" * 60)

    from soma.envs.synthetic_procurement_gen import (
        SyntheticProcurementGen, generate_clean_transactions,
        generate_fraud_episode, VENDOR_COHORTS, FEATURE_NAMES,
    )

    gen = SyntheticProcurementGen(n_vendors=8, seed=42)
    gen.reset()
    all_txns = []
    for _ in range(20):
        all_txns.extend(gen.step())

    print(f"  Vendors:         {gen.n_vendors}")
    print(f"  Cohorts:         {VENDOR_COHORTS}")
    print(f"  Features:        {len(FEATURE_NAMES)}")
    print(f"  Transactions/20 steps: {len(all_txns)}")

    X_clean = generate_clean_transactions(n=100, seed=0)
    print(f"  Clean data shape: {X_clean.shape}")
    print(f"  Feature range:    [{X_clean.min():.3f}, {X_clean.max():.3f}]")

    obs, lbl, inf = generate_fraud_episode(stealth=0.0, n_steps=50, seed=0)
    n_fraud = lbl.sum()
    print(f"  Fraud episode: {len(obs)} txns, {n_fraud} fraudulent "
          f"({n_fraud/max(len(obs),1)*100:.1f}%)")

    ok = X_clean.shape[1] == 11 and n_fraud > 0
    print(f"  [{'PASS' if ok else 'FAIL'}] Synthetic env OK")
    return ok


# ---------------------------------------------------------------------------
# Step 1: Innate immunity (Layer 1) sanity check
# ---------------------------------------------------------------------------

def run_innate_check(quick: bool = False) -> dict:
    print("\n" + "=" * 60)
    print("STEP 1: Innate Immunity (Layer 1 — Isolation Forest)")
    print("=" * 60)

    from soma.layers.innate import InnateSupplyChainDetector
    from soma.envs.synthetic_procurement_gen import (
        generate_clean_transactions, generate_fraud_episode,
    )

    X_clean = generate_clean_transactions(n=300 if not quick else 100, seed=42)
    iso = InnateSupplyChainDetector(contamination=0.01)
    iso.fit(X_clean)
    iso.calibrate_threshold(X_clean)

    # Quick FPR check
    fpr = float((iso.anomaly_scores_batch(X_clean) > iso.threshold_).mean())
    print(f"  Calibrated FPR (clean):  {fpr:.4f}")

    # Quick TPR check on obvious pathogen
    obs, lbl, _ = generate_fraud_episode(stealth=0.0, n_steps=60, seed=99)
    if lbl.sum() > 0:
        tpr = float((iso.anomaly_scores_batch(obs[lbl]) > iso.threshold_).mean())
        print(f"  TPR (obvious pathogen):  {tpr:.3f}")
    else:
        tpr = 0.0

    ok = fpr <= 0.025 and tpr >= 0.50
    print(f"  [{'PASS' if ok else 'NOTE'}] L1 innate immunity calibrated")
    return {"fpr": fpr, "tpr": tpr}


# ---------------------------------------------------------------------------
# Step 2: Pathogen evasion matrix (beat 3: THE TWIST)
# ---------------------------------------------------------------------------

def run_evasion(quick: bool = False) -> dict:
    print("\n" + "=" * 60)
    print("STEP 2: Pathogen Evasion Matrix — The Twist (Beat 3)")
    print("=" * 60)

    from soma.adversary.pathogen_evasion import (
        run_pathogen_evasion, print_evasion_matrix,
    )

    n_ep = 8 if quick else 15
    results = run_pathogen_evasion(n_episodes=n_ep, episode_len=80, seed=0)
    print_evasion_matrix(results)

    # Save
    path = RESULTS_EVASION / "evasion_matrix.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"\n  Saved: {path}")

    obv = results.get("obvious", {})
    sph = results.get("sophisticated", {})
    inn_drop = obv.get("Innate (early)", 0) - sph.get("Innate (early)", 0)
    fus_ok   = sph.get("Fusion (all)", 0) >= 0.55
    drop_ok  = inn_drop >= 0.20

    print(f"  [{'PASS' if drop_ok else 'NOTE'}] Innate drop > 0.20 "
          f"(actual: {inn_drop:.3f})")
    print(f"  [{'PASS' if fus_ok  else 'NOTE'}] Fusion catches sophisticated > 0.55 "
          f"(actual: {sph.get('Fusion (all)', 0):.3f})")
    return results


# ---------------------------------------------------------------------------
# Step 3: Immune response fusion table (beat 4: THE NUMBER)
# ---------------------------------------------------------------------------

def run_fusion(quick: bool = False) -> dict:
    print("\n" + "=" * 60)
    print("STEP 3: Coordinated Immune Response — THE NUMBER (Beat 4)")
    print("=" * 60)

    from soma.fusion.procurement_immune_response import (
        compute_immune_response_table, print_immune_response_table,
    )
    from soma.envs.synthetic_procurement_gen import generate_fraud_episode

    obs, lbl, inf = generate_fraud_episode(stealth=0.0, n_steps=80, seed=42)
    vids = [i["vendor_id"] for i in inf]
    result = compute_immune_response_table(obs, lbl, vids)
    print_immune_response_table(result)

    path = RESULTS_FUSION / "immune_response_table.json"
    save = {k: v for k, v in result.items() if k != "error"}
    path.write_text(json.dumps(save, indent=2))
    print(f"\n  Saved: {path}")

    ratio  = result.get("fpr_reduction_factor", 0)
    ok     = ratio >= 3
    rstr   = f"{ratio:.1f}x" if ratio < 1e7 else "∞ (0 false alarms)"
    print(f"  [{'PASS' if ok else 'NOTE'}] FPR reduction: {rstr} (target ≥ 3x)")
    return result


# ---------------------------------------------------------------------------
# Step 4: Static demo episode
# ---------------------------------------------------------------------------

def run_demo_export() -> None:
    print("\n" + "=" * 60)
    print("STEP 4: Exporting Static Demo Episode")
    print("=" * 60)

    from scripts.demo import export_static
    export_static(
        output_path=RESULTS_DEMO / "demo_episode.json",
        stealth=0.0,
        n_steps=100,
    )
    # Copy to frontend public
    import shutil
    dst = Path("frontend/public/demo_episode.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(RESULTS_DEMO / "demo_episode.json", dst)
    print(f"  Copied to {dst}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(
    innate_result: dict,
    evasion_result: dict,
    fusion_result: dict,
) -> None:
    print("\n" + "=" * 60)
    print("RUN COMPLETE — Immune Stack Summary")
    print("=" * 60)

    obv = evasion_result.get("obvious", {})
    sph = evasion_result.get("sophisticated", {})
    ratio = fusion_result.get("fpr_reduction_factor", 0)
    rstr  = f"{ratio:.1f}x" if ratio < 1e7 else "∞"

    print(f"  L1 Innate FPR:           {innate_result.get('fpr', 0):.4f}")
    print(f"  L1 Innate TPR (obvious): {innate_result.get('tpr', 0):.3f}")
    print(f"  Innate obvious:          {obv.get('Innate (early)', 0):.3f}")
    print(f"  Innate sophisticated:    {sph.get('Innate (early)', 0):.3f}  ← should be low")
    print(f"  Memory sophisticated:    {sph.get('Memory (sustained)', 0):.3f}  ← should be high")
    print(f"  Fusion sophisticated:    {sph.get('Fusion (all)', 0):.3f}")
    print(f"  FPR reduction:           {rstr}")

    print("\n  DEMO ASSETS:")
    for p in [
        RESULTS_EVASION / "evasion_matrix.json",
        RESULTS_FUSION  / "immune_response_table.json",
        RESULTS_DEMO    / "demo_episode.json",
        Path("frontend/public/demo_episode.json"),
    ]:
        status = "[OK]" if p.exists() else "[MISSING]"
        print(f"    {status} {p}")

    print("\n  Run: cd frontend && npm start")
    print("  Run: python -m scripts.demo --stealth 0   (live server)")
    print("  Run: python -m scripts.demo --static       (pre-render)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SOMA Immune Stack Validation")
    parser.add_argument("--quick", action="store_true", help="Fewer episodes (fast check)")
    parser.add_argument("--demo",  action="store_true", help="Also export static demo episode")
    parser.add_argument("--skip-fusion", action="store_true", help="Skip fusion table (slow)")
    args = parser.parse_args()

    env_ok = run_env_check()
    if not env_ok:
        print("Environment check failed. Aborting.")
        sys.exit(1)

    innate_result  = run_innate_check(quick=args.quick)
    evasion_result = run_evasion(quick=args.quick)

    if args.skip_fusion:
        fusion_result = {}
        print("\n[STEP 3] Skipped fusion table (--skip-fusion).")
    else:
        fusion_result = run_fusion(quick=args.quick)

    if args.demo:
        run_demo_export()

    print_summary(innate_result, evasion_result, fusion_result)


if __name__ == "__main__":
    main()
