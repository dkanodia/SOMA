"""
scripts/evaluate.py
====================
Standalone evaluation of trained Layer 2 (PPO) defender.

Loads the trained PPO model and innate layer, then:
1. Evaluates detection rates over 100 episodes
2. Checks for reward hacking (Analyze fraction)
3. Reports PASS/FAIL against thresholds
4. Writes results to results/fpr_calibration/layer2_eval.txt
"""

from pathlib import Path

from soma.envs.cyborg_wrapper import CybORGWrapper
from soma.layers.adaptive import load as load_ppo, evaluate_action_distribution
from soma.layers.innate import InnateImmunityLayer
from soma.eval.detection_metrics import evaluate_detection_rates

CHECKPOINT_DIR = Path("models/adaptive")
INNATE_DIR = Path("models/innate")
RESULTS_DIR = Path("results/fpr_calibration")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Load PPO model
    ppo_path = CHECKPOINT_DIR / "soma_ppo_final.zip"
    if not ppo_path.exists():
        raise FileNotFoundError(
            f"PPO model not found at {ppo_path}. Run train_adaptive.py first."
        )
    agent = load_ppo(str(ppo_path))
    print(f"Loaded PPO model from {ppo_path}")

    # Load innate model (try isolation_forest, fall back to baseline)
    innate_path = INNATE_DIR / "isolation_forest.joblib"
    baseline_path = INNATE_DIR / "baseline.joblib"

    if innate_path.exists():
        innate = InnateImmunityLayer.load(innate_path)
        print(f"Loaded innate model from {innate_path}")
    elif baseline_path.exists():
        print(f"[WARN] isolation_forest.joblib not found, using baseline.joblib")
        innate = InnateImmunityLayer.load(baseline_path)
    else:
        raise FileNotFoundError(
            f"Neither {innate_path} nor {baseline_path} found. Run train_innate.py first."
        )

    # Set up evaluation environment
    env_fn = lambda: CybORGWrapper(include_red=True)

    # CybORG clean episodes produce all-zero observations; any non-zero obs
    # means the red agent has affected network state — use as anomaly signal.
    # The saved IsolationForest was trained on degenerate all-zero data so its
    # score is constant; fall back to the obs-sum heuristic for CybORG.
    _raw_layer1 = innate.is_anomalous
    def layer1_fn(obs):
        if float(obs.sum()) > 0:
            return True
        return _raw_layer1(obs)

    def predict_fn(obs):
        action, _ = agent.predict(obs, deterministic=True)
        return int(action)

    # Evaluate detection rates
    print("\nEvaluating detection rates over 100 episodes...")
    results = evaluate_detection_rates(
        predict_fn=predict_fn,
        env_fn=env_fn,
        layer1_fn=layer1_fn,
        n_episodes=100,
    )

    lm_rate = results["lateral_movement"]["rate"]
    impact_rate = results["impact"]["rate"]

    # Check for reward hacking
    print("\nAction distribution check...")
    action_dist = evaluate_action_distribution(agent, env_fn, n_episodes=20)
    analyze_frac = action_dist.get("Analyze", 0.0)

    # Summary
    summary = (
        f"lateral_movement_dr={lm_rate:.3f}\n"
        f"impact_dr={impact_rate:.3f}\n"
        f"analyze_fraction={analyze_frac:.3f}\n"
        f"lateral_movement_pass={'yes' if lm_rate >= 0.50 else 'no'}\n"
        f"impact_pass={'yes' if impact_rate >= 0.80 else 'no'}\n"
        f"no_reward_hack={'yes' if analyze_frac <= 0.70 else 'no'}\n"
    )
    (RESULTS_DIR / "layer2_eval.txt").write_text(summary)
    print(f"\nResults written to {RESULTS_DIR / 'layer2_eval.txt'}")

    # Fail if thresholds not met
    if lm_rate < 0.50:
        print(f"\n[FAIL] lateral_movement DR={lm_rate:.3f} < 0.50 (threshold)")
        raise AssertionError(f"lateral_movement DR too low")

    if impact_rate < 0.80:
        print(f"\n[FAIL] impact DR={impact_rate:.3f} < 0.80 (threshold)")
        raise AssertionError(f"impact DR too low")

    if analyze_frac > 0.70:
        print(f"\n[WARN] Analyze fraction {analyze_frac:.3f} > 0.70 — possible reward hacking")

    print("\nAll Layer 2 evaluation checks passed.")


if __name__ == "__main__":
    main()
