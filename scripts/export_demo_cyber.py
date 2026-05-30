"""
scripts/export_demo_cyber.py
==============================
Export a static demo episode for the frontend dashboard.

Runs one representative episode with the B_line-like attack sequence
and records per-step state for all 5 immune layers.

Output JSON format:
  {
    "meta": {episode_length, n_hosts, n_features, stealth},
    "steps": [
      {
        "step": t,
        "phase": "initial_access" | "lateral_movement" | ... | "clean",
        "obs": [30 floats],
        "host_states": {host: {activity, compromised, sessions, ...}},
        "is_attack": bool,
        "anomaly_score": float,        # Layer 1
        "innate_fired": bool,
        "host_innate_scores": {host: float},
        "drift_scores": {host: float}, # Layer 4
        "memory_fired": bool,
        "tolerance_suppressed": [host],
        "tolerance_breached": [host],
        "learned_attack_conf": float,  # Layer 5
        "learned_attack_type": str,
        "incidents": [                 # Fusion
          {host, score, layers_fired, explanation, confidence}
        ],
        "top_threat": {host, score} | null,
      }
    ]
  }

Usage:
  python -m scripts.export_demo_cyber
  python -m scripts.export_demo_cyber --stealth 0.0 --out results/cyber/demo_episode.json
"""

import argparse
import json
import numpy as np
from pathlib import Path


def export_demo(
    innate,
    memory,
    tolerance,
    learned,
    stealth:     float = 0.0,
    n_steps:     int   = 50,
    attack_start: int  = 10,
    seed:        int   = 42,
    output_path: Path  = Path("results/cyber/demo_episode.json"),
) -> dict:
    from soma.envs.synthetic_network_gen import (
        SyntheticNetworkGen, HOST_NAMES, FEATURES_PER_HOST
    )
    from soma.layers.memory import HostDriftLayer
    from soma.fusion.network_correlator import NetworkImmuneCorrelator

    gen = SyntheticNetworkGen(
        episode_length=n_steps,
        attack_start=attack_start,
        stealth=stealth,
        seed=seed,
    )
    gen.reset()

    ep_mem = HostDriftLayer(memory_k=10, recent_k=10)
    ep_mem.threshold_ = memory.threshold_
    corr = NetworkImmuneCorrelator()

    obs_buffer = []
    steps_data = []

    for t in range(n_steps):
        obs, is_atk, info = gen.step()
        obs_buffer.append(obs)

        # Parse per-host states from obs
        host_states = {}
        for i, h in enumerate(HOST_NAMES):
            start = i * FEATURES_PER_HOST
            feat  = obs[start:start + FEATURES_PER_HOST]
            host_states[h] = {
                "activity":     float(feat[0]),
                "compromised":  float(feat[1]),
                "sessions":     float(feat[2]),
                "processes":    float(feat[3]),
                "network_pos":  float(feat[4]),
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

        steps_data.append({
            "step":          t,
            "phase":         info["phase"],
            "obs":           obs.tolist(),
            "host_states":   host_states,
            "is_attack":     bool(is_atk),
            "compromised_hosts": info.get("compromised_hosts", []),

            # Layer 1
            "anomaly_score":    float(ann_score),
            "innate_fired":     bool(l_inn),
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
                    "host":        inc.host,
                    "score":       float(inc.score),
                    "layers_fired": inc.layers_fired,
                    "explanation": inc.explanation,
                    "confidence":  inc.confidence,
                    "attack_type": inc.attack_type,
                }
                for inc in incidents
            ],
            "top_threat": {"host": top[0], "score": float(top[1])} if top else None,
        })

    episode = {
        "meta": {
            "episode_length": n_steps,
            "n_hosts":        len(HOST_NAMES),
            "n_features":     FEATURES_PER_HOST,
            "stealth":        stealth,
            "attack_start":   attack_start,
            "host_names":     HOST_NAMES,
            "innate_threshold": float(innate.threshold_),
            "memory_threshold": float(ep_mem.threshold_ or 0.0),
        },
        "steps": steps_data,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(episode, indent=2))
    print(f"[Demo] Exported {n_steps}-step episode → {output_path}")

    n_atk    = sum(s["is_attack"]     for s in steps_data)
    n_inn    = sum(s["innate_fired"]  for s in steps_data if s["is_attack"])
    n_mem    = sum(s["memory_fired"]  for s in steps_data if s["is_attack"])
    n_inc    = sum(len(s["incidents"]) > 0 for s in steps_data if s["is_attack"])
    print(f"  Attack steps: {n_atk}/{n_steps}")
    print(f"  Innate detections on attack: {n_inn}/{n_atk}")
    print(f"  Memory detections on attack: {n_mem}/{n_atk}")
    print(f"  Fused incidents on attack:   {n_inc}/{n_atk}")
    return episode


def main():
    parser = argparse.ArgumentParser(description="Export SOMA demo episode")
    parser.add_argument("--stealth",      type=float, default=0.0)
    parser.add_argument("--n-steps",      type=int,   default=50)
    parser.add_argument("--attack-start", type=int,   default=10)
    parser.add_argument("--seed",         type=int,   default=42)
    parser.add_argument("--out",          type=str,   default="results/cyber/demo_episode.json")
    args = parser.parse_args()

    from soma.envs.synthetic_network_gen import generate_clean_episodes
    from soma.layers.innate   import InnateImmunityLayer
    from soma.layers.memory   import HostDriftLayer
    from soma.layers.tolerance import ImmuneToleranceLayer
    from soma.layers.learned_attacks import LearnedAttackRecognizer

    X_clean = generate_clean_episodes(n_steps=1000, seed=999)

    model_path = Path("models/innate/baseline.joblib")
    vae_path   = Path("models/innate/vae.joblib")

    if model_path.exists():
        innate = InnateImmunityLayer.load(model_path)
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
    else:
        learned = LearnedAttackRecognizer()
        learned.fit(X_clean, epochs=50)

    export_demo(
        innate=innate,
        memory=memory,
        tolerance=tolerance,
        learned=learned,
        stealth=args.stealth,
        n_steps=args.n_steps,
        attack_start=args.attack_start,
        seed=args.seed,
        output_path=Path(args.out),
    )


if __name__ == "__main__":
    main()
