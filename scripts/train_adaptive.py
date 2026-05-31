"""
scripts/train_adaptive.py
==========================
Train Layer 2 PPO defender on CAGE 2.

Steps
-----
1. Build CybORGWrapper
2. Train PPO for 200k steps with reward-hacking guard
3. Save checkpoint every 50k steps
4. Run behavioral evaluation (detection rates per attack chain step)
5. Fail loudly if lateral movement detection < 0.50

Expected runtime: ~45 minutes on laptop GPU

Usage
-----
  python scripts/train_adaptive.py              # fresh 200k-step run
  python scripts/train_adaptive.py --resume     # resume from 100k checkpoint
"""

import argparse
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import CheckpointCallback

from soma.envs.cyborg_wrapper import CybORGWrapper
from soma.layers.adaptive import build_agent, train, evaluate_action_distribution
from soma.layers.innate import InnateImmunityLayer
from soma.eval.detection_metrics import evaluate_detection_rates

TOTAL_STEPS    = 200_000
CHECKPOINT_DIR = Path("models/adaptive")
INNATE_DIR     = Path("models/innate")
RESULTS_DIR    = Path("results/fpr_calibration")
TB_LOG         = "./tb_logs"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume training from models/adaptive/soma_ppo_100000_steps.zip",
    )
    args = parser.parse_args()

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    env_fn = lambda: CybORGWrapper(include_red=True)

    if args.resume:
        checkpoint_path = CHECKPOINT_DIR / "soma_ppo_100000_steps.zip"
        if not checkpoint_path.exists():
            raise FileNotFoundError(
                f"Checkpoint not found: {checkpoint_path}\n"
                "Run without --resume to start from scratch."
            )
        print(f"[train] Resuming from {checkpoint_path} (steps 100k → 200k)")
        env = DummyVecEnv([env_fn])
        agent = PPO.load(str(checkpoint_path), env=env)
        checkpoint_cb = CheckpointCallback(
            save_freq=50_000,
            save_path=str(CHECKPOINT_DIR),
            name_prefix="soma_ppo",
        )
        # reset_num_timesteps=False preserves LR scheduler and step counter
        agent.learn(
            total_timesteps=100_000,
            callback=checkpoint_cb,
            reset_num_timesteps=False,
        )
    else:
        print(f"[train] Starting fresh training ({TOTAL_STEPS:,} steps)")
        agent = build_agent(env_fn, tb_log=TB_LOG)
        agent = train(agent, TOTAL_STEPS, str(CHECKPOINT_DIR))

    agent.save(str(CHECKPOINT_DIR / "soma_ppo_final"))
    print("Model saved to models/adaptive/soma_ppo_final.zip")

    print("\nAction distribution sanity check...")
    evaluate_action_distribution(agent, env_fn)

    print("\nRunning behavioral evaluation (100 episodes)...")
    innate_path   = INNATE_DIR / "isolation_forest.joblib"
    baseline_path = INNATE_DIR / "baseline.joblib"

    if innate_path.exists():
        innate = InnateImmunityLayer.load(innate_path)
        print(f"Loaded innate model from {innate_path}")
    elif baseline_path.exists():
        print(f"[WARN] isolation_forest.joblib not found, using baseline.joblib")
        innate = InnateImmunityLayer.load(baseline_path)
    else:
        raise FileNotFoundError(
            f"Neither {innate_path} nor {baseline_path} found — run train_innate.py first"
        )

    layer1_fn = innate.is_anomalous

    def predict_fn(obs):
        action, _ = agent.predict(obs, deterministic=True)
        return int(action)

    results = evaluate_detection_rates(
        predict_fn=predict_fn,
        env_fn=env_fn,
        layer1_fn=layer1_fn,
        n_episodes=100,
    )

    lm_rate     = results["lateral_movement"]["rate"]
    impact_rate = results["impact"]["rate"]

    summary = (
        f"lateral_movement_dr={lm_rate:.3f}\n"
        f"impact_dr={impact_rate:.3f}\n"
        f"lateral_movement_pass={'yes' if lm_rate >= 0.50 else 'no'}\n"
        f"impact_pass={'yes' if impact_rate >= 0.80 else 'no'}\n"
    )
    (RESULTS_DIR / "layer2_eval.txt").write_text(summary)
    print(f"\nResults written to results/fpr_calibration/layer2_eval.txt")

    if lm_rate < 0.30:
        print(
            "\n[FAIL] Lateral movement DR critically low. "
            "Increase early-detection bonus from +8 to +12 in cyborg_wrapper.py "
            "or add a -15 penalty for impact completion."
        )
        raise AssertionError(f"lateral_movement DR={lm_rate:.3f} < 0.30 — retune reward")

    assert lm_rate    >= 0.50, f"[FAIL] lateral_movement DR={lm_rate:.3f} < 0.50"
    assert impact_rate >= 0.80, f"[FAIL] impact DR={impact_rate:.3f} < 0.80"
    print("\nAll Layer 2 checks passed.")


if __name__ == "__main__":
    main()
