"""
scripts/verify_env.py
======================
Verify that CybORG is installed and the environment runs correctly.
Run this before anything else.
"""

def verify_cyborg():
    try:
        from CybORG import CybORG
        from CybORG.Agents import B_lineAgent
        import inspect
        path = str(inspect.getfile(CybORG))
        scenario = path[:-7] + "/Shared/Scenarios/Scenario1b.yaml"
        env = CybORG(scenario, "sim", agents={"Red": B_lineAgent()})
        obs, _, _, _ = env.step(action="Monitor", agent="Blue")
        assert isinstance(obs, dict), "Observation is not a dict"
        print("CybORG OK — observation keys:", list(obs.keys())[:5])
        return True
    except ImportError:
        print("CybORG NOT FOUND. Install with:")
        print("  git clone https://github.com/cage-challenge/cage-challenge-2")
        print("  cd cage-challenge-2 && pip install -e .")
        return False


def verify_sb3():
    try:
        from stable_baselines3 import PPO
        print("Stable Baselines3 OK")
        return True
    except ImportError:
        print("SB3 NOT FOUND: pip install stable-baselines3")
        return False


def verify_torch():
    try:
        import torch
        print(f"PyTorch OK — version {torch.__version__}, CUDA: {torch.cuda.is_available()}")
        return True
    except ImportError:
        print("PyTorch NOT FOUND: pip install torch")
        return False


def verify_sklearn():
    try:
        from sklearn.ensemble import IsolationForest
        from soma.layers.innate import InnateImmunityLayer
        print("scikit-learn + InnateImmunityLayer OK")
        return True
    except ImportError as e:
        print(f"sklearn NOT FOUND: pip install scikit-learn  ({e})")
        return False


if __name__ == "__main__":
    results = [verify_torch(), verify_sb3(), verify_cyborg(), verify_sklearn()]
    if all(results):
        print("\nAll checks passed. Ready to train.")
    else:
        print("\nSome checks failed. Fix above before running training scripts.")
