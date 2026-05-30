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


def verify_supply_chain():
    """Verify USASpending API is reachable and supply chain ingest imports work."""
    try:
        import requests
        resp = requests.post(
            "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            json={
                "filters": {
                    "agencies": [{"type": "funding", "tier": "toptier",
                                  "name": "Department of Defense"}],
                    "award_type_codes": ["A"],
                    "time_period": [{"start_date": "2023-01-01",
                                     "end_date": "2023-03-01"}],
                },
                "fields": ["Award ID", "Award Amount", "Number of Offers Received"],
                "limit": 1,
            },
            timeout=15,
        )
        resp.raise_for_status()
        n = len(resp.json().get("results", []))
        print(f"USASpending API OK — returned {n} record(s)")

        from soma.envs.supply_chain_ingest import build_feature_vector, PARTS_PSC_CODES
        from soma.layers.innate import InnateSupplyChainDetector, FEATURE_COLS
        print(f"Supply chain imports OK — {len(FEATURE_COLS)} features, "
              f"{len(PARTS_PSC_CODES)} PSC codes")
        return True
    except Exception as e:
        print(f"Supply chain check FAILED: {e}")
        return False


if __name__ == "__main__":
    results = [verify_torch(), verify_sb3(), verify_cyborg(), verify_supply_chain()]
    if all(results):
        print("\nAll checks passed. Ready to train.")
    else:
        print("\nSome checks failed. Fix above before running training scripts.")
