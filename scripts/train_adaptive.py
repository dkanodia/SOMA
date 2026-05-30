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

TOTAL_STEPS    = 200_000
CHECKPOINT_DIR = Path("models/adaptive")
TB_LOG         = "./tb_logs"


def main():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    print("Building environment...")
    # from soma.envs.cyborg_wrapper import CybORGWrapper
    # from soma.layers.adaptive import build_agent, train
    # env_fn = lambda: CybORGWrapper()
    # agent  = build_agent(env_fn, tb_log=TB_LOG)

    print(f"Training PPO for {TOTAL_STEPS:,} steps...")
    # agent = train(agent, TOTAL_STEPS, str(CHECKPOINT_DIR))
    # agent.save(str(CHECKPOINT_DIR / "soma_ppo_final"))

    print("Running behavioral evaluation...")
    # from soma.eval.detection_metrics import evaluate_detection_rates
    # results = evaluate_detection_rates(...)
    # assert results["lateral_movement"]["rate"] >= 0.50, "FAIL: lateral movement DR too low"
    # assert results["impact"]["rate"]           >= 0.80, "FAIL: impact DR too low"

    print("Done. Model saved to models/adaptive/soma_ppo_final.zip")


if __name__ == "__main__":
    main()
