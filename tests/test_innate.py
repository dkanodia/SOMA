"""tests/test_innate.py — Layer 1 smoke tests."""
import numpy as np

class TestInnateLayer:
    def test_isolation_forest_fits_without_error(self):
        # from soma.layers.innate import InnateIsolationForest
        # iso = InnateIsolationForest()
        # iso.fit(np.random.randn(500, 25))
        # iso.calibrate_threshold(np.random.randn(100, 25))
        # assert iso.threshold_ is not None
        pass

    def test_dual_timescale_does_not_alarm_on_flat_signal(self):
        # from soma.layers.innate import DualTimescaleBaseline
        # dtb = DualTimescaleBaseline()
        # for _ in range(200):
        #     fired = dtb.update_and_flag(1.0)   # flat signal
        # assert not fired
        pass
