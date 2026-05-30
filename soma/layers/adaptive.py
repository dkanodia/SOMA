"""
soma/layers/adaptive.py
========================
Layer 2 — Adaptive Immunity: PPO defender agent on CAGE 2.

Uses Stable Baselines3 PPO. Trained offline against B_lineAgent (scripted,
deterministic). The trained policy is FROZEN at deployment — this is NOT
online adaptive. Stated explicitly in the pitch.

FPR budget: 1% (consistent with Layer 1 budget).

Success criteria (not cumulative reward — that is training evidence only):
  - Lateral movement detection rate >= 0.50
  - Impact stage detection rate      >= 0.80
  - FPR on clean episodes            <= 0.01
See soma/eval/detection_metrics.py for evaluation.

Reward hacking guard:
  Repeated Analyze on recently-analyzed clean hosts receives a -2 penalty.
  Without this, the agent learns to spam Analyze for +8 rewards without
  genuine defensive value.
"""

from pathlib import Path
from typing import Optional

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback


DEFAULT_HYPERPARAMS = dict(
    n_steps       = 2048,
    batch_size    = 64,
    n_epochs      = 10,
    learning_rate = 3e-4,
    ent_coef      = 0.01,   # encourage exploration — reduce if policy collapses
    clip_range    = 0.2,
    gae_lambda    = 0.95,
    gamma         = 0.99,
)

DEFAULT_TOTAL_STEPS = 200_000


def build_agent(env_fn, hyperparams: Optional[dict] = None, tb_log: str = "./tb_logs") -> PPO:
    """
    Construct a PPO agent on the wrapped CybORG environment.

    Parameters
    ----------
    env_fn : callable
        Zero-argument factory returning a CybORGWrapper instance.
    hyperparams : dict, optional
        Override DEFAULT_HYPERPARAMS.
    tb_log : str
        TensorBoard log directory.

    Returns
    -------
    PPO agent (untrained).
    """
    hp  = {**DEFAULT_HYPERPARAMS, **(hyperparams or {})}
    env = DummyVecEnv([env_fn])
    return PPO("MlpPolicy", env, verbose=1, tensorboard_log=tb_log, **hp)


def train(
    agent: PPO,
    total_timesteps: int  = DEFAULT_TOTAL_STEPS,
    checkpoint_dir: str   = "./models/adaptive",
    checkpoint_freq: int  = 50_000,
) -> PPO:
    """
    Train the PPO agent with periodic checkpointing.

    Convergence check:
      If reward does not improve after 50k steps, increase ent_coef to 0.05
      or reduce learning_rate to 1e-4. Do not continue past 300k steps without
      evidence of lateral-movement detection improvement.

    Reward hacking check (inspect at 50k steps):
      Print action distribution — if Analyze actions > 70% of total and
      reward is improving, check whether detected anomalies correspond to
      genuine B_lineAgent actions or noise.
    """
    callbacks = [
        CheckpointCallback(
            save_freq=checkpoint_freq,
            save_path=checkpoint_dir,
            name_prefix="soma_ppo",
        )
    ]
    agent.learn(total_timesteps=total_timesteps, callback=callbacks)
    return agent


def load(path: str) -> PPO:
    """Load a saved PPO agent."""
    return PPO.load(path)


def evaluate_action_distribution(agent: PPO, env_fn, n_episodes: int = 20) -> dict:
    """
    Sanity check: inspect what actions the trained agent actually takes.
    If Analyze fraction > 0.70 and reward looks good, check for reward hacking.
    """
    from soma.envs.cyborg_wrapper import BLUE_ACTIONS

    category_counts: dict = {"Monitor": 0, "Analyze": 0, "Remove": 0, "Restore": 0}
    total = 0

    for _ in range(n_episodes):
        env  = env_fn()
        obs, _ = env.reset()
        for _ in range(200):
            action, _ = agent.predict(obs, deterministic=True)
            obs, _, done, _, _ = env.step(int(action))
            name = BLUE_ACTIONS[int(action)]
            for cat in category_counts:
                if name.startswith(cat):
                    category_counts[cat] += 1
                    break
            total += 1
            if done:
                break

    distribution = {cat: count / max(total, 1) for cat, count in category_counts.items()}
    analyze_frac = distribution.get("Analyze", 0.0)
    if analyze_frac > 0.70:
        print(f"[WARN] Analyze fraction = {analyze_frac:.2f} > 0.70 — possible reward hacking")
    for cat, frac in distribution.items():
        print(f"  {cat}: {frac:.3f}")
    return distribution
