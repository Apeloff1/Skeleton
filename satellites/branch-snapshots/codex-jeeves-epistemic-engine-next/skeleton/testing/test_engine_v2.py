"""Tests for the high-intricacy engine: predict, control, engine v2."""

from __future__ import annotations

import unittest


class TestSensorFusion(unittest.TestCase):
    def test_outlier_rejection(self):
        from skeleton.overseer.predict import SensorFusion
        fusion = SensorFusion()
        for _ in range(10):
            fusion.observe("cpu", 0.5)
        ch = fusion.observe("cpu", 50.0)  # wild outlier
        self.assertLess(ch.value, 1.0)

    def test_confidence_drops_with_variance(self):
        from skeleton.overseer.predict import SensorFusion
        fusion = SensorFusion()
        for v in (0.1, 0.9, 0.1, 0.9, 0.1, 0.9):
            ch = fusion.observe("x", v)
        noisy = ch.confidence
        fusion2 = SensorFusion()
        for v in (0.5, 0.5, 0.5, 0.5, 0.5):
            ch2 = fusion2.observe("y", v)
        self.assertGreater(ch2.confidence, noisy)


class TestTrendForecaster(unittest.TestCase):
    def test_forecast_tracks_trend(self):
        from skeleton.overseer.predict import TrendForecaster
        fc = TrendForecaster()
        for i in range(10):
            fc.observe("thermal", 60.0 + i)  # rising 1/step
        out = fc.forecast("thermal", steps=5)
        self.assertGreater(out.point, 69.0)
        self.assertGreater(out.trend_per_step, 0)

    def test_breach_prediction(self):
        from skeleton.overseer.predict import TrendForecaster
        fc = TrendForecaster()
        for i in range(10):
            fc.observe("memory", 0.5 + i * 0.04)  # rising toward 0.9
        out = fc.forecast("memory", steps=20, threshold=0.9)
        self.assertIsNotNone(out.crosses_threshold_at)

    def test_no_breach_when_flat(self):
        from skeleton.overseer.predict import TrendForecaster
        fc = TrendForecaster()
        for _ in range(10):
            fc.observe("x", 0.5)
        out = fc.forecast("x", steps=10, threshold=0.9)
        self.assertIsNone(out.crosses_threshold_at)


class TestWorkloadProfiler(unittest.TestCase):
    def test_regimes_classify_with_hysteresis(self):
        from skeleton.overseer.predict import WorkloadProfiler, WorkloadRegime
        prof = WorkloadProfiler()
        for _ in range(5):
            p = prof.observe(0.02, 0.0)
        self.assertEqual(p.regime, WorkloadRegime.IDLE)
        for _ in range(6):
            p = prof.observe(0.85, 0.1)
        self.assertIn(p.regime, (WorkloadRegime.BATCH, WorkloadRegime.SUSTAINED))
        self.assertGreaterEqual(p.dwell_ticks, 1)

    def test_burst_detection(self):
        from skeleton.overseer.predict import WorkloadProfiler, WorkloadRegime
        prof = WorkloadProfiler()
        for v in (0.1, 0.7, 0.05, 0.65, 0.1, 0.6, 0.05, 0.7, 0.1, 0.65):
            p = prof.observe(v, 0.2)
        self.assertEqual(p.regime, WorkloadRegime.BURST)


class TestWearModel(unittest.TestCase):
    def test_wear_accumulates(self):
        from skeleton.overseer.predict import WearModel
        import time as _t
        wear = WearModel()
        wear.observe(85.0, 0.2)
        _t.sleep(0.01)
        wear.observe(85.0, 0.2)
        report = wear.report()
        self.assertGreater(report.throttle_duty, 0.9)
        self.assertEqual(report.deep_throttle_events, 2)
        self.assertGreater(report.estimated_wear_index, 0)


class TestPIDRegulator(unittest.TestCase):
    def test_backs_off_over_setpoint(self):
        from skeleton.overseer.control import PIDRegulator
        pid = PIDRegulator("cpu", setpoint=0.7)
        out = pid.update(0.95)
        self.assertLess(out, 1.0)
        self.assertGreaterEqual(out, 0.05)

    def test_full_speed_under_setpoint(self):
        from skeleton.overseer.control import PIDRegulator
        pid = PIDRegulator("cpu", setpoint=0.7)
        out = pid.update(0.3)
        self.assertEqual(out, 1.0)

    def test_integral_anti_windup(self):
        from skeleton.overseer.control import PIDRegulator
        pid = PIDRegulator("cpu", setpoint=0.7)
        for _ in range(100):
            pid.update(1.0)
        self.assertLessEqual(pid._integral, 0.5)


class TestQoSArbiter(unittest.TestCase):
    def test_deferrable_sheds_first(self):
        from skeleton.overseer.control import QoSArbiter, QoSTier
        arbiter = QoSArbiter()
        allocs = {a.tier: a for a in arbiter.arbitrate(0.7)}
        self.assertFalse(allocs[QoSTier.DEFERRABLE].allowed)
        self.assertTrue(allocs[QoSTier.CRITICAL].allowed)

    def test_shares_sum_to_one(self):
        from skeleton.overseer.control import QoSArbiter
        arbiter = QoSArbiter()
        total = sum(a.share for a in arbiter.arbitrate(0.4))
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_critical_never_sheds(self):
        from skeleton.overseer.control import QoSArbiter, QoSTier
        arbiter = QoSArbiter()
        for pressure in (0.5, 0.8, 0.95, 0.99):
            allocs = {a.tier: a for a in arbiter.arbitrate(pressure)}
            self.assertTrue(allocs[QoSTier.CRITICAL].allowed)


class TestControlCore(unittest.TestCase):
    def _workload(self, regime):
        return type("W", (), {"regime": regime})()

    def test_fast_tick_produces_decision(self):
        from skeleton.overseer.control import ControlCore
        from skeleton.overseer.predict import WorkloadRegime
        core = ControlCore()
        decision = core.fast_tick(
            {"cpu": 0.5, "memory": 0.5, "thermal": 55.0, "battery": 1.0, "io": 0.05},
            self._workload(WorkloadRegime.INTERACTIVE),
        )
        self.assertGreaterEqual(decision.aggregate, 0.05)
        self.assertLessEqual(decision.aggregate, 1.0)
        self.assertEqual(len(decision.allocations), 4)

    def test_slow_loop_pre_throttles_on_forecast(self):
        from skeleton.overseer.control import ControlCore
        from skeleton.overseer.predict import WorkloadRegime
        core = ControlCore()
        forecast = type("F", (), {"crosses_threshold_at": 5})()
        for _ in range(5):  # trigger slow loop
            decision = core.fast_tick(
                {"cpu": 0.5, "memory": 0.5, "thermal": 72.0, "battery": 1.0, "io": 0.05},
                self._workload(WorkloadRegime.SUSTAINED),
                forecasts={"thermal": forecast},
            )
        self.assertGreater(len(decision.anticipatory), 0)
        self.assertLess(core._setpoints["thermal"], 68.0)

    def test_regime_adaptive_gains(self):
        from skeleton.overseer.control import ControlCore, REGIME_GAINS
        from skeleton.overseer.predict import WorkloadRegime
        core = ControlCore()
        core.fast_tick({"cpu": 0.5}, self._workload(WorkloadRegime.BURST))
        burst_kp = core._regulators["cpu"].gains.kp
        core.fast_tick({"cpu": 0.5}, self._workload(WorkloadRegime.IDLE))
        idle_kp = core._regulators["cpu"].gains.kp
        self.assertGreater(burst_kp, idle_kp)


class TestEngineV2(unittest.TestCase):
    def test_tick_produces_full_telemetry(self):
        from skeleton.overseer.engine_v2 import OverseerEngineV2
        engine = OverseerEngineV2()
        tick = engine.tick()
        self.assertIn("decision", tick.to_dict())
        self.assertIn("fused", tick.to_dict())
        self.assertIn("forecasts", tick.to_dict())
        self.assertIn("wear", tick.to_dict())
        self.assertIn("budget", tick.to_dict())

    def test_enforcer_applies_controlled_budget(self):
        from skeleton.overseer.engine_v2 import OverseerEngineV2
        engine = OverseerEngineV2()
        applied = []
        engine.bind("probe_consumer", lambda b: applied.append(b.queue_size))
        engine.tick()
        self.assertEqual(len(applied), 1)

    def test_tier_share_surface(self):
        from skeleton.overseer.engine_v2 import OverseerEngineV2
        from skeleton.overseer.control import QoSTier
        engine = OverseerEngineV2()
        engine.tick()
        share = engine.tier_share(QoSTier.CRITICAL)
        self.assertGreater(share, 0.0)

    def test_status_shape(self):
        from skeleton.overseer.engine_v2 import OverseerEngineV2
        engine = OverseerEngineV2()
        engine.tick()
        status = engine.status()
        for key in ("device", "control", "wear", "last_tick", "consumers"):
            self.assertIn(key, status)

    def test_history_bounded(self):
        from skeleton.overseer.engine_v2 import OverseerEngineV2
        engine = OverseerEngineV2()
        for _ in range(70):
            engine.tick()
        self.assertEqual(len(engine._history), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
