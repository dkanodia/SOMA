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
"""

from pathlib import Path

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
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Building environment...")
    env_fn = lambda: CybORGWrapper(include_red=True)

    print(f"Training PPO for {TOTAL_STEPS:,} steps...")
    agent = build_agent(env_fn, tb_log=TB_LOG)
    agent = train(agent, TOTAL_STEPS, str(CHECKPOINT_DIR))
    agent.save(str(CHECKPOINT_DIR / "soma_ppo_final"))
    print("Model saved to models/adaptive/soma_ppo_final.zip")

    print("\nAction distribution sanity check...")
    evaluate_action_distribution(agent, env_fn)

    print("\nRunning behavioral evaluation (100 episodes)...")
    innate_path = INNATE_DIR / "isolation_forest.joblib"
    if not innate_path.exists():
        raise FileNotFoundError(
            f"{innate_path} not found — run train_innate.py first"
        )
    innate    = InnateImmunityLayer.load(innate_path)
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

    assert lm_rate  >= 0.50, f"[FAIL] lateral_movement DR={lm_rate:.3f} < 0.50"
    assert impact_rate >= 0.80, f"[FAIL] impact DR={impact_rate:.3f} < 0.80"
    print("\nAll Layer 2 checks passed.")


if __name__ == "__main__":
    main()
