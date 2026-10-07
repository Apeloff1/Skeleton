"""Tests for the paramount engine: system ID, MPC, twin, meta-cognition, V3."""

from __future__ import annotations

import unittest


class TestSystemIdentifier(unittest.TestCase):
    def test_invalid_forgetting_and_samples_do_not_poison_model(self):
        from skeleton.overseer.mpc import SystemIdentifier
        for value in (0.0, -1.0, 1.1, float("nan"), float("inf"), True):
            with self.subTest(forgetting=value), self.assertRaises(ValueError):
                SystemIdentifier(forgetting=value)
        sid = SystemIdentifier()
        sid.observe("cpu", 0.5, 0.8, 0.2)
        before = sid.stats()
        for sample in ((float("nan"), 0.8, 0.2), (0.5, float("inf"), 0.2), (0.5, 0.8, True)):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                sid.observe("cpu", *sample)
            self.assertEqual(sid.stats(), before)
        self.assertEqual(sid.observe("cpu", 0.6, 0.8, 0.2).samples, 1)

    def test_covariance_matches_single_observation_information_inverse(self):
        from skeleton.overseer.mpc import SystemIdentifier
        sid = SystemIdentifier(forgetting=1.0)
        sid.observe("cpu", 1.0, 2.0, 2.0)
        sid.observe("cpu", 0.5, 0.0, 0.0)
        # Inverse of 0.01 I + phi phi^T, phi=(1,2,2), via Sherman-Morrison.
        phi = (1.0, 2.0, 2.0)
        covariance = sid._cov["cpu"]
        for i in range(3):
            for j in range(3):
                expected = (100.0 if i == j else 0.0) - 10000.0 * phi[i] * phi[j] / 901.0
                self.assertAlmostEqual(covariance[i][j], expected)
                self.assertAlmostEqual(covariance[i][j], covariance[j][i])

    def test_model_converges_on_stable_dynamics(self):
        from skeleton.overseer.mpc import SystemIdentifier
        sid = SystemIdentifier()
        # True dynamics: x' = 0.8x + 0.2u + 0.0d
        x = 0.5
        for i in range(60):
            sid.observe("cpu", x, 0.8, 0.0)
            x = 0.8 * x + 0.2 * 0.8
        model = sid.model("cpu")
        self.assertGreater(model.samples, 50)
        self.assertAlmostEqual(model.a, 0.8, delta=0.15)

    def test_anomaly_flags_model_failure(self):
        from skeleton.overseer.mpc import SystemIdentifier
        sid = SystemIdentifier()
        for i in range(30):
            sid.observe("thermal", 60.0 + (i % 2) * 0.1, 1.0, 0.0)
        # Sudden dynamics break
        anomalies = []
        for i in range(10):
            sid.observe("thermal", 95.0 + i * 2, 1.0, 0.0)
        self.assertIn("thermal", sid.anomalies(threshold=2.0))

    def test_stats_shape(self):
        from skeleton.overseer.mpc import SystemIdentifier
        sid = SystemIdentifier()
        for _ in range(5):
            sid.observe("x", 0.5, 1.0, 0.0)
        stats = sid.stats()
        self.assertIn("x", stats)
        for key in ("a", "b", "c", "anomaly_score", "samples"):
            self.assertIn(key, stats["x"])


class TestMPC(unittest.TestCase):
    def test_terminal_wall_is_hard_even_when_wall_penalty_is_zero(self):
        from skeleton.overseer.mpc import ChannelModel, ModelPredictiveController
        mpc = ModelPredictiveController(horizon=1, weights={"wall": 0.0})
        result = mpc.plan({"thermal": ChannelModel("thermal", a=0.0, b=100.0, c=0.0)},
                          {"thermal": 70.0}, {"thermal": 95.0}, current_u=0.8)
        self.assertEqual(result.control, 0.8)
        self.assertLessEqual(result.planned_path[-1], 85.0)
        self.assertTrue(result.constraint_wall_hit)

    def test_infeasible_plan_minimizes_violation_before_tracking_cost(self):
        from skeleton.overseer.mpc import ChannelModel, ModelPredictiveController
        mpc = ModelPredictiveController(horizon=2, walls={"cpu": 1.0},
                                       weights={"track": 1e12, "wall": 0.0})
        result = mpc.plan({"cpu": ChannelModel("cpu", a=1.0, b=1.0, c=0.0)},
                          {"cpu": 2.0}, {"cpu": 3.0}, current_u=0.8)
        self.assertEqual(result.control, 0.05)
        self.assertTrue(result.constraint_wall_hit)

    def test_invalid_plan_inputs_fail_before_planning(self):
        from skeleton.overseer.mpc import ModelPredictiveController
        for horizon in (0, -1, True, 2.5):
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                ModelPredictiveController(horizon=horizon)
        mpc = ModelPredictiveController()
        for control in (float("nan"), float("inf"), 0.0, 1.1, True):
            with self.subTest(control=control), self.assertRaises(ValueError):
                mpc.plan({}, {}, {}, current_u=control)
        self.assertEqual(mpc.stats()["plans"], 0)

    def _models(self):
        from skeleton.overseer.mpc import ChannelModel
        return {
            "thermal": ChannelModel(name="thermal", a=0.9, b=-0.05, c=0.1),
            "memory": ChannelModel(name="memory", a=0.95, b=-0.02, c=0.03),
        }

    def test_plan_returns_feasible_control(self):
        from skeleton.overseer.mpc import ModelPredictiveController
        mpc = ModelPredictiveController(horizon=6)
        result = mpc.plan(self._models(), {"thermal": 70.0, "memory": 0.6},
                          {"thermal": 66.0, "memory": 0.68}, current_u=0.8)
        self.assertGreaterEqual(result.control, 0.05)
        self.assertLessEqual(result.control, 1.0)
        self.assertGreater(result.candidates_evaluated, 1)

    def test_no_model_preserves_current_control(self):
        from skeleton.overseer.mpc import ModelPredictiveController
        mpc = ModelPredictiveController()
        result = mpc.plan({}, {}, {}, current_u=0.7)
        self.assertEqual(result.trajectory_name, "hold")
        self.assertEqual(result.control, 0.7)

    def test_wall_violation_marks_result(self):
        from skeleton.overseer.mpc import ModelPredictiveController, ChannelModel
        mpc = ModelPredictiveController(horizon=4)
        models = {"memory": ChannelModel(name="memory", a=1.0, b=0.0, c=0.0)}
        result = mpc.plan(models, {"memory": 0.95}, {"memory": 0.68}, current_u=1.0)
        self.assertTrue(result.constraint_wall_hit)


class TestDigitalTwin(unittest.TestCase):
    def _models(self):
        from skeleton.overseer.mpc import ChannelModel
        return {"cpu": ChannelModel(name="cpu", a=0.9, b=-0.1, c=0.1)}

    def test_replay_computes_delta(self):
        from skeleton.overseer.twin import DigitalTwin
        twin = DigitalTwin()
        for i in range(12):
            twin.record({"cpu": 0.6 + i * 0.01}, 1.0, 0.5, 0.04)
        cf = twin.replay(self._models(), alternate_u=0.5, back_ticks=10,
                         setpoints={"cpu": 0.7})
        self.assertEqual(cf.simulated_ticks, 10)
        self.assertIsInstance(cf.delta, float)

    def test_grid_search_returns_all_candidates(self):
        from skeleton.overseer.twin import DigitalTwin
        twin = DigitalTwin()
        for _ in range(6):
            twin.record({"cpu": 0.6}, 1.0, 0.5, 0.04)
        grid = twin.grid_search(self._models(), back_ticks=5, setpoints={"cpu": 0.7})
        self.assertEqual(len(grid), 5)


class TestMetaCognition(unittest.TestCase):
    def test_nonfinite_inputs_cannot_poison_errors_or_parameter_rewrites(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(value=value):
                for action in (lambda: meta.observe_error("cpu", value),
                               lambda: meta.observe_regret(value),
                               lambda: meta.consider_rewrite("gain", -1.0, value, "test")):
                    with self.assertRaises(ValueError):
                        action()
        self.assertEqual(meta._errors, {})
        self.assertEqual(meta._regret_window, [])
        self.assertEqual(meta.rewrites, [])

    def test_scorecard_grades(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        for e in [0.01, -0.01, 0.01, -0.01, 0.01, -0.01, 0.01]:
            meta.observe_error("cpu", e)
        sc = meta.scorecard("cpu")
        self.assertEqual(sc.grade, "A")

    def test_oscillation_detected(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        for e in [0.3, -0.3, 0.3, -0.3, 0.3, -0.3]:
            meta.observe_error("cpu", e)
        sc = meta.scorecard("cpu")
        self.assertGreater(sc.oscillation_index, 0.5)
        self.assertNotEqual(sc.grade, "A")

    def test_regret_triggers_bounded_rewrite(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        for _ in range(10):
            meta.observe_regret(0.8)
        rw = meta.consider_rewrite("setpoints.thermal", 66.0, 40.0, "test")
        self.assertIsNotNone(rw)
        # Bounded to -25%: 66 * 0.75 = 49.5
        self.assertAlmostEqual(rw.after, 49.5, places=2)
        self.assertEqual(meta._regret_window, [])

    def test_no_rewrite_without_regret(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        meta.observe_regret(0.1)
        self.assertIsNone(meta.consider_rewrite("x", 1.0, 0.5, "test"))

    def test_negative_parameter_moves_toward_proposal_within_bound(self):
        from skeleton.overseer.twin import MetaCognition
        for proposed, expected in ((-20.0, -12.5), (-1.0, -7.5), (-9.0, -9.0)):
            with self.subTest(proposed=proposed):
                meta = MetaCognition()
                for _ in range(10):
                    meta.observe_regret(0.8)
                rewrite = meta.consider_rewrite("gain", -10.0, proposed, "regression")
                self.assertIsNotNone(rewrite)
                self.assertEqual(rewrite.after, expected)

    def test_trust_drops_with_persistent_regret(self):
        from skeleton.overseer.twin import MetaCognition
        meta = MetaCognition()
        for e in [0.2, -0.2, 0.2, -0.2, 0.2, -0.2]:
            meta.observe_error("cpu", e)
        for _ in range(20):
            meta.observe_regret(0.9)
        self.assertLess(meta.trust(), 0.6)


class TestEngineV3(unittest.TestCase):
    def test_tick_full_telemetry(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        engine = OverseerEngineV3()
        tick = engine.tick()
        d = tick.to_dict()
        for key in ("control", "mpc", "models", "anomalies", "regime",
                    "trust", "fallback", "wear", "budget"):
            self.assertIn(key, d)
        self.assertGreaterEqual(d["control"], 0.05)
        self.assertLessEqual(d["control"], 1.0)

    def test_enforcer_applies_mpc_budget(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        engine = OverseerEngineV3()
        applied = []
        engine.bind("probe", lambda b: applied.append(b.queue_size))
        engine.tick()
        self.assertEqual(len(applied), 1)

    def test_sysid_models_appear_over_ticks(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        engine = OverseerEngineV3()
        for _ in range(6):
            engine.tick()
        stats = engine.sysid.stats()
        self.assertGreater(len(stats), 0)
        self.assertTrue(all(s["samples"] >= 1 for s in stats.values()))

    def test_status_shape(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        engine = OverseerEngineV3()
        engine.tick()
        status = engine.status()
        for key in ("device", "control", "setpoints", "sysid", "mpc",
                    "twin", "meta", "wear", "consumers"):
            self.assertIn(key, status)

    def test_fallback_path_reachable(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        from skeleton.overseer.twin import MetaCognition
        engine = OverseerEngineV3()
        # Force low trust
        for e in [0.4, -0.4, 0.4, -0.4, 0.4, -0.4]:
            engine.meta.observe_error("cpu", e)
        for _ in range(20):
            engine.meta.observe_regret(0.95)
        tick = engine.tick()
        self.assertTrue(tick.fallback)
        self.assertLessEqual(tick.control, 0.5)

    def test_history_bounded(self):
        from skeleton.overseer.engine_v3 import OverseerEngineV3
        engine = OverseerEngineV3()
        for _ in range(70):
            engine.tick()
        self.assertEqual(len(engine._history), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
