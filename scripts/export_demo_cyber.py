"""
scripts/export_demo_cyber.py
==============================
Export a static demo episode for the frontend dashboard.

Runs one representative episode with the B_line-like attack sequence
and records per-step state for all 5 immune layers + explainability
+ causal kill chain + attack gallery snapshots.

Output JSON format:
  {
    "meta": {
      episode_length, n_hosts, n_features, stealth, attack_start,
      host_names, innate_threshold, memory_threshold,
      evasion_matrix: {obvious: {...}, sophisticated: {...}},
      gallery_initial: [{attack_type, n_steps, embedding}]
    },
    "steps": [
      {
        "step": t,
        "phase": "initial_access" | "lateral_movement" | ... | "clean",
        "obs": [30 floats],
        "host_states": {host: {activity, compromised, sessions, ...}},
        "is_attack": bool,
        "anomaly_score": float,             # Layer 1
        "innate_fired": bool,
        "host_innate_scores": {host: float},
        "drift_scores": {host: float},      # Layer 4
        "memory_fired": bool,
        "tolerance_suppressed": [host],     # Layer 3
        "tolerance_breached": [host],
        "learned_attack_conf": float,       # Layer 5
        "learned_attack_type": str,
        "incidents": [                      # Fusion
          {host, score, layers_fired, explanation, confidence, attack_type}
        ],
        "top_threat": {host, score} | null,
        "kill_chain": [                     # Causal tracer
          {source, target, phase, confidence, t_source, t_target}
        ],
        "explanation": {                    # Per-layer WHY
          innate: {layer, top_hosts, top_features, reason},
          memory: {...}, tolerance: {...}, learned_attacks: {...}
        },
        "gallery_snapshot": [{attack_type, n_steps, embedding}] | null,
      }
    ]
  }

Usage:
  python -m scripts.export_demo_cyber
  python -m scripts.export_demo_cyber --stealth 0.9 --n-steps 60
"""

import argparse
import json
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Core export function
# ---------------------------------------------------------------------------

def export_demo(
    innate,
    memory,
    tolerance,
    learned,
    stealth:      float = 0.0,
    n_steps:      int   = 60,
    attack_start: int   = 10,
    seed:         int   = 42,
    output_path:  Path  = Path("results/cyber/demo_episode.json"),
    evasion_matrix: dict = None,
) -> dict:
    from soma.envs.synthetic_network_gen import (
        SyntheticNetworkGen, generate_attack_episode,
        HOST_NAMES, FEATURES_PER_HOST,
    )
    from soma.layers.memory       import HostDriftLayer
    from soma.layers.attack_tracer import AttackTracer
    from soma.layers.explainer    import ImmuneExplainer
    from soma.fusion.network_correlator import NetworkImmuneCorrelator

    gen = SyntheticNetworkGen(
        episode_length=n_steps,
        attack_start=attack_start,
        stealth=stealth,
        seed=seed,
    )
    gen.reset()

    ep_mem   = HostDriftLayer(memory_k=10, recent_k=10)
    ep_mem.threshold_ = memory.threshold_
    corr     = NetworkImmuneCorrelator()
    tracer   = AttackTracer()
    explainer = ImmuneExplainer()

    obs_buffer  = []
    steps_data  = []

    for t in range(n_steps):
        obs, is_atk, info = gen.step()
        obs_buffer.append(obs)

        # Per-host states
        host_states = {}
        for i, h in enumerate(HOST_NAMES):
            start = i * FEATURES_PER_HOST
            feat  = obs[start:start + FEATURES_PER_HOST]
            host_states[h] = {
                "activity":    float(feat[0]),
                "compromised": float(feat[1]),
                "sessions":    float(feat[2]),
                "processes":   float(feat[3]),
                "network_pos": float(feat[4]),
            }

        # Layer 1: Innate
        ann_score   = innate.anomaly_score(obs)
        l_inn       = ann_score > innate.threshold_
        host_inn_sc = innate.per_host_scores(obs)

        # Layer 3: Tolerance
        sup = tolerance.suppressed_hosts(obs)
        brh = tolerance.breach_hosts(obs)

        # Layer 4: Memory
        mem_sc = ep_mem.update_and_scores(obs)
        l_mem  = any(s > ep_mem.threshold_ for s in mem_sc.values())

        # Layer 5: Learned attacks
        la_conf, la_type = 0.0, "unknown"
        if len(obs_buffer) >= 3 and learned.gallery_size > 0:
            la_conf, la_type = learned.recognize(
                np.array(obs_buffer[-min(len(obs_buffer), 10):])
            )

        # Fusion
        incidents = corr.update_step(
            obs=obs,
            innate_score=ann_score,
            innate_threshold=innate.threshold_,
            memory_scores=mem_sc,
            memory_threshold=ep_mem.threshold_,
            tolerance_suppressed=sup,
            tolerance_breached=brh,
            learned_attack_conf=la_conf,
            learned_attack_type=la_type,
            innate_host_scores=host_inn_sc,
        )
        top = corr.top_threat()

        # Causal kill chain — update with currently compromised hosts
        compromised_hosts = set(info.get("compromised_hosts", []))
        # Also add hosts flagged by innate above threshold
        if l_inn:
            for h, sc in host_inn_sc.items():
                if sc > innate.threshold_:
                    compromised_hosts.add(h)
        new_kc_edges = tracer.update(t, compromised_hosts)
        kill_chain   = tracer.to_json()

        # Explanation
        explanation = explainer.explain_step(
            obs=obs,
            host_innate_scores=host_inn_sc,
            innate_threshold=float(innate.threshold_),
            drift_scores=mem_sc,
            memory_threshold=float(ep_mem.threshold_ or 1.0),
            tolerance_suppressed=list(sup),
            tolerance_breached=list(brh),
            la_conf=la_conf,
            la_type=la_type,
            gallery_size=learned.gallery_size,
        )

        # Gallery snapshot at attack start and at end
        gallery_snap = None
        if t == attack_start or t == n_steps - 1:
            gallery_snap = learned.gallery_summary()

        steps_data.append({
            "step":    t,
            "phase":   info["phase"],
            "obs":     obs.tolist(),
            "host_states": host_states,
            "is_attack": bool(is_atk),
            "compromised_hosts": list(info.get("compromised_hosts", [])),

            # Layer 1
            "anomaly_score":      float(ann_score),
            "innate_fired":       bool(l_inn),
            "host_innate_scores": {h: float(v) for h, v in host_inn_sc.items()},

            # Layer 4
            "drift_scores":  {h: float(v) for h, v in mem_sc.items()},
            "memory_fired":  bool(l_mem),

            # Layer 3
            "tolerance_suppressed": list(sup),
            "tolerance_breached":   list(brh),

            # Layer 5
            "learned_attack_conf": float(la_conf),
            "learned_attack_type": la_type,

            # Fusion
            "incidents": [
                {
                    "host":         inc.host,
                    "score":        float(inc.score),
                    "layers_fired": inc.layers_fired,
                    "explanation":  inc.explanation,
                    "confidence":   inc.confidence,
                    "attack_type":  inc.attack_type,
                }
                for inc in incidents
            ],
            "top_threat": {"host": top[0], "score": float(top[1])} if top else None,

            # Kill chain (cumulative to this step)
            "kill_chain": kill_chain,

            # Explanation
            "explanation": explanation,

            # Gallery snapshot (only at key steps)
            "gallery_snapshot": gallery_snap,
        })

    episode = {
        "meta": {
            "episode_length":   n_steps,
            "n_hosts":          len(HOST_NAMES),
            "n_features":       FEATURES_PER_HOST,
            "stealth":          stealth,
            "attack_start":     attack_start,
            "host_names":       HOST_NAMES,
            "innate_threshold": float(innate.threshold_),
            "memory_threshold": float(ep_mem.threshold_ or 0.0),
            "evasion_matrix":   evasion_matrix or {},
            "gallery_initial":  learned.gallery_summary(),
        },
        "steps": steps_data,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(episode, indent=2))
    print(f"[Demo] Exported {n_steps}-step episode → {output_path}")

    n_atk = sum(s["is_attack"]    for s in steps_data)
    n_inn = sum(s["innate_fired"] for s in steps_data if s["is_attack"])
    n_mem = sum(s["memory_fired"] for s in steps_data if s["is_attack"])
    n_inc = sum(len(s["incidents"]) > 0 for s in steps_data if s["is_attack"])
    n_kc  = len(steps_data[-1]["kill_chain"]) if steps_data else 0
    print(f"  Attack steps:   {n_atk}/{n_steps}")
    print(f"  Innate detect:  {n_inn}/{n_atk}")
    print(f"  Memory detect:  {n_mem}/{n_atk}")
    print(f"  Fused incidents:{n_inc}/{n_atk}")
    print(f"  Kill-chain edges:{n_kc}")
    print(f"  Gallery size:   {learned.gallery_size}")
    return episode


# ---------------------------------------------------------------------------
# Pre-populate gallery helper
# ---------------------------------------------------------------------------

def _prepopulate_gallery(learned, seed_base: int = 100):
    """
    Train the gallery on representative attack sequences so the
    demo has non-empty gallery from step 0.
    """
    from soma.envs.synthetic_network_gen import generate_attack_episode

    attack_configs = [
        (0.0, "lateral_move_obvious",       ["User0", "Enterprise0"]),
        (0.9, "lateral_move_sophisticated",  ["User1", "Enterprise1"]),
        (0.3, "privilege_escalation",        ["Enterprise0", "Op_Server0"]),
        (0.0, "direct_impact",               ["User0", "Op_Server0"]),
    ]
    for i, (stealth, atype, hosts) in enumerate(attack_configs):
        obs_atk, labels, _ = generate_attack_episode(
            stealth=stealth, n_steps=40, attack_start=5, seed=seed_base + i,
        )
        attack_obs = obs_atk[labels]
        if len(attack_obs) >= 2:
            learned.learn_attack(attack_obs, atype, hosts)


# ---------------------------------------------------------------------------
# Quick evasion matrix (2×4: obvious vs sophisticated, per layer)
# ---------------------------------------------------------------------------

def _compute_evasion_matrix(innate, memory, tolerance, learned, n_episodes=5):
    from soma.envs.synthetic_network_gen import generate_attack_episode
    from soma.layers.memory import HostDriftLayer
    from soma.fusion.network_correlator import NetworkImmuneCorrelator
    import numpy as np

    results = {}
    for stealth, label in [(0.0, "obvious"), (0.9, "sophisticated")]:
        ep_tpr_inn, ep_tpr_mem, ep_tpr_fus = [], [], []
        for ep in range(n_episodes):
            obs_arr, labels, _ = generate_attack_episode(
                stealth=stealth, n_steps=50, attack_start=10, seed=200 + ep,
            )
            ep_mem  = HostDriftLayer(memory_k=10, recent_k=10)
            ep_mem.threshold_ = memory.threshold_
            corr    = NetworkImmuneCorrelator()
            obs_buf = []

            inn_det, mem_det, fus_det, n_atk = 0, 0, 0, 0
            for t, obs in enumerate(obs_arr):
                obs_buf.append(obs)
                ann  = innate.anomaly_score(obs)
                l_in = ann > innate.threshold_
                sup  = tolerance.suppressed_hosts(obs)
                brh  = tolerance.breach_hosts(obs)
                msc  = ep_mem.update_and_scores(obs)
                l_me = any(s > ep_mem.threshold_ for s in msc.values())
                la_conf, la_type = 0.0, "unknown"
                if len(obs_buf) >= 3 and learned.gallery_size > 0:
                    la_conf, la_type = learned.recognize(
                        np.array(obs_buf[-min(len(obs_buf), 10):])
                    )
                incs = corr.update_step(
                    obs=obs, innate_score=ann, innate_threshold=innate.threshold_,
                    memory_scores=msc, memory_threshold=ep_mem.threshold_,
                    tolerance_suppressed=sup, tolerance_breached=brh,
                    learned_attack_conf=la_conf, learned_attack_type=la_type,
                )
                if labels[t]:
                    n_atk += 1
                    if l_in: inn_det += 1
                    if l_me: mem_det += 1
                    if len(incs) > 0: fus_det += 1
            if n_atk:
                ep_tpr_inn.append(inn_det / n_atk)
                ep_tpr_mem.append(mem_det / n_atk)
                ep_tpr_fus.append(fus_det / n_atk)
        results[label] = {
            "innate_tpr":  round(float(np.mean(ep_tpr_inn)), 3),
            "memory_tpr":  round(float(np.mean(ep_tpr_mem)), 3),
            "fusion_tpr":  round(float(np.mean(ep_tpr_fus)), 3),
        }
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export SOMA demo episode")
    parser.add_argument("--stealth",      type=float, default=0.9,
                        help="Attacker stealth 0=obvious 1=sophisticated (default 0.9)")
    parser.add_argument("--n-steps",      type=int,   default=60)
    parser.add_argument("--attack-start", type=int,   default=10)
    parser.add_argument("--seed",         type=int,   default=42)
    parser.add_argument("--out", type=str,
                        default="results/cyber/demo_episode.json")
    parser.add_argument("--no-evasion", action="store_true",
                        help="Skip evasion matrix computation (faster)")
    parser.add_argument("--use-cyborg", action="store_true",
                        help="Use real CybORG observations for model training (requires CybORG install)")
    args = parser.parse_args()

    from soma.layers.innate        import InnateImmunityLayer
    from soma.layers.memory        import HostDriftLayer
    from soma.layers.tolerance     import ImmuneToleranceLayer
    from soma.layers.learned_attacks import LearnedAttackRecognizer

    if args.use_cyborg:
        print("[Demo] Collecting CybORG clean baseline data...")
        from soma.envs.cyborg_wrapper import generate_cyborg_clean_episodes
        X_clean = generate_cyborg_clean_episodes(n_steps=1200, seed=999)
        model_path = Path("models/innate/cyborg_baseline.joblib")
        vae_path   = Path("models/innate/cyborg_vae.joblib")
        print(f"[Demo] CybORG clean data: {X_clean.shape}")
    else:
        print("[Demo] Generating synthetic clean baseline data...")
        from soma.envs.synthetic_network_gen import generate_clean_episodes
        X_clean = generate_clean_episodes(n_steps=1200, seed=999)
        model_path = Path("models/innate/baseline.joblib")
        vae_path   = Path("models/innate/vae.joblib")

    if model_path.exists():
        print("[Demo] Loading saved innate model...")
        innate = InnateImmunityLayer.load(model_path)
    else:
        print("[Demo] Training innate layer...")
        innate = InnateImmunityLayer(fpr_target=0.01)
        innate.fit(X_clean)
        innate.calibrate_threshold(X_clean[-200:])

    print("[Demo] Calibrating memory layer...")
    memory = HostDriftLayer(memory_k=10, recent_k=10, fpr_target=0.05)
    memory.calibrate_threshold(X_clean)

    print("[Demo] Calibrating tolerance layer...")
    tolerance = ImmuneToleranceLayer()
    tolerance.calibrate(X_clean)

    if vae_path.exists():
        print("[Demo] Loading saved VAE...")
        learned = LearnedAttackRecognizer.load(vae_path)
    else:
        print("[Demo] Training VAE...")
        learned = LearnedAttackRecognizer()
        learned.fit(X_clean, epochs=50)

    # Pre-populate gallery with representative attack types
    if learned.gallery_size == 0:
        print("[Demo] Pre-populating attack gallery...")
        _prepopulate_gallery(learned)

    # Evasion matrix
    evasion_matrix = {}
    if not args.no_evasion:
        print("[Demo] Computing evasion matrix...")
        evasion_matrix = _compute_evasion_matrix(innate, memory, tolerance, learned)
        print(f"  obvious:       {evasion_matrix.get('obvious')}")
        print(f"  sophisticated: {evasion_matrix.get('sophisticated')}")

    # Export
    episode = export_demo(
        innate=innate,
        memory=memory,
        tolerance=tolerance,
        learned=learned,
        stealth=args.stealth,
        n_steps=args.n_steps,
        attack_start=args.attack_start,
        seed=args.seed,
        output_path=Path(args.out),
        evasion_matrix=evasion_matrix,
    )

    # Copy to frontend public dir
    frontend_path = Path("frontend/public/demo_episode.json")
    if frontend_path.parent.exists():
        frontend_path.write_text(json.dumps(episode, indent=2))
        print(f"[Demo] Copied → {frontend_path}")


if __name__ == "__main__":
    import json
    main()
