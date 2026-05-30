"""
scripts/run_cyber_stack.py
===========================
Full 5-layer immune stack validation on CybORG/synthetic network data.

Runs the complete SOMA immune response against:
  - Noisy (obvious) attack:      caught by Layer 1 in < 5 steps
  - Sophisticated (slow drift):  caught by Layer 4 in < 20 steps

Outputs:
  results/cyber/evasion_matrix.json   — per-layer detection rates
  results/cyber/detection_rates.json  — detailed per-episode metrics

Usage:
  python -m scripts.run_cyber_stack
  python -m scripts.run_cyber_stack --quick
  python -m scripts.run_cyber_stack --demo
"""

import argparse
import json
import numpy as np
from pathlib import Path

RESULTS = Path("results/cyber")
RESULTS.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Episode runner
# ---------------------------------------------------------------------------

def run_episode(
    stealth:     float,
    n_steps:     int,
    attack_start: int,
    seed:        int,
    innate_layer,
    memory_layer,
    tolerance_layer,
    learned_rec,
    corr,
) -> dict:
    """Run one attack episode; return per-step detection flags."""
    from soma.envs.synthetic_network_gen import SyntheticNetworkGen, HOST_NAMES
    from soma.layers.memory import HostDriftLayer

    gen = SyntheticNetworkGen(
        episode_length=n_steps,
        attack_start=attack_start,
        stealth=stealth,
        seed=seed,
    )
    gen.reset()

    ep_mem = HostDriftLayer(memory_k=10, recent_k=10)
    ep_mem.threshold_ = memory_layer.threshold_
    corr.reset()

    # Collect obs_seq for learned_attack recognition
    obs_buffer = []
    first_detection_step = None
    detection_layers = []

    inn_detections  = []
    mem_detections  = []
    fused_detections = []
    attack_steps    = []
    phases          = []

    for t in range(n_steps):
        obs, is_atk, info = gen.step()
        obs_buffer.append(obs)
        attack_steps.append(is_atk)
        phases.append(info["phase"])

        # Layer 1: Innate
        l_inn = innate_layer.is_anomalous(obs)
        host_scores = innate_layer.per_host_scores(obs)

        # Layer 3: Tolerance
        sup = tolerance_layer.suppressed_hosts(obs)
        brh = tolerance_layer.breach_hosts(obs)

        # Layer 4: Memory
        mem_sc = ep_mem.update_and_scores(obs)
        l_mem  = any(s > ep_mem.threshold_ for s in mem_sc.values())

        # Layer 5: Learned attacks
        la_conf, la_type = 0.0, "unknown"
        if len(obs_buffer) >= 3 and learned_rec.gallery_size > 0:
            la_conf, la_type = learned_rec.recognize(
                np.array(obs_buffer[-10:])
            )

        # Fusion
        incidents = corr.update_step(
            obs=obs,
            innate_score=innate_layer.anomaly_score(obs),
            innate_threshold=innate_layer.threshold_,
            memory_scores=mem_sc,
            memory_threshold=ep_mem.threshold_,
            tolerance_suppressed=sup,
            tolerance_breached=brh,
            learned_attack_conf=la_conf,
            learned_attack_type=la_type,
            innate_host_scores=host_scores,
        )
        fused_alarm = any(i.score > 2.0 for i in incidents)

        inn_detections.append(l_inn)
        mem_detections.append(l_mem)
        fused_detections.append(fused_alarm)

        if is_atk and first_detection_step is None:
            if fused_alarm:
                first_detection_step = t - attack_start   # steps since attack began
                detection_layers = incidents[0].layers_fired if incidents else []

    # After episode: learn the attack signature
    attack_obs = np.array([obs_buffer[t] for t in range(n_steps) if attack_steps[t]])
    if len(attack_obs) > 0:
        att_type = "sophisticated" if stealth > 0.5 else "obvious"
        learned_rec.learn_attack(attack_obs, att_type, [])

    n_atk = sum(attack_steps)
    if n_atk == 0:
        return {}

    # Per-phase detection rates
    phase_det = {}
    for phase in set(phases):
        if phase == "clean":
            continue
        mask = [attack_steps[t] and phases[t] == phase for t in range(n_steps)]
        n_p  = sum(mask)
        if n_p == 0:
            continue
        phase_det[phase] = {
            "n": n_p,
            "innate":  sum(inn_detections[t] for t in range(n_steps) if mask[t]) / n_p,
            "memory":  sum(mem_detections[t] for t in range(n_steps) if mask[t]) / n_p,
            "fused":   sum(fused_detections[t] for t in range(n_steps) if mask[t]) / n_p,
        }

    return {
        "innate_tpr":  sum(inn_detections[t] for t in range(n_steps) if attack_steps[t]) / n_atk,
        "memory_tpr":  sum(mem_detections[t] for t in range(n_steps) if attack_steps[t]) / n_atk,
        "fused_tpr":   sum(fused_detections[t] for t in range(n_steps) if attack_steps[t]) / n_atk,
        "innate_fpr":  sum(inn_detections[t] for t in range(n_steps) if not attack_steps[t]) / max(n_steps - n_atk, 1),
        "fused_fpr":   sum(fused_detections[t] for t in range(n_steps) if not attack_steps[t]) / max(n_steps - n_atk, 1),
        "first_detection_step": first_detection_step,
        "detection_layers":     detection_layers,
        "phase_detection":      phase_det,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SOMA Cyber Immune Stack Validation")
    parser.add_argument("--quick",    action="store_true", help="Fewer episodes")
    parser.add_argument("--demo",     action="store_true", help="Export demo episode")
    parser.add_argument("--episodes", type=int, default=None)
    args = parser.parse_args()

    n_ep = args.episodes or (5 if args.quick else 10)

    print("=" * 65)
    print("SOMA CYBER IMMUNE STACK — 5-Layer Validation")
    print("=" * 65)

    # ------------------------------------------------------------------
    # 1. Load or train baseline
    # ------------------------------------------------------------------
    print("\n[Step 1] Loading / training immune layers...")
    from soma.envs.synthetic_network_gen import generate_clean_episodes
    from soma.layers.innate   import InnateImmunityLayer
    from soma.layers.memory   import HostDriftLayer
    from soma.layers.tolerance import ImmuneToleranceLayer
    from soma.layers.learned_attacks import LearnedAttackRecognizer
    from soma.fusion.network_correlator import NetworkImmuneCorrelator

    model_path = Path("models/innate/baseline.joblib")
    vae_path   = Path("models/innate/vae.joblib")

    X_clean = generate_clean_episodes(n_steps=1000, seed=999)

    if model_path.exists():
        innate = InnateImmunityLayer.load(model_path)
        print(f"  Loaded innate from {model_path}")
    else:
        innate = InnateImmunityLayer(fpr_target=0.01)
        innate.fit(X_clean)
        innate.calibrate_threshold(X_clean[-200:])

    memory = HostDriftLayer(memory_k=10, recent_k=10, fpr_target=0.05)
    memory.calibrate_threshold(X_clean)

    tolerance = ImmuneToleranceLayer()
    tolerance.calibrate(X_clean)

    if vae_path.exists():
        learned = LearnedAttackRecognizer.load(vae_path)
        print(f"  Loaded VAE from {vae_path}")
    else:
        learned = LearnedAttackRecognizer()
        learned.fit(X_clean, epochs=30, verbose=False)

    # ------------------------------------------------------------------
    # 2. Evasion matrix: obvious vs sophisticated
    # ------------------------------------------------------------------
    print("\n[Step 2] Running evasion matrix experiments...")
    evasion_results = {}

    for label, stealth, attack_start in [
        ("obvious",       0.0, 10),
        ("sophisticated", 0.9, 10),
    ]:
        corr = NetworkImmuneCorrelator()
        agg = {"innate_tpr": [], "memory_tpr": [], "fused_tpr": [],
               "innate_fpr": [], "fused_fpr": [], "first_detect": []}

        for ep in range(n_ep):
            r = run_episode(
                stealth=stealth,
                n_steps=50,
                attack_start=attack_start,
                seed=ep * 100,
                innate_layer=innate,
                memory_layer=memory,
                tolerance_layer=tolerance,
                learned_rec=learned,
                corr=corr,
            )
            if r:
                for k in ["innate_tpr", "memory_tpr", "fused_tpr", "innate_fpr", "fused_fpr"]:
                    agg[k].append(r[k])
                if r["first_detection_step"] is not None:
                    agg["first_detect"].append(r["first_detection_step"])

        evasion_results[label] = {
            k: float(np.mean(v)) if v else 0.0 for k, v in agg.items()
        }
        print(f"  [{label:>15}]  "
              f"Innate={evasion_results[label]['innate_tpr']:.3f}  "
              f"Memory={evasion_results[label]['memory_tpr']:.3f}  "
              f"Fused={evasion_results[label]['fused_tpr']:.3f}  "
              f"FPR={evasion_results[label]['fused_fpr']:.3f}")

    # ------------------------------------------------------------------
    # 3. Print evasion matrix
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("EVASION MATRIX — The Twist (Beat 3)")
    print("  Innate=all steps  Memory=all steps  Fused=all steps")
    print("=" * 65)
    print(f"  {'Attack Type':<18} {'Innate':>8} {'Memory':>8} {'Fused':>8} {'FPR':>8}")
    print("  " + "-" * 44)
    for lbl, r in evasion_results.items():
        print(f"  {lbl:<18} {r['innate_tpr']:>8.3f} {r['memory_tpr']:>8.3f} "
              f"{r['fused_tpr']:>8.3f} {r['fused_fpr']:>8.3f}")
    print("=" * 65)

    # Analysis
    obv = evasion_results.get("obvious", {})
    sph = evasion_results.get("sophisticated", {})
    inn_drop  = obv.get("innate_tpr", 0) - sph.get("innate_tpr", 0)
    mem_comp  = sph.get("memory_tpr", 0)
    fus_soph  = sph.get("fused_tpr", 0)
    fpr_ratio = obv.get("innate_fpr", 0.01) / max(sph.get("fused_fpr", 0.01), 1e-6)

    print(f"\n  Innate drop (obvious→sophisticated):  -{inn_drop:.3f}")
    print(f"  Memory compensates (sophisticated):  +{mem_comp:.3f}")
    print(f"  Fusion catches sophisticated:         {fus_soph:.3f}")

    inn_ok = "PASS" if inn_drop  > 0.20 else "NOTE"
    mem_ok = "PASS" if mem_comp  > 0.40 else "NOTE"
    fus_ok = "PASS" if fus_soph  > 0.60 else "NOTE"
    print(f"\n  [{inn_ok}] Sophisticated evades Innate (drop > 0.20)")
    print(f"  [{mem_ok}] Memory compensates for sophisticated (> 0.40)")
    print(f"  [{fus_ok}] Fusion catches sophisticated (> 0.60)")

    # Save
    (RESULTS / "evasion_matrix.json").write_text(
        json.dumps(evasion_results, indent=2)
    )
    print(f"\n  Saved: {RESULTS}/evasion_matrix.json")

    # ------------------------------------------------------------------
    # 4. Detection speed (< 5 steps for obvious, < 20 for sophisticated)
    # ------------------------------------------------------------------
    print("\n[Step 3] Detection speed check...")
    fast_obv = obv.get("first_detect", 999)
    fast_sph = sph.get("first_detect", 999)
    print(f"  Obvious attack first detected at step:       {fast_obv:.1f}")
    print(f"  Sophisticated attack first detected at step: {fast_sph:.1f}")
    print(f"  [{'PASS' if fast_obv < 5  else 'NOTE'}] Obvious: < 5 steps (actual {fast_obv:.1f})")
    print(f"  [{'PASS' if fast_sph < 20 else 'NOTE'}] Sophisticated: < 20 steps (actual {fast_sph:.1f})")

    # ------------------------------------------------------------------
    # 5. Demo export
    # ------------------------------------------------------------------
    if args.demo:
        print("\n[Step 4] Exporting demo episode...")
        from scripts.export_demo_cyber import export_demo
        export_demo(
            innate=innate,
            memory=memory,
            tolerance=tolerance,
            learned=learned,
            output_path=RESULTS / "demo_episode.json",
        )
        # Copy to frontend
        import shutil
        dst = Path("frontend/public/demo_episode.json")
        if dst.parent.exists():
            shutil.copy(RESULTS / "demo_episode.json", dst)
            print(f"  Copied to {dst}")

    print("\n" + "=" * 65)
    print("RUN COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
