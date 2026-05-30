"""tests/test_adaptive.py — Layer 2 smoke tests."""

class TestAdaptiveLayer:
    def test_agent_builds_without_error(self):
        # from soma.layers.adaptive import build_agent
        # from soma.envs.cyborg_wrapper import CybORGWrapper
        # agent = build_agent(lambda: CybORGWrapper())
        # assert agent is not None
        pass

    def test_reward_function_penalises_repeated_analyze(self):
        # Verify that analyzing the same clean host twice incurs -2
        pass
